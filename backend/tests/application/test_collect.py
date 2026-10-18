import pytest

from app.domain import events
from app.domain.errors import CredentialsRejected, ProviderThrottled, ProviderUnavailable
from app.domain.model import GapCause
from app.domain.values import ErrorKind, Instant
from tests.application.conftest import INTERVAL
from tests.builders import DHW, m


async def test_records_new_measurements_and_logs_success(ctx):
    now = ctx.clock.now()
    ctx.gateway.measurements = [m(Instant(now.epoch - 600), 53.17, polled=now)]
    result = await ctx.collect().run()
    assert result.outcome.ok and result.outcome.recorded == 1
    assert len(await ctx.measurements.latest()) == 1
    assert (await ctx.poll_log.last_success()).at == now
    [eq] = await ctx.equipment.all()
    assert eq.available is True and eq.first_seen == now
    assert any(isinstance(e, events.MeasurementRecorded) for e in ctx.events)


async def test_unchanged_provider_instant_is_not_recorded_again(ctx):
    t = ctx.clock.now()
    ctx.gateway.measurements = [m(Instant(t.epoch - 600), 53.17)]
    uc = ctx.collect()
    await uc.run()
    ctx.clock.advance(INTERVAL)
    second = await uc.run()
    assert second.outcome.recorded == 0
    assert second.gap is None


async def test_restart_does_not_duplicate(ctx):
    t = ctx.clock.now()
    ctx.gateway.measurements = [m(Instant(t.epoch - 600), 53.17)]
    await ctx.collect().run()
    ctx.clock.advance(INTERVAL)
    # nouvelle instance = redémarrage : le cache est rechargé depuis la base
    again = await ctx.collect().run()
    assert again.outcome.recorded == 0


async def test_provider_errors_are_logged_typed_and_reraised(ctx):
    ctx.gateway.fail_with = ProviderThrottled("429", retry_after=600)
    with pytest.raises(ProviderThrottled):
        await ctx.collect().run()
    [o] = await ctx.poll_log.recent()
    assert not o.ok and o.error_kind is ErrorKind.THROTTLED
    assert isinstance(ctx.events[-1], events.PollFailed)


async def test_credentials_rejected_emits_dedicated_event(ctx):
    ctx.gateway.fail_with = CredentialsRejected("invalid_grant")
    with pytest.raises(CredentialsRejected):
        await ctx.collect().run()
    assert isinstance(ctx.events[-1], events.CredentialsRejected)


async def test_unexpected_errors_are_logged_as_unexpected(ctx):
    ctx.gateway.fail_with = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        await ctx.collect().run()
    [o] = await ctx.poll_log.recent()
    assert o.error_kind is ErrorKind.UNEXPECTED


async def test_gap_recorded_on_recovery_after_provider_failures(ctx):
    uc = ctx.collect()
    await uc.run()
    first = ctx.clock.now()
    ctx.gateway.fail_with = ProviderUnavailable("503")
    for _ in range(4):
        ctx.clock.advance(INTERVAL)
        with pytest.raises(ProviderUnavailable):
            await uc.run()
    ctx.gateway.fail_with = None
    ctx.clock.advance(INTERVAL)
    result = await uc.run()
    assert result.recovered_after_failure
    assert result.gap is not None and result.gap.cause is GapCause.PROVIDER_ERROR
    assert result.gap.start == first + INTERVAL and result.gap.end == ctx.clock.now()
    assert len(await ctx.gaps.list(first, ctx.clock.now())) == 1


async def test_gap_recorded_after_downtime_restart(ctx):
    await ctx.collect().run()
    before = ctx.clock.now()
    ctx.clock.advance(3 * 3600)  # conteneur arrêté 3 h
    result = await ctx.collect().run()
    assert result.gap.cause is GapCause.DOWNTIME and result.gap.start == before + INTERVAL


async def test_availability_from_gateway_is_stored(ctx):
    ctx.gateway.available = {DHW: False}
    await ctx.collect().run()
    [eq] = await ctx.equipment.all()
    assert eq.available is False
