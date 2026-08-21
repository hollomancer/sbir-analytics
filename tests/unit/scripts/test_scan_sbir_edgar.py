from scripts.archive.data.scan_sbir_edgar import _ServerErrorTracker


def test_request_error_tracker_marks_rate_limited_company() -> None:
    tracker = _ServerErrorTracker()
    tracker.register("Acme Labs")

    tracker.write(
        "EDGAR filing mention search failed for 'Acme Labs': "
        "429 Too Many Requests"
    )

    assert tracker.had_error("Acme Labs")


def test_request_error_tracker_ignores_unrelated_warning() -> None:
    tracker = _ServerErrorTracker()
    tracker.register("Acme Labs")

    tracker.write("A warning unrelated to an EFTS request")

    assert not tracker.had_error("Acme Labs")
