"""Proposing the categories a tree is missing — and the restraint that makes it
worth reading.

The categorizer no longer declines, so nothing else notices when the *tree* is
the problem. This module is what notices. Which means the interesting tests are
not "does it propose something" but the four ways it must refuse to: one odd
line is not a taxonomy claim, a category the tree already has is not missing, a
dismissal is an answer, and a run must leave the tree exactly as it found it.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from ai_api.suggestions.gaps import (
    MIN_GROUP_SIZE, build_prompt, doubtful_lines, group_by_supplier, suggest_gaps,
)
from web_api.db.models import (
    Company, Invoice, InvoiceLine, Organization, SpendCategory,
    SpendCategorySuggestion, SuggestionState, Vendor,
)
from web_api.spend_trees import service

PROPOSAL = (
    '{"name": "Ground Transport", "description": "Rail, bus and taxi.", '
    '"parent": "Travel & Entertainment", "rationale": "Rail travel has no home."}'
)


def _replying(text: str):
    seen: list[str] = []

    def complete(prompt: str) -> str:
        seen.append(prompt)
        return text

    complete.prompts = seen  # type: ignore[attr-defined]
    return complete


@pytest.fixture()
def world():
    """An org, a company on a bare travel taxonomy, and a rail supplier.

    Deliberately *not* the default template: that now ships `Ground Transport`,
    so a tree built from it has no gap to find and every test here would be
    asserting against the wrong thing.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Organization(id="org", name="Org"))
        s.commit()
        tree = service.create_tree(s, "org", "Sparse", max_depth=3)
        root = service.add_node(s, tree, "Indirect")
        travel = service.add_node(s, tree, "Travel & Entertainment", parent_id=root.id)
        service.add_node(s, tree, "Airfare", parent_id=travel.id,
                         description="Flights and other long-distance travel")
        s.commit()

        company = Company(id="co", organization_id="org", name="Acme",
                          base_currency="DKK", spend_tree_id=tree.id)
        vendor = Vendor(id="v-dsb", name="DSB",
                        description="Danish State Railways, passenger rail.")
        s.add(company)
        s.add(vendor)
        s.commit()
        yield {"session": s, "tree": tree, "company": company, "vendor": vendor}


def _doubtful(world, count: int, *, vendor_id: str = "v-dsb", prefix: str = "Togbillet"):
    s = world["session"]
    invoice = Invoice(company_id="co", vendor_id=vendor_id, status="uncategorized")
    s.add(invoice)
    s.commit()
    for index in range(count):
        s.add(InvoiceLine(
            company_id="co", invoice_id=invoice.id, item_name=f"{prefix} {index}",
            amount=Decimal("58.00"), status="ai_categorized",
            level_1="Indirect", level_2="Travel & Entertainment", level_3="Airfare",
            confidence=Decimal("0.250"),
        ))
    s.commit()


def _paths(s: Session, tree_id: str) -> set[tuple]:
    nodes = s.exec(select(SpendCategory).where(SpendCategory.spend_tree_id == tree_id)).all()
    return {tuple(x for x in (n.level_1, n.level_2, n.level_3) if x) for n in nodes}


# -- The signal ---------------------------------------------------------------


def test_a_run_of_unconfident_answers_becomes_one_suggestion(world):
    _doubtful(world, 5)

    run = suggest_gaps(world["session"], "co", complete=_replying(PROPOSAL))

    assert run.proposed == 1
    suggestion = world["session"].exec(select(SpendCategorySuggestion)).first()
    assert suggestion.name == "Ground Transport"
    assert suggestion.state == SuggestionState.PENDING
    assert len(suggestion.evidence_line_ids) == 5


def test_the_suggestion_names_an_existing_node_as_its_parent(world):
    _doubtful(world, 4)

    suggest_gaps(world["session"], "co", complete=_replying(PROPOSAL))

    s = world["session"]
    suggestion = s.exec(select(SpendCategorySuggestion)).first()
    parent = s.get(SpendCategory, suggestion.parent_id)
    assert parent is not None and parent.name == "Travel & Entertainment"


def test_confident_lines_are_not_evidence(world):
    """A confident answer is evidence the tree works."""
    s = world["session"]
    invoice = Invoice(company_id="co", vendor_id="v-dsb", status="uncategorized")
    s.add(invoice)
    s.commit()
    for index in range(6):
        s.add(InvoiceLine(
            company_id="co", invoice_id=invoice.id, item_name=f"Flight {index}",
            amount=Decimal("900.00"), status="ai_categorized",
            level_3="Airfare", confidence=Decimal("0.950"),
        ))
    s.commit()

    run = suggest_gaps(s, "co", complete=_replying(PROPOSAL))

    assert run.considered == 0 and run.proposed == 0


# -- The four refusals --------------------------------------------------------


def test_one_odd_line_is_not_a_taxonomy_change(world):
    """A category is a structural claim about how a company spends. One strange
    purchase is not one, and a tree that grows a node per strange invoice is
    worse than a tree with a gap — the gap is at least visible."""
    _doubtful(world, MIN_GROUP_SIZE - 1)

    run = suggest_gaps(world["session"], "co", complete=_replying(PROPOSAL))

    assert run.groups == 0 and run.proposed == 0


def test_a_category_the_tree_already_has_is_not_proposed(world):
    """The correct outcome when the *categorizer* was the problem rather than the
    taxonomy — which is why the prompt invites the answer instead of forbidding
    it. A model told never to name an existing category will invent one."""
    _doubtful(world, 4)
    already = PROPOSAL.replace('"name": "Ground Transport"', '"name": "Airfare"')

    run = suggest_gaps(world["session"], "co", complete=_replying(already))

    assert run.already_present == 1 and run.proposed == 0
    assert world["session"].exec(select(SpendCategorySuggestion)).first() is None


def test_a_dismissed_suggestion_is_not_proposed_again(world):
    """Re-arguing a question the customer has answered is how a review list
    becomes something people stop opening."""
    _doubtful(world, 4)
    s = world["session"]
    s.add(SpendCategorySuggestion(
        spend_tree_id=world["tree"].id, company_id="co", name="Ground Transport",
        state=SuggestionState.DISMISSED,
    ))
    s.commit()

    run = suggest_gaps(s, "co", complete=_replying(PROPOSAL))

    assert run.dismissed_before == 1 and run.proposed == 0


def test_a_matching_name_is_recognised_however_it_is_written(world):
    """Compared the way a person compares them. "ground transport" and
    "Ground Transport" are the same answer, and storing both would put a
    duplicate in front of a reviewer as though it were new."""
    _doubtful(world, 4)
    s = world["session"]
    s.add(SpendCategorySuggestion(
        spend_tree_id=world["tree"].id, company_id="co", name="ground  transport!",
        state=SuggestionState.DISMISSED,
    ))
    s.commit()

    run = suggest_gaps(s, "co", complete=_replying(PROPOSAL))

    assert run.proposed == 0


# -- It writes no tree --------------------------------------------------------


def test_a_run_leaves_the_tree_exactly_as_it_found_it(world):
    """The guarantee the whole feature rests on. A tree is the customer's
    statement of how they think about their own spending; a system that edits it
    unattended has taken that away, and every categorization made afterwards is
    against a taxonomy they never chose."""
    _doubtful(world, 6)
    s = world["session"]
    before = _paths(s, world["tree"].id)

    suggest_gaps(s, "co", complete=_replying(PROPOSAL))

    assert _paths(s, world["tree"].id) == before


def test_an_unparseable_reply_costs_one_group_not_the_run(world):
    _doubtful(world, 4)
    _doubtful(world, 4, vendor_id="v-other", prefix="Kontorartikler")
    s = world["session"]
    s.add(Vendor(id="v-other", name="Lyreco"))
    s.commit()

    replies = iter(["I'm sorry, I can't help with that.", PROPOSAL])
    run = suggest_gaps(s, "co", complete=lambda prompt: next(replies))

    assert run.groups == 2
    assert run.proposed == 1
    assert len(run.notes) == 1


# -- Scoping ------------------------------------------------------------------


def test_a_company_with_no_tree_suggests_nothing(world):
    s = world["session"]
    company = s.get(Company, "co")
    company.spend_tree_id = None
    s.add(company)
    s.commit()
    _doubtful(world, 5)

    run = suggest_gaps(s, "co", complete=_replying(PROPOSAL))

    assert run.proposed == 0 and run.notes


def test_lines_whose_invoice_names_no_supplier_are_not_grouped(world):
    """They have nothing in common but our ignorance. A proposal argued from
    them would cite lines that share no property at all."""
    s = world["session"]
    invoice = Invoice(company_id="co", vendor_id=None, status="uncategorized")
    s.add(invoice)
    s.commit()
    for index in range(5):
        s.add(InvoiceLine(
            company_id="co", invoice_id=invoice.id, item_name=f"Ukendt {index}",
            amount=Decimal("10.00"), status="ai_categorized",
            confidence=Decimal("0.100"),
        ))
    s.commit()

    assert group_by_supplier(s, doubtful_lines(s, "co")) == {}


# -- The prompt ---------------------------------------------------------------


def test_the_prompt_shows_the_tree_and_the_evidence(world):
    _doubtful(world, 4)
    s = world["session"]
    complete = _replying(PROPOSAL)

    suggest_gaps(s, "co", complete=complete)

    prompt = complete.prompts[0]
    assert "DSB — Danish State Railways" in prompt
    assert "Togbillet 0" in prompt
    assert "Indirect > Travel & Entertainment > Airfare" in prompt
    assert "landed in Airfare" in prompt, "where the doubtful lines went is the argument"
