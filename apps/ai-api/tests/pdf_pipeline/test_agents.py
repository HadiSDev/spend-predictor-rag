from ai_api.agents import make_categorizer, make_extractor, make_verifier


def test_all_agents_are_toolless():
    assert make_extractor().tools == []
    assert make_verifier().tools == []
    assert make_categorizer().tools == []


def test_agents_have_distinct_roles():
    roles = {make_extractor().role, make_verifier().role, make_categorizer().role}
    assert len(roles) == 3
