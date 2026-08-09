"""The migration chain must be runnable from base on a fresh database.

This is the regression guard for a defect that stood for twenty migrations: the
chain had no initial schema migration at all — its base revision opened with
``ALTER TABLE organizations`` and nothing in it ever ran ``create_table`` for a
base table. The schema was only ever created out-of-band by
``SQLModel.metadata.create_all()``, so ``alembic upgrade head`` against an empty
database failed with ``UndefinedTable``. The rest of the suite cannot see any of
this: it builds its schema with ``create_all`` on SQLite and never runs a
migration.

Two levels of guard:

* :func:`test_single_base_and_head` is static and always runs. Cheap, and it
  catches an accidental second base or a branched head.
* :func:`test_upgrade_from_empty_database` is the real one. It creates a
  throwaway PostgreSQL database, runs ``alembic upgrade head`` in a subprocess
  exactly as a developer would, and asserts the result is a *usable* schema —
  including an ``AuditLog`` write **through the ORM**, which is the only path
  that exercises ``audit_log.seq``'s server-side sequence. (Raw SQL always
  worked; a baseline missing the sequence passes a raw INSERT that names ``seq``
  and fails every real audit write. Do not weaken this to raw SQL.)

If PostgreSQL is not reachable the second test **skips with a reason** rather
than passing — a guard that quietly passes is worse than no guard.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def _script_directory():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))


def test_single_base_and_head() -> None:
    """Exactly one base and one head — no branch, no orphaned root."""
    script = _script_directory()
    assert len(script.get_heads()) == 1, f"expected one head, got {script.get_heads()}"
    bases = script.get_bases()
    assert len(bases) == 1, f"expected one base revision, got {bases}"


def test_base_revision_creates_tables() -> None:
    """The base revision must actually create tables.

    The original chain's base revision started with ``ALTER TABLE``; nothing in
    the whole chain created one. This is the static shape of that bug.
    """
    script = _script_directory()
    (base,) = script.get_bases()
    source = Path(script.get_revision(base).path).read_text()
    assert "op.create_table(" in source, (
        f"base revision {base} creates no table — a fresh database has nothing "
        "to ALTER. See tests/web_api/test_migrations.py."
    )


def _web_api_table_names() -> set[str]:
    """Tables the **domain** owns — not everything on ``SQLModel.metadata``.

    ``SQLModel.metadata`` is a single global registry shared by both packages,
    so importing ``ai_api.persistence`` anywhere in a test session adds
    ``line_ground_truth`` to it. That table is deliberately ai_api-owned and
    deliberately absent from the domain's migrations (and from the live
    database), so comparing against the raw metadata makes this test pass or
    fail depending on which other tests ran first.
    """
    import web_api.db.models as models

    return {
        obj.__tablename__
        for obj in vars(models).values()
        if isinstance(obj, type)
        and issubclass(obj, SQLModel)
        and getattr(obj, "__table__", None) is not None
    }


# Every engine this test builds gets a bounded connect timeout — see the
# comment at its first use.
_CONNECT_ARGS: dict = {"connect_args": {"connect_timeout": 5}}


def _assert_subprocess_targets(env: dict[str, str], db_name: str) -> None:
    """Refuse to migrate anything but the throwaway database.

    The subprocess picks up its URL from ``web_api.config``, which calls
    ``load_dotenv()``. That resolves to the ``DATABASE_URL`` we set here *only*
    because ``load_dotenv``'s default is ``override=False``, so the real
    environment beats ``.env``. Flip that one keyword to ``True`` — a plausible,
    entirely unrelated edit — and this test would silently run ``alembic upgrade
    head`` against the developer's live database instead. That failure mode is
    destructive and invisible, so it gets a check rather than a comment: ask the
    subprocess what URL it actually resolved, *before* anything is migrated.
    """
    probe = subprocess.run(
        [sys.executable, "-c", "from web_api.config import DATABASE_URL; print(DATABASE_URL)"],
        cwd=REPO_ROOT,
        env={**env, "PYTHONPATH": str(REPO_ROOT / "src")},
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
    from web_api.config import DATABASE_URL

    url = make_url(DATABASE_URL)
    if not url.drivername.startswith("postgresql"):
        return None
    # render_as_string(hide_password=False): str(URL) masks the password as "***".
    return url.set(database="postgres").render_as_string(hide_password=False)


def test_upgrade_from_empty_database() -> None:
    admin_url = _postgres_admin_url()
    if admin_url is None:
        pytest.skip("DATABASE_URL is not PostgreSQL; migrations target PostgreSQL only")

    # connect_timeout is what keeps "unreachable ⇒ skip" from becoming
    # "unreachable ⇒ hang". A host that *refuses* the connection fails
    # instantly, but one that silently drops packets — a firewalled CI runner,
    # a stale host in DATABASE_URL — otherwise leaves libpq waiting on the OS
    # TCP timeout, which is far longer than any sensible test budget. With this,
    # the failure arrives in seconds and lands in the skip branch below.
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", **_CONNECT_ARGS)
    try:
        with admin.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL not reachable at {make_url(admin_url).host}: {exc}")

    # Never the configured database: always a fresh, uniquely named throwaway
    # that this test drops again.
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
            [sys.executable, "-m", "alembic", "upgrade", "head"],
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
            # Belt and braces: the migration ran somewhere, and this proves
            # where. Cheap, and it fails loudly instead of leaving a corrupted
            # dev database to be discovered later.
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
            # Never let the comparison go vacuous if the discovery above breaks.
            assert {"organizations", "audit_log", "erp_entries"} <= expected
            assert expected <= present, (
                "migrations left tables missing that the ORM expects: "
                f"{sorted(expected - present)}"
            )

            # The audit sequence: `server_default=FetchedValue()` on the model
            # renders no DDL, so autogenerate cannot produce this and only a
            # hand-written statement in the migration can.
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

            # The write itself, through the ORM. This is the assertion that
            # would actually have caught the shipped bug.
            from web_api.audit import record_audit

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
