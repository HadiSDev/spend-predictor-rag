"""Fixtures for the sync runner: in-memory SQLite plus a scriptable connector.

Tenants here are built the way the customer API builds them — organization,
company, then a connected ``ErpIntegration`` — and never by the runner. That is
the whole point of the change under test: the runner reads its work, it does not
create it.
"""
from __future__ import annotations


import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from ai_api.sync import runner
from web_api.db.models import Company, ErpCredential, ErpIntegration, Organization

from ai_api_testkit import FakeConnector  # importing it registers the "fake" ERP


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
    """A real Fernet key, so encrypt/decrypt round-trips like production."""
    from cryptography.fernet import Fernet
    from web_api import config as web_config

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(web_config, "WEB_API_CREDENTIAL_ENC_KEY", key)
    return key


@pytest.fixture
def make_tenant(engine):
    """Build a tenant the way the API does, never via the runner.

    Returns a callable so a test can build several and check that one run
    covers them all.
    """
    def _make(name: str = "Acme", *, erp_type: str = "fake",
              credentials: dict | None = None, connected: bool = True) -> dict:
        from web_api.credentials import encrypt_config

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
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


# --- Suite-wide guards ----------------------------------------------------
# These lived in a repository-root conftest.py while both APIs shared one test
# tree. Each app now carries the ones its own session needs, so the web-api
# suite never imports ai_api (the root conftest's categorizer guard used to).


@pytest.fixture(autouse=True)
def offline_fx(monkeypatch):
    """No test ever fetches a rate over the network.

    `FX_ENABLED` is read from the environment, and the environment includes the
    developer's own `.env`. Switching FX on for real work therefore reached into
    the suite: two tests asserting the off-by-default posture began failing, and
    — far worse — `default_provider()` started handing back the Frankfurter
    client, so a full run made outbound HTTP requests. The codebase promises the
    opposite in as many words: "tests and offline runs make no outbound
    request."

    Forcing it off costs no coverage. Every test that wants rates injects its
    own `StubProvider` into `FxService`; only `default_provider()` consults this
    flag, and what those two tests assert is precisely the default. A test that
    genuinely needs the flag on can monkeypatch it back.
    """
    from web_api import config as web_config

    monkeypatch.setattr(web_config, "FX_ENABLED", False)


@pytest.fixture(autouse=True)
def offline_categorizer(monkeypatch):
    """No test ever calls a real model.

    The line categorizer asks an LLM, so without this the suite would open
    network connections to whatever `VLLM_BASE_URL` points at — hanging when
    nothing is listening and, worse, passing or failing on a model's mood.

    The stand-in reads the prompt the categorizer actually built and answers in
    the format it actually expects, so the seam under test is the real one: it
    parses the numbered candidate list, scores it against the line's own words,
    and picks the best overlap or declines. Deterministic, offline, and it
    exercises the parsing and grounding paths rather than bypassing them.

    A test that wants a specific answer passes its own `complete` to
    `categorize_line`, or monkeypatches this back out.
    """
    import re

    from ai_api.sync import llm_categorizer

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
