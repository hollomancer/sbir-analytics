from sbir_etl.reporting.procurement_transition.plain_language import check_plain_language


def test_flags_jargon_with_suggestions():
    result = check_plain_language(
        "## Snapshot\n\n- Award cohort: 5 awards\n- Screening rank: composite 0.87\n"
    )
    assert {finding["term"] for finding in result["jargon"]} == {"cohort", "composite score"}
    assert all(finding["suggestion"] for finding in result["jargon"])
    assert not result["passed"]


def test_flags_overlong_sentences():
    sentence = " ".join(["word"] * 31) + "."
    result = check_plain_language(sentence)
    assert result["long_sentences"][0]["words"] == 31
    assert not result["passed"]


def test_ignores_quoted_public_text_and_tables():
    markdown = (
        "> The quoted abstract mentions a cohort, topical similarity, and "
        + " ".join(["word"] * 40)
        + "\n\n| Award work | Why listed |\n|---|---|\n| Composite 9 watchlist materials | data |\n"
    )
    result = check_plain_language(markdown)
    assert result["passed"]


def test_strips_markdown_before_counting():
    result = check_plain_language("**Screening result:** passed 2 of 3 checks \\[details\\].")
    assert result["passed"]
    assert result["sentences"] == 1


def test_clean_packet_text_passes_with_stats():
    markdown = "# Packet\n\nThe award funded navigation software. The notice asks for a flight demonstration.\n"
    result = check_plain_language(markdown)
    assert result["passed"]
    assert result["sentences"] == 2
    assert result["average_sentence_length"] > 0
