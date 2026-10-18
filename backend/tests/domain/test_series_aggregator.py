import itertools

import pytest

from app.domain.model import Gap, GapCause
from app.domain.services import SeriesAggregator, bucket_bounds
from app.domain.values import BucketSize, Instant
from tests.builders import COUNTER, m, paris

agg = SeriesAggregator()
H = 3600


def test_time_weighted_average_with_locf():
    # 10 °C pendant 45 min puis 20 °C pendant 15 min : moyenne 12,5, pas 15
    t0 = 1_800_000_000 - 1_800_000_000 % H
    [b] = agg.aggregate([m(t0, 10), m(t0 + 2700, 20)], Instant(t0), Instant(t0 + H), BucketSize.HOUR)
    assert b.avg == pytest.approx(12.5)
    assert (b.min, b.max, b.last, b.samples, b.covered_seconds) == (10, 20, 20, 2, H)


def test_prior_value_is_carried_into_the_period():
    t0 = 1_800_000_000 - 1_800_000_000 % H
    [b] = agg.aggregate([], Instant(t0), Instant(t0 + H), BucketSize.HOUR, prior=m(t0 - 600, 42))
    assert b.avg == 42 and b.samples == 0 and b.covered_seconds == H


def test_no_data_means_empty_bucket_not_zero():
    t0 = 1_800_000_000 - 1_800_000_000 % H
    [b] = agg.aggregate([], Instant(t0), Instant(t0 + H), BucketSize.HOUR)
    assert (b.avg, b.min, b.max, b.covered_seconds) == (None, None, None, 0)


def test_gaps_interrupt_locf():
    t0 = 1_800_000_000 - 1_800_000_000 % H
    gap = Gap(Instant(t0 + 1800), Instant(t0 + 3 * H), GapCause.DOWNTIME)
    b1, b2, b3 = agg.aggregate(
        [m(t0, 10), m(t0 + 3 * H, 30)], Instant(t0), Instant(t0 + 3 * H), BucketSize.HOUR, gaps=[gap]
    )
    assert b1.covered_seconds == 1800 and b1.avg == 10
    assert b2.covered_seconds == 0 and b2.avg is None  # on n'invente pas la valeur pendant le trou
    assert b3.covered_seconds == 0


def test_known_until_stops_carrying_the_last_value():
    t0 = 1_800_000_000 - 1_800_000_000 % H
    [b] = agg.aggregate([m(t0, 10)], Instant(t0), Instant(t0 + H), BucketSize.HOUR, known_until=Instant(t0 + 600))
    assert b.covered_seconds == 600


def test_non_numeric_values_are_skipped():
    from dataclasses import replace

    from app.domain.values import MeasurementValue

    t0 = 1_800_000_000 - 1_800_000_000 % H
    text = replace(m(t0, 0), value=MeasurementValue.of_text("Heat"))
    [b] = agg.aggregate([text], Instant(t0), Instant(t0 + H), BucketSize.HOUR)
    assert b.samples == 0 and b.avg is None


def test_counter_deltas_with_reset():
    t0 = 1_800_000_000 - 1_800_000_000 % H
    pts = [
        m(t0, 100, key=COUNTER),
        m(t0 + 600, 130, key=COUNTER),
        m(t0 + H + 60, 5, key=COUNTER),
        m(t0 + H + 120, 25, key=COUNTER),
    ]
    b1, b2 = agg.aggregate(pts, Instant(t0), Instant(t0 + 2 * H), BucketSize.HOUR, cumulative=True)
    assert b1.delta == 30
    # remise à zéro : 130 -> 5 compte 5, puis +20
    assert b2.delta == 25


def test_counter_delta_across_gap_is_kept_whole_and_flagged():
    t0 = 1_800_000_000 - 1_800_000_000 % H
    gap = Gap(Instant(t0 + 300), Instant(t0 + 2 * H), GapCause.PROVIDER_ERROR)
    pts = [m(t0, 100, key=COUNTER), m(t0 + 2 * H + 10, 160, key=COUNTER)]
    *_, last = agg.aggregate(pts, Instant(t0), Instant(t0 + 3 * H), BucketSize.HOUR, gaps=[gap], cumulative=True)
    assert last.delta == 60 and last.delta_spans_gap


def test_counter_delta_uses_prior_point():
    t0 = 1_800_000_000 - 1_800_000_000 % H
    [b] = agg.aggregate(
        [m(t0 + 60, 110, key=COUNTER)],
        Instant(t0),
        Instant(t0 + H),
        BucketSize.HOUR,
        prior=m(t0 - 60, 100, key=COUNTER),
        cumulative=True,
    )
    assert b.delta == 10


def test_five_minute_buckets_are_aligned():
    bounds = bucket_bounds(Instant(1_000_000_123), Instant(1_000_000_123 + 600), BucketSize.FIVE_MINUTES)
    assert all(lo.epoch % 300 == 0 and hi - lo == 300 for lo, hi in bounds)
    assert len(bounds) == 3


@pytest.mark.parametrize(
    ("day", "hours"),
    [((2026, 3, 29), 23), ((2026, 10, 25), 25), ((2026, 10, 18), 24)],
    ids=["heure-d-ete", "heure-d-hiver", "jour-normal"],
)
def test_daily_buckets_follow_paris_midnights(day, hours):
    start = paris(*day)
    [(lo, hi)] = bucket_bounds(start, start + 3600, BucketSize.DAY)
    assert lo == start
    assert hi - lo == hours * H


def test_daily_average_over_25_hour_day():
    start = paris(2026, 10, 25)
    [b] = agg.aggregate([m(start, 10), m(start + 24 * H, 35)], start, start + 25 * H, BucketSize.DAY)
    # 24 h à 10 puis 1 h à 35 : (240 + 35) / 25
    assert b.covered_seconds == 25 * H
    assert b.avg == pytest.approx(11.0)


def test_hourly_buckets_across_dst_change_are_contiguous():
    start = paris(2026, 10, 25)
    bounds = bucket_bounds(start, start + 25 * H, BucketSize.HOUR)
    assert len(bounds) == 25
    assert all(b[0] == a[1] for a, b in itertools.pairwise(bounds))
