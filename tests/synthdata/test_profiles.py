from spend_predictor.synthdata.profiles import PROFILES, BuyerProfile, level1_for


def test_level1_depends_on_buyer_business():
    saas = BuyerProfile(
        name="Nimbus SaaS A/S", website="https://nimbus.example", country_code="DK",
        vat_number="DK11111111", business_description="Cloud SaaS platform.",
        direct_level2=frozenset({"Technology"}),
    )
    law = BuyerProfile(
        name="Lex Partners", website="https://lex.example", country_code="DE",
        vat_number="DE222222222", business_description="Corporate law firm.",
        direct_level2=frozenset({"Professional Services"}),
    )
    # Same account (Technology) is Direct for the SaaS buyer, Indirect for the firm.
    assert level1_for(saas, "Technology") == "Direct"
    assert level1_for(law, "Technology") == "Indirect"
    assert level1_for(law, "Professional Services") == "Direct"


def test_profiles_are_populated_and_well_formed():
    assert len(PROFILES) >= 3
    for p in PROFILES:
        assert isinstance(p, BuyerProfile)
        assert p.name and p.country_code and p.vat_number and p.business_description
        assert isinstance(p.direct_level2, frozenset) and p.direct_level2
