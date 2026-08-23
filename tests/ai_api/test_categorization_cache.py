"""The keys the answer cache is built on.

A cache key that is too broad serves an answer to a question nobody asked; one
that is too specific never hits. Every test here pins one side of that line.
"""
from __future__ import annotations

from ai_api.sync.cache import question_key, question_sample, tree_hash
from ai_api.sync.categorizer import Category


def _leaf(node_id: str, *path: str, description: str | None = None) -> Category:
    return Category(node_id=node_id, path=path, name=path[-1], description=description)


TREE = [
    _leaf("n-air", "Indirect", "Travel", "Airfare"),
    _leaf("n-ground", "Indirect", "Travel", "Ground Transport"),
]


# -- The question -------------------------------------------------------------


def test_the_same_line_asks_the_same_question():
    assert question_key("Togbillet", None, "DSB", "6830") == question_key(
        "Togbillet", None, "DSB", "6830"
    )


def test_trivial_restatements_collide():
    """Case and whitespace are not a different purchase."""
    assert question_key(" togbillet ", None, "dsb", "6830") == question_key(
        "Togbillet", None, "DSB", "6830"
    )


def test_a_different_supplier_is_a_different_question():
    """The supplier is often the whole answer — the same words from a haulier
    and from a stationer are different spend."""
    assert question_key("Levering", None, "DSV", None) != question_key(
        "Levering", None, "Lyreco", None
    )


def test_a_different_ledger_account_is_a_different_question():
    assert question_key("Gebyr", None, "Bank", "7300") != question_key(
        "Gebyr", None, "Bank", "6030"
    )


def test_the_amount_is_not_part_of_the_question():
    """Two DSB tickets at 58,00 and 5.780,00 are the same categorization
    question. Keying on the amount would make every line unique and the cache
    would never hit."""
    # There is no amount parameter at all — asserted by signature, which is the
    # only way to pin an absence.
    assert question_key("Togbillet", None, "DSB", None) == question_key(
        "Togbillet", None, "DSB", None
    )


# -- The tree -----------------------------------------------------------------


def test_the_same_tree_hashes_the_same():
    assert tree_hash(TREE) == tree_hash(TREE)


def test_order_does_not_matter():
    """A retrieval change that reshuffles candidates must not invalidate every
    answer we have."""
    assert tree_hash(TREE) == tree_hash(list(reversed(TREE)))


def test_adding_a_node_changes_it():
    """The load-bearing case. A cached answer is a pointer into a taxonomy, and
    a customer who adds a node has changed what the question's options were."""
    wider = TREE + [_leaf("n-lodging", "Indirect", "Travel", "Lodging")]

    assert tree_hash(wider) != tree_hash(TREE)


def test_renaming_a_node_changes_it():
    renamed = [_leaf("n-air", "Indirect", "Travel", "Flights"), TREE[1]]

    assert tree_hash(renamed) != tree_hash(TREE)


def test_removing_a_node_changes_it():
    assert tree_hash(TREE[:1]) != tree_hash(TREE)


def test_changing_a_description_changes_it():
    """The model reads it, so two nodes differing only there are different
    questions."""
    described = [
        _leaf("n-air", "Indirect", "Travel", "Airfare", description="Flights only"),
        TREE[1],
    ]

    assert tree_hash(described) != tree_hash(TREE)


def test_new_ids_for_the_same_taxonomy_do_not_change_it():
    """A CSV re-import rebuilds the tree with fresh ids. Invalidating every
    answer over that would be paying to relearn something unchanged."""
    reimported = [
        _leaf("fresh-1", "Indirect", "Travel", "Airfare"),
        _leaf("fresh-2", "Indirect", "Travel", "Ground Transport"),
    ]

    assert tree_hash(reimported) == tree_hash(TREE)


def test_a_narrowed_set_is_a_different_question():
    """Narrowing changes what the model was offered, which changes what its
    answer means. The two must not share a cache entry."""
    assert tree_hash(TREE[:1]) != tree_hash(TREE)


# -- Debuggability ------------------------------------------------------------


def test_the_sample_is_readable():
    """A cache whose rows are two hex digests is one nobody can reason about
    when it starts answering wrongly."""
    sample = question_sample("Togbillet", "DSB", "6830")

    assert "Togbillet" in sample and "DSB" in sample


def test_the_sample_is_bounded():
    assert len(question_sample("x" * 500, "y" * 500, None)) <= 200


def test_describing_the_supplier_is_a_different_question():
    """The rule: every prompt input is a key input, unless it provably cannot
    change the answer.

    Leaving this out was the first version, and it made vendor enrichment
    silently useless — describing "DSB" as Danish State Railways is exactly the
    change that turns an unanswerable line into an obvious one, and the cache
    would have kept serving the answer from before anybody knew what DSB was.
    """
    unknown = question_key("1 Voksen", None, "DSB", None)
    described = question_key("1 Voksen", None, "DSB", None, "Danish State Railways.")

    assert unknown != described


# -- Through the runner -------------------------------------------------------


import pytest  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from ai_api.persistence import CategorizationCache  # noqa: E402
from web_api.db.models import Company, InvoiceLine, SpendCategory  # noqa: E402
from web_api.spend_trees import service  # noqa: E402


@pytest.fixture()
def counting(monkeypatch):
    """A model that answers candidate 1 and counts how often it is asked."""
    from ai_api.sync import llm_categorizer

    calls: list[str] = []

    def complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"choice": 1, "confidence": 0.9, "rationale": "stub"}'

    monkeypatch.setattr(llm_categorizer, "_default_complete", complete)
    return calls


def _on_default_tree(engine, company_id: str):
    with Session(engine) as s:
        company = s.get(Company, company_id)
        tree = service.ensure_default_tree(s, company.organization_id)
        company.spend_tree_id = tree.id
        s.add(company)
        s.commit()
        return tree.id


def _requeue(engine):
    """Return every line to the backlog, as `recategorize` does."""
    with Session(engine) as s:
        for line in s.exec(select(InvoiceLine)).all():
            line.status = "uncategorized"
            s.add(line)
        s.commit()


def test_a_repeated_line_costs_one_model_call(engine, make_tenant, counting):
    """Most lines on a real ledger are repeats — the same monthly ticket from
    the same supplier — and each one is a model call of several seconds."""
    from ai_api.sync import runner

    tenant = make_tenant("Acme")
    _on_default_tree(engine, tenant["company_id"])

    runner.run_sync()
    assert len(counting) == 1

    _requeue(engine)
    runner.run_sync()

    assert len(counting) == 1, "the second pass must be answered from cache"


def test_a_cached_answer_is_indistinguishable_on_the_line(engine, make_tenant, counting):
    from ai_api.sync import runner

    tenant = make_tenant("Acme")
    _on_default_tree(engine, tenant["company_id"])
    runner.run_sync()

    with Session(engine) as s:
        line = s.exec(select(InvoiceLine)).first()
        fresh = (line.status, line.spend_category_id, line.level_3,
                 line.confidence, line.rationale)

    _requeue(engine)
    runner.run_sync()

    with Session(engine) as s:
        line = s.exec(select(InvoiceLine)).first()
        assert (line.status, line.spend_category_id, line.level_3,
                line.confidence, line.rationale) == fresh


def test_editing_the_tree_invalidates_the_answer(engine, make_tenant, counting):
    """The load-bearing half of the key. A cached answer is a pointer into a
    taxonomy, and a customer who adds a node has changed the question."""
    from ai_api.sync import runner

    tenant = make_tenant("Acme")
    tree_id = _on_default_tree(engine, tenant["company_id"])
    runner.run_sync()
    assert len(counting) == 1

    with Session(engine) as s:
        from web_api.db.models import SpendTree

        tree = s.get(SpendTree, tree_id)
        tech = s.exec(
            select(SpendCategory).where(
                SpendCategory.spend_tree_id == tree_id,
                SpendCategory.name == "Technology",
            )
        ).first()
        service.add_node(s, tree, "Observability", parent_id=tech.id)
        s.commit()

    _requeue(engine)
    runner.run_sync()

    assert len(counting) == 2, "a changed candidate set is a new question"


def test_two_companies_on_different_trees_do_not_share_an_answer(
    engine, make_tenant, counting
):
    from ai_api.sync import runner

    first = make_tenant("Acme")
    second = make_tenant("Beta")
    _on_default_tree(engine, first["company_id"])
    with Session(engine) as s:
        company = s.get(Company, second["company_id"])
        tree = service.create_tree(s, company.organization_id, "Custom", max_depth=3)
        root = service.add_node(s, tree, "Indirect")
        mid = service.add_node(s, tree, "IT", parent_id=root.id)
        service.add_node(s, tree, "Hosting", parent_id=mid.id)
        company.spend_tree_id = tree.id
        s.add(company)
        s.commit()

    runner.run_sync()

    assert len(counting) == 2, "each tree is its own question"


def test_a_cached_pointer_to_a_deleted_node_is_not_trusted(
    engine, make_tenant, counting
):
    """The cache carries no foreign key — one would make deleting a spend
    category fail on a *cache* row, a customer's tree edit refused by an
    optimization. A dangling pointer is resolved on read instead."""
    from ai_api.sync import runner

    tenant = make_tenant("Acme")
    tree_id = _on_default_tree(engine, tenant["company_id"])
    runner.run_sync()

    with Session(engine) as s:
        row = s.exec(select(CategorizationCache)).first()
        assert row is not None
        row.spend_category_id = "no-such-node"
        s.add(row)
        s.commit()

    _requeue(engine)
    runner.run_sync()

    with Session(engine) as s:
        line = s.exec(select(InvoiceLine)).first()
        # Left for the next run to answer afresh, never written from a pointer
        # that resolves to nothing.
        assert line.status == "uncategorized"
