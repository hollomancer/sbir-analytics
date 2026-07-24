from sbir_etl.reporting.procurement_transition.ai import validate_cited_summary


def test_accepts_only_evidence_cited_sentences():
    assert validate_cited_summary("The notice concerns navigation prototypes. [SAM]")
    assert validate_cited_summary("This is definitely Phase III.") is None
    assert validate_cited_summary(None) is None
