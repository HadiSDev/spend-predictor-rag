"""Fixtures for the sync runner: in-memory SQLite plus a scriptable connector."""
from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from ai_api.sync import llm_categorizer, runner
from ai_api_testkit import FakeConnector
from web_api import config as web_config
from web_api.credentials import encrypt_config
from web_api.db.models import Company, ErpCredential, ErpIntegration, Organization


@pytest.fixture(autouse=True)
def fake_connector():
    FakeConnector.reset()
    yield FakeConnector
    FakeConnector.reset()


@pytest.fixture
def engine(monkeypatch):
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(runner, "engine", eng)
    return eng


@pytest.fixture
def enc_key(monkeypatch):
    """Install a real Fernet key as the credential encryption key."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(web_config, "WEB_API_CREDENTIAL_ENC_KEY", key)
    return key


@pytest.fixture
def make_tenant(engine):
    """Build an org, company and ERP integration the way the API does."""
    def _make(name: str = "Acme", *, erp_type: str = "fake",
              credentials: dict | None = None, connected: bool = True) -> dict:
        with Session(engine) as s:
            org = Organization(name=f"{name} Org", clerk_org_id=f"clerk_{name}")
            s.add(org)
            s.commit()
            company = Company(organization_id=org.id, name=name)
            s.add(company)
            s.commit()
            integration = ErpIntegration(
                company_id=company.id,
                erp_type=erp_type,
                label=f"{name} connection",
                connected_at=None if not connected else _utcnow(),
                disconnected_at=None if connected else _utcnow(),
            )
            s.add(integration)
            s.commit()
            if credentials is not None:
                s.add(ErpCredential(erp_integration_id=integration.id,
                                    encrypted_config=encrypt_config(credentials)))
                s.commit()
            return {"org_id": org.id, "company_id": company.id,
                    "integration_id": integration.id, "name": name}

    return _make


def _utcnow():
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def offline_fx(monkeypatch):
    """No test ever fetches a rate over the network."""
    monkeypatch.setattr(web_config, "FX_ENABLED", False)


@pytest.fixture(autouse=True)
def offline_categorizer(monkeypatch):
    """No test ever calls a real model."""
    def _words(text: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}

    def offline_complete(prompt: str) -> str:
        facts, _, rest = prompt.partition("Categories:")
        line_words = _words(facts.split("Invoice line:", 1)[-1])
        best_index, best_score = 0, 0
        for raw in rest.splitlines():
            match = re.match(r"\s*(\d+)\.\s+(.*)", raw)
            if not match or match.group(1) == "0":
                continue
            score = len(line_words & _words(match.group(2)))
            if score > best_score:
                best_index, best_score = int(match.group(1)), score
        if best_index == 0:
            return '{"choice": 0, "confidence": 0.0, "rationale": "offline stand-in found no overlap"}'
        return (
            f'{{"choice": {best_index}, "confidence": 0.9, '
            f'"rationale": "offline stand-in matched {best_score} word(s)"}}'
        )

    monkeypatch.setattr(llm_categorizer, "_default_complete", offline_complete)
