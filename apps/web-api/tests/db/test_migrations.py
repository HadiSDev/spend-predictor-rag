"""The migration chain must be runnable from base on a fresh database."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel

from web_api import config as web_config
from web_api.audit import record_audit
from web_api.db import models

APP_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = APP_ROOT.parents[1]
ALEMBIC_INI = APP_ROOT / "alembic.ini"


def _script_directory():
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))


def test_single_base_and_head() -> None:
    script = _script_directory()
    assert len(script.get_heads()) == 1, f"expected one head, got {script.get_heads()}"
    bases = script.get_bases()
    assert len(bases) == 1, f"expected one base revision, got {bases}"


def test_base_revision_creates_tables() -> None:
    script = _script_directory()
    (base,) = script.get_bases()
    source = Path(script.get_revision(base).path).read_text()
    assert "op.create_table(" in source, (
        f"base revision {base} creates no table — a fresh database has nothing "
        "to ALTER. See apps/web-api/tests/db/test_migrations.py."
    )


def _web_api_table_names() -> set[str]:
    """Tables the **domain** owns — not everything on ``SQLModel.metadata``."""

    return {
        obj.__tablename__
        for obj in vars(models).values()
        if isinstance(obj, type)
        and issubclass(obj, SQLModel)
        and getattr(obj, "__table__", None) is not None
    }


_CONNECT_ARGS: dict = {"connect_args": {"connect_timeout": 5}}


def _assert_subprocess_targets(env: dict[str, str], db_name: str) -> None:
    """Refuse to migrate anything but the throwaway database."""
    probe = subprocess.run(
        [sys.executable, "-c", "from web_api.config import DATABASE_URL; print(DATABASE_URL)"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, f"could not resolve the subprocess URL:\n{probe.stderr}"
    resolved = make_url(probe.stdout.strip())
    assert resolved.database == db_name, (
        f"the migration subprocess would target {resolved.database!r}, not the "
        f"throwaway {db_name!r} — refusing to run it. Has load_dotenv() been "
        "switched to override=True in web_api/config.py?"
    )


def _postgres_admin_url() -> str | None:
    """URL of the ``postgres`` maintenance DB on the configured server, or None."""

    url = make_url(web_config.DATABASE_URL)
    if not url.drivername.startswith("postgresql"):
        return None
    return url.set(database="postgres").render_as_string(hide_password=False)


def _upgrade(env: dict[str, str], revision: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", revision],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


@contextmanager
def _throwaway_database(admin_url: str):
    """A uniquely named database, dropped again however the body exits."""
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", **_CONNECT_ARGS)
    db_name = f"sp_migration_guard_{uuid.uuid4().hex[:12]}"
    target_url = make_url(admin_url).set(database=db_name).render_as_string(
        hide_password=False
    )
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    try:
        yield db_name, target_url
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin.dispose()


def _reachable_admin_url() -> str:
    """The admin URL, or skip — with the reason, never a quiet pass."""
    admin_url = _postgres_admin_url()
    if admin_url is None:
        pytest.skip("DATABASE_URL is not PostgreSQL; migrations target PostgreSQL only")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", **_CONNECT_ARGS)
    try:
        with admin.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PostgreSQL not reachable at {make_url(admin_url).host}: {exc}")
    finally:
        admin.dispose()
    return admin_url


def test_backfill_queues_only_the_invoices_that_have_a_scan() -> None:
    admin_url = _reachable_admin_url()

    with _throwaway_database(admin_url) as (db_name, target_url):
        env = {**os.environ, "DATABASE_URL": target_url}
        _assert_subprocess_targets(env, db_name)

        baseline = _upgrade(env, "0001_baseline_schema")
        assert baseline.returncode == 0, (
            f"upgrade to the baseline failed:\n{baseline.stdout}\n{baseline.stderr}"
        )

        engine = create_engine(target_url, **_CONNECT_ARGS)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO organizations (id, name, status, created_at) "
                        "VALUES ('org', 'Org', 'active', now())"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO companies "
                        "(id, organization_id, name, base_currency, is_active, created_at) "
                        "VALUES ('co', 'org', 'Co', 'DKK', true, now())"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO files "
                        "(id, company_id, filename, file_type, storage_path, status, created_at) "
                        "VALUES ('f1', 'co', 'scan.pdf', 'invoice_pdf', 's3://x', 'pending', now())"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO invoices "
                        "(id, company_id, file_id, status, source, created_at) VALUES "
                        "('with-scan', 'co', 'f1', 'uncategorized', 'erp', now()), "
                        "('no-scan', 'co', NULL, 'uncategorized', 'erp', now())"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO invoice_lines "
                        "(id, company_id, invoice_id, status, created_at) "
                        "VALUES ('ln', 'co', 'with-scan', 'uncategorized', now())"
                    )
                )

            head = _upgrade(env, "head")
            assert head.returncode == 0, (
                f"upgrade from the baseline failed:\n{head.stdout}\n{head.stderr}"
            )

            with engine.connect() as conn:
                statuses = dict(
                    conn.execute(text("SELECT id, doc_status FROM invoices")).all()
                )
                attempts = dict(
                    conn.execute(text("SELECT id, doc_attempts FROM invoices")).all()
                )
                origins = dict(
                    conn.execute(text("SELECT id, origin FROM invoice_lines")).all()
                )

            assert statuses["with-scan"] == "pending", (
                "an invoice that already had a scan was not queued — the whole "
                f"pre-0002 corpus would be invisible to the stage (got {statuses})"
            )
            assert statuses["no-scan"] == "not_applicable", (
                f"an invoice with no scan must not be queued (got {statuses})"
            )
            assert set(attempts.values()) == {0}, f"attempts not zeroed: {attempts}"
            assert origins == {"ln": "erp"}, (
                f"pre-existing lines must backfill to 'erp', got {origins}"
            )
        finally:
            engine.dispose()


def _downgrade(env: dict[str, str], revision: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "downgrade", revision],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_0004_rebuilds_flat_spend_categories_as_a_tree() -> None:
    admin_url = _reachable_admin_url()

    with _throwaway_database(admin_url) as (db_name, target_url):
        env = {**os.environ, "DATABASE_URL": target_url}
        _assert_subprocess_targets(env, db_name)

        before = _upgrade(env, "0003_line_unit_and_doc_number")
        assert before.returncode == 0, (
            f"upgrade to 0003 failed:\n{before.stdout}\n{before.stderr}"
        )

        engine = create_engine(target_url, **_CONNECT_ARGS)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO organizations (id, name, status, created_at) "
                        "VALUES ('org', 'Org', 'active', now())"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO companies "
                        "(id, organization_id, name, base_currency, is_active, created_at) "
                        "VALUES ('co', 'org', 'Co', 'DKK', true, now())"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO spend_categories "
                        "(id, company_id, level_1, level_2, level_3, created_at) VALUES "
                        "('leaf', 'co', 'Indirect', 'Technology', 'Cloud', now())"
                    )
                )

            head = _upgrade(env, "head")
            assert head.returncode == 0, (
                f"upgrade from 0003 failed:\n{head.stdout}\n{head.stderr}"
            )

            with engine.connect() as conn:
                tree_id = conn.execute(
                    text("SELECT spend_tree_id FROM companies WHERE id = 'co'")
                ).scalar_one()
                nodes = conn.execute(
                    text(
                        "SELECT id, parent_id, depth, name, level_1, level_2, level_3 "
                        "FROM spend_categories ORDER BY depth"
                    )
                ).all()

            assert tree_id is not None, "the company was not assigned a migrated tree"
            assert [n.depth for n in nodes] == [1, 2, 3], (
                f"the implied ancestors were not materialized: {nodes}"
            )
            root, mid, leaf = nodes
            assert (root.name, root.parent_id) == ("Indirect", None)
            assert (mid.name, mid.parent_id) == ("Technology", root.id)
            assert (leaf.name, leaf.parent_id) == ("Cloud", mid.id)
            assert leaf.id == "leaf", (
                "the original row must keep its id — invoice_lines.spend_category_id "
                f"points at it (got {leaf.id!r})"
            )
            assert (root.level_1, root.level_2) == ("Indirect", None), (
                f"a depth-1 node's path is its level_1 alone (got {root})"
            )

            back = _downgrade(env, "0003_line_unit_and_doc_number")
            assert back.returncode == 0, (
                f"downgrade of 0004 failed:\n{back.stdout}\n{back.stderr}"
            )

            with engine.connect() as conn:
                restored = conn.execute(
                    text("SELECT id, company_id FROM spend_categories ORDER BY id")
                ).all()
            assert {r.company_id for r in restored} == {"co"}, (
                f"downgrade did not restore company_id: {restored}"
            )
        finally:
            engine.dispose()


def test_upgrade_from_empty_database() -> None:
    admin_url = _postgres_admin_url()
    if admin_url is None:
        pytest.skip("DATABASE_URL is not PostgreSQL; migrations target PostgreSQL only")

    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", **_CONNECT_ARGS)
    try:
        with admin.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PostgreSQL not reachable at {make_url(admin_url).host}: {exc}")

    db_name = f"sp_migration_guard_{uuid.uuid4().hex[:12]}"
    target_url = make_url(admin_url).set(database=db_name).render_as_string(
        hide_password=False
    )

    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    try:
        env = {**os.environ, "DATABASE_URL": target_url}
        _assert_subprocess_targets(env, db_name)

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            "`alembic upgrade head` failed on an empty database — the chain is "
            f"not runnable from base.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

        engine = create_engine(target_url, **_CONNECT_ARGS)
        try:
            with engine.connect() as conn:
                actual_db = conn.execute(text("SELECT current_database()")).scalar()
            assert actual_db == db_name, (
                f"migrated {actual_db!r}, not the throwaway {db_name!r}"
            )

            with engine.connect() as conn:
                present = set(
                    conn.execute(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = 'public'"
                        )
                    ).scalars()
                )
            expected = _web_api_table_names()
            assert {"organizations", "audit_log", "erp_entries"} <= expected
            assert expected <= present, (
                "migrations left tables missing that the ORM expects: "
                f"{sorted(expected - present)}"
            )

            with engine.connect() as conn:
                default = conn.execute(
                    text(
                        "SELECT column_default FROM information_schema.columns "
                        "WHERE table_name = 'audit_log' AND column_name = 'seq'"
                    )
                ).scalar()
            assert default and "nextval(" in default, (
                f"audit_log.seq has no sequence default (got {default!r}) — every "
                "audit write would fail with NotNullViolation"
            )

            with Session(engine) as session:
                record_audit(session, entity_type="invoice_line", entity_id="a", action="verify")
                record_audit(session, entity_type="invoice_line", entity_id="b", action="verify")
                session.commit()
            with engine.connect() as conn:
                seqs = list(
                    conn.execute(text("SELECT seq FROM audit_log ORDER BY seq")).scalars()
                )
            assert len(seqs) == 2, f"expected 2 audit rows, got {seqs}"
            assert all(s is not None for s in seqs), f"NULL seq written: {seqs}"
            assert len(set(seqs)) == 2, f"duplicate seq written: {seqs}"
        finally:
            engine.dispose()
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin.dispose()
