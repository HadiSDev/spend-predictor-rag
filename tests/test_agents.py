from spend_predictor.agents import make_categorizer, make_extractor, make_verifier
from spend_predictor.rag.search_tool import ChartOfAccountsSearchTool


def test_extractor_and_verifier_have_no_tools():
    assert make_extractor().tools == []
    assert make_verifier().tools == []


def test_categorizer_has_rag_tool():
    cat = make_categorizer()
    assert any(isinstance(t, ChartOfAccountsSearchTool) for t in cat.tools)


def test_agents_have_distinct_roles():
    roles = {make_extractor().role, make_verifier().role, make_categorizer().role}
    assert len(roles) == 3
