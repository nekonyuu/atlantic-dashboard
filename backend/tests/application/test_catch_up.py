from datetime import date

from app.adapters.outbound.fake import NullHistorySource
from app.domain.model import Gap, GapCause
from app.domain.values import EnergyDay, Tariff
from tests.builders import paris


def day(d, kwh=1.0, cat=1, tariff=Tariff.OFF_PEAK):
    return EnergyDay(d, cat, tariff, kwh)


async def test_no_source_means_nothing_fabricated(ctx):
    ctx.history = NullHistorySource()
    report = await ctx.catch_up().run()
    assert not report.source_available and report.energy_days == 0
    assert await ctx.energy.range(date(2026, 1, 1), date(2026, 12, 31)) == []


async def test_energy_days_are_backfilled_idempotently(ctx):
    ctx.history.days = [day(date(2026, 10, 16), 3.4), day(date(2026, 10, 17), 8.4)]
    first = await ctx.catch_up().run()
    second = await ctx.catch_up().run()
    assert first.energy_days == 2 and second.energy_days == 0
    assert len(await ctx.energy.range(date(2026, 10, 1), date(2026, 10, 31))) == 2


async def test_today_is_rewritten_until_closed(ctx):
    ctx.history.days = [day(date(2026, 10, 18), 1.0)]
    await ctx.catch_up().run()
    ctx.history.days = [day(date(2026, 10, 18), 2.5)]
    report = await ctx.catch_up().run()
    assert report.energy_days == 1
    [d] = await ctx.energy.range(date(2026, 10, 18), date(2026, 10, 18))
    assert d.kwh == 2.5


async def test_window_is_bounded_by_source_capacity_and_since(ctx):
    await ctx.catch_up().run()
    await ctx.catch_up().run(since=date(2026, 10, 10))
    await ctx.catch_up().run(since=date(2020, 1, 1))
    (s1, u1), (s2, _), (s3, _) = ctx.history.requests
    assert u1 == date(2026, 10, 18) and (u1 - s1).days == 32
    assert s2 == date(2026, 10, 10)
    assert s3 == s1  # jamais au-delà de ce que la source sait fournir


async def test_gaps_inside_covered_days_are_marked_recovered(ctx):
    inside = await ctx.gaps.add(Gap(paris(2026, 10, 16, 3), paris(2026, 10, 16, 9), GapCause.DOWNTIME))
    outside = await ctx.gaps.add(Gap(paris(2026, 10, 1, 3), paris(2026, 10, 1, 9), GapCause.DOWNTIME))
    ctx.history.days = [day(date(2026, 10, 16)), day(date(2026, 10, 17))]
    report = await ctx.catch_up().run()
    assert report.gaps_recovered == 1
    [g_in] = await ctx.gaps.list(inside.start, inside.end)
    [g_out] = await ctx.gaps.list(outside.start, outside.end)
    assert g_in.recovered and not g_out.recovered
