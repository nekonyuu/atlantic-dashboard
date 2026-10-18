import pytest

from app.adapters.outbound.fake import FakeBackupService
from app.application.usecases.backup import RunBackup
from app.application.usecases.purge import PurgeRaw
from app.application.usecases.queries import GetGaps, GetHealth, GetLatest, GetSeries
from app.domain.errors import ProviderUnavailable
from app.domain.values import BucketSize, ErrorKind, Instant, PollOutcome
from tests.application.conftest import INTERVAL
from tests.builders import COUNTER, DHW, TEMP, m


def series_uc(ctx, cumulative=()):
    return GetSeries(
        measurements=ctx.measurements,
        gaps=ctx.gaps,
        poll_log=ctx.poll_log,
        clock=ctx.clock,
        gap_detector=ctx.gap_detector,
        cumulative_metrics=cumulative,
    )


def health_uc(ctx):
    return GetHealth(
        poll_log=ctx.poll_log,
        gaps=ctx.gaps,
        equipment=ctx.equipment,
        storage=ctx.storage,
        clock=ctx.clock,
        gap_detector=ctx.gap_detector,
        poll_interval=INTERVAL,
    )


async def test_latest_reports_age(ctx):
    now = ctx.clock.now()
    await ctx.measurements.append([m(Instant(now.epoch - 900), 53.0)])
    [v] = await GetLatest(ctx.measurements, ctx.clock).run(DHW)
    assert v.age_seconds == 900


async def test_series_carries_prior_value_and_returns_gaps(ctx):
    now = ctx.clock.now()
    start = Instant(now.epoch - 2 * 3600)
    await ctx.measurements.append([m(Instant(start.epoch - 60), 50.0), m(Instant(start.epoch + 3600), 54.0)])
    await ctx.poll_log.add(PollOutcome.success(now, 1, 0))
    res = await series_uc(ctx).run(DHW, TEMP, start, now, BucketSize.HOUR)
    b1, b2 = res.series.buckets
    assert b1.avg == 50.0 and b2.avg == 54.0
    assert res.gaps == []


async def test_series_includes_ongoing_gap(ctx):
    now = ctx.clock.now()
    await ctx.poll_log.add(PollOutcome.success(Instant(now.epoch - 3600), 1, 0))
    res = await series_uc(ctx).run(DHW, TEMP, Instant(now.epoch - 7200), now, BucketSize.HOUR)
    assert len(res.gaps) == 1 and res.gaps[0].end == now
    gaps = await GetGaps(ctx.gaps, ctx.poll_log, ctx.clock, ctx.gap_detector).run(Instant(0), now)
    assert len(gaps) == 1


async def test_series_counter_deltas(ctx):
    now = ctx.clock.now()
    start = Instant(now.epoch - now.epoch % 3600 - 3600)
    await ctx.measurements.append([m(start, 100, key=COUNTER), m(Instant(start.epoch + 1800), 130, key=COUNTER)])
    res = await series_uc(ctx, cumulative={COUNTER}).run(
        DHW, COUNTER, start, Instant(start.epoch + 3600), BucketSize.HOUR
    )
    assert res.series.buckets[0].delta == 30


async def test_series_rejects_empty_period(ctx):
    now = ctx.clock.now()
    with pytest.raises(ValueError):
        await series_uc(ctx).run(DHW, TEMP, now, now, BucketSize.HOUR)


async def test_health_reports_staleness_errors_and_availability(ctx):
    h = await health_uc(ctx).run()
    assert h.poller_stale and h.last_success is None

    await ctx.collect().run()
    h = await health_uc(ctx).run()
    assert not h.poller_stale and h.availability == {DHW: True} and h.db_size_bytes == 4096

    ctx.gateway.fail_with = ProviderUnavailable("503")
    uc = ctx.collect()
    for _ in range(4):
        ctx.clock.advance(INTERVAL)
        with pytest.raises(ProviderUnavailable):
            await uc.run()
    h = await health_uc(ctx).run()
    assert h.poller_stale
    assert h.error_counts == {ErrorKind.UNAVAILABLE: 4}
    assert ErrorKind.UNAVAILABLE in h.last_errors
    assert len(h.recent_gaps) == 1  # trou en cours


async def test_backup_runs_under_writer_lock(ctx):
    backup = FakeBackupService()
    name = await RunBackup(backup, ctx.clock, ctx.lock).run()
    assert name == "pac-2026-10-18.db" and backup.snapshots == [name]


async def test_purge_disabled_by_default(ctx):
    await ctx.measurements.append([m(0, 1.0)])
    purge = PurgeRaw(
        measurements=ctx.measurements, gaps=ctx.gaps, clock=ctx.clock, writer_lock=ctx.lock, retention_days=0
    )
    assert await purge.run() == 0


async def test_purge_aggregates_hourly_before_deleting_and_keeps_last_point(ctx):
    now = ctx.clock.now()
    old = now.epoch - 40 * 86400
    old -= old % 3600
    await ctx.measurements.append([m(old, 10.0), m(old + 1800, 20.0), m(old + 3600, 30.0)])
    purge = PurgeRaw(
        measurements=ctx.measurements, gaps=ctx.gaps, clock=ctx.clock, writer_lock=ctx.lock, retention_days=30
    )
    deleted = await purge.run()
    assert deleted == 2
    assert ctx.measurements.hourly[(DHW, TEMP, Instant(old))].avg == 15.0
    [kept] = await ctx.measurements.latest()
    assert kept.value.number == 30.0
