"""SpendCategory ORM: the renamed spend-tree node with stored level_1..level_4."""
from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from web_api.db.models import Company, Organization, SpendCategory


def _engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(e)
    return e


def test_spend_category_persists_all_levels():
    e = _engine()
    with Session(e) as s:
        org = Organization(id="o1", name="Org")
        co = Company(id="c1", organization_id="o1", name="Co")
        s.add(org)
        s.add(co)
        s.add(SpendCategory(
            company_id="c1",
            level_1="Indirect", level_2="Technology", level_3="Cloud Infrastructure",
            level_4="Compute", description="cloud servers",
        ))
        s.commit()

    with Session(e) as s:
        node = s.exec(select(SpendCategory).where(SpendCategory.level_3 == "Cloud Infrastructure")).one()
        assert node.level_1 == "Indirect"       # Direct/Indirect stored on the node
        assert node.level_2 == "Technology"
        assert node.level_3 == "Cloud Infrastructure"
        assert node.level_4 == "Compute"
        # reachable via the renamed relationship
        co = s.get(Company, "c1")
        assert [c.level_2 for c in co.spend_categories] == ["Technology"]


def test_spend_category_table_name_and_no_voucher_confusion():
    # Renamed table; the ERP-side ErpAccount is a separate entity.
    assert SpendCategory.__tablename__ == "spend_categories"
    cols = set(SpendCategory.__table__.columns.keys())
    assert {"level_1", "level_2", "level_3", "level_4"} <= cols
    assert "level2" not in cols and "level3" not in cols
    # ERP account code/name belong to ErpAccount, not the spend-tree node.
    assert "account_code" not in cols and "account_name" not in cols


def test_optional_deeper_levels_nullable():
    e = _engine()
    with Session(e) as s:
        s.add(Organization(id="o1", name="Org"))
        s.add(Company(id="c1", organization_id="o1", name="Co"))
        s.add(SpendCategory(company_id="c1", level_2="Facilities & Office"))
        s.commit()
        node = s.exec(select(SpendCategory).where(SpendCategory.level_2 == "Facilities & Office")).one()
        assert node.level_2 == "Facilities & Office"
        assert node.level_1 is None and node.level_3 is None and node.level_4 is None
