import pytest

from app.domain.model import GapCause
from app.domain.services import GapDetector
from app.domain.values import ErrorKind, Instant, PollOutcome

INTERVAL = 300
det = GapDetector(interval=INTERVAL)


def ok(t):
    return PollOutcome.success(Instant(t), 10, 0)


def ko(t, kind=ErrorKind.UNAVAILABLE):
    return PollOutcome.failure(Instant(t), 10, kind, "x")


def test_regular_polls_produce_no_gap():
    assert det.detect([ok(0), ok(300), ok(610), ok(900)]) == []


def test_jitter_within_tolerance_is_not_a_gap():
    assert det.detect([ok(0), ok(590)]) == []


def test_downtime_without_polls():
    [g] = det.detect([ok(0), ok(3600)])
    assert (g.start, g.end, g.cause) == (Instant(300), Instant(3600), GapCause.DOWNTIME)


def test_provider_errors_between_successes():
    [g] = det.detect([ok(0), ko(300), ko(600, ErrorKind.THROTTLED), ok(1800)])
    assert g.cause is GapCause.PROVIDER_ERROR and g.end == Instant(1800)


def test_credentials_cause_wins():
    [g] = det.detect([ok(0), ko(300), ko(600, ErrorKind.CREDENTIALS), ok(1800)])
    assert g.cause is GapCause.CREDENTIALS


def test_unexpected_errors_give_unknown_cause():
    [g] = det.detect([ok(0), ko(300, ErrorKind.UNEXPECTED), ok(1800)])
    assert g.cause is GapCause.UNKNOWN


def test_outcomes_are_sorted_first():
    assert len(det.detect([ok(3600), ok(0)])) == 1


def test_ongoing_gap():
    assert det.ongoing(Instant(0), Instant(500)) is None
    g = det.ongoing(Instant(0), Instant(5000), [ko(300)])
    assert g is not None and g.end == Instant(5000) and g.cause is GapCause.PROVIDER_ERROR
    assert det.ongoing(None, Instant(5000)) is None


def test_invalid_interval():
    with pytest.raises(ValueError):
        GapDetector(0)
