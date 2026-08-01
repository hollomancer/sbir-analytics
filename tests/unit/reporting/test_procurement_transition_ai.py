from sbir_etl.reporting.procurement_transition.ai import (
    MAX_SUMMARY_CHARS,
    validate_cited_summary,
)


def test_accepts_only_evidence_cited_sentences():
    assert validate_cited_summary("The notice concerns navigation prototypes. [SAM]")
    assert validate_cited_summary("This is definitely Phase III.") is None
    assert validate_cited_summary(None) is None


def test_rejects_a_summary_whose_second_sentence_is_uncited():
    # Two citations in one sentence must not license an uncited claim in the next.
    assert (
        validate_cited_summary(
            "The award built a navigation stack [SBIR] and the notice asks for one [SAM]. "
            "This qualifies as Phase III."
        )
        is None
    )


def test_accepts_a_summary_where_every_sentence_carries_its_own_citation():
    assert validate_cited_summary(
        "The award built a navigation stack [SBIR]. The notice asks for one [SAM]."
    )


def test_rejects_summaries_longer_than_the_rendered_limit():
    filler = "The award built a navigation stack [SBIR]. " * 40
    assert len(filler) > MAX_SUMMARY_CHARS
    # Over-limit summaries are rejected rather than truncated after validation,
    # which could cut a sentence's citation off in the packet.
    assert validate_cited_summary(filler) is None
