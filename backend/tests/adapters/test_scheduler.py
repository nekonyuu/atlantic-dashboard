import asyncio
import contextlib
from datetime import date

import pytest

from app.adapters.inbound.scheduler import MAX_BACKOFF, Scheduler, next_delay
from app.domain.errors import CredentialsRejected, ProviderThrottled, ProviderUnavailable


def test_next_delay_policy():
    assert next_delay(300, 0, None) == 300
    assert next_delay(300, 1, ProviderThrottled("429", retry_after=900)) == 900
    assert next_delay(300, 1, ProviderThrottled("429", retry_after=10)) == 300
    assert [next_delay(300, n, ProviderUnavailable("x")) for n in (1, 2, 3)] == [300, 600, 1200]
    assert next_delay(300, 10, ProviderUnavailable("x")) == MAX_BACKOFF
    assert next_delay(300, 2, RuntimeError()) == 600


class Recorder:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def run(self, *args):
        self.calls += 1
        item = self.outcomes.pop(0) if self.outcomes else Ok()
        if isinstance(item, BaseException):
            raise item
        return item


class Ok:
    def __init__(self, recovered=False):
        self.recovered_after_failure = recovered


class Job:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    async def run(self, *args):
        self.calls += 1
        if self.fail:
            raise RuntimeError("job ko")
        return "ok"


def make(outcomes, *, days=None, catch_up=None, backup=None, max_cycles=None):
    collect = Recorder(outcomes)
    catch_up = catch_up or Job()
    backup = backup or Job()
    purge = Job()
    delays = []
    days = iter(days or [])
    current = {"d": date(2026, 10, 18)}

    async def sleep(d):
        delays.append(d)
        if max_cycles is not None and len(delays) >= max_cycles:
            raise asyncio.CancelledError

    def today():
        current["d"] = next(days, current["d"])
        return current["d"]

    s = Scheduler(
        collect=collect,
        catch_up=catch_up,
        backup=backup,
        purge=purge,
        interval=300,
        sleep=sleep,
        rand=lambda: 0.5,
        today=today,
    )
    return s, collect, catch_up, backup, purge, delays


async def run_until_done(s):
    task = s.start()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_polls_immediately_and_runs_daily_jobs_once_per_day():
    s, collect, catch_up, backup, purge, delays = make([], max_cycles=3)
    await run_until_done(s)
    assert collect.calls == 3
    assert (catch_up.calls, backup.calls, purge.calls) == (1, 1, 1)
    assert delays == [300, 300, 300]  # rand=0.5 -> jitter nul


async def test_daily_jobs_run_again_on_new_day():
    s, _, catch_up, backup, _, _ = make([], days=[date(2026, 10, 18)] * 4 + [date(2026, 10, 19)] * 4, max_cycles=4)
    await run_until_done(s)
    assert backup.calls == 2 and catch_up.calls == 2


async def test_backoff_then_catch_up_after_recovery():
    outcomes = [Ok(), ProviderUnavailable("503"), ProviderUnavailable("503"), Ok(recovered=True)]
    s, _collect, catch_up, _, _, delays = make(outcomes, max_cycles=4)
    await run_until_done(s)
    assert delays == [300, 300, 600, 300]
    assert catch_up.calls == 2  # démarrage + récupération
    assert s.state.consecutive_failures == 0


async def test_throttling_respects_retry_after():
    s, _, _, _, _, delays = make([ProviderThrottled("429", retry_after=1200)], max_cycles=1)
    await run_until_done(s)
    assert delays == [1200]


async def test_credentials_rejected_stops_the_loop_for_good():
    s, collect, *_, delays = make([Ok(), CredentialsRejected("invalid_grant"), Ok()], max_cycles=10)
    await run_until_done(s)
    assert collect.calls == 2 and len(delays) == 1
    assert s.state.stopped_reason == "credentials" and not s.state.running


async def test_unexpected_errors_never_kill_the_loop():
    s, collect, *_ = make([RuntimeError("boom"), KeyError("x"), Ok()], max_cycles=3)
    await run_until_done(s)
    assert collect.calls == 3


async def test_failing_side_jobs_do_not_stop_collection():
    s, collect, *_ = make([], backup=Job(fail=True), catch_up=Job(fail=True), max_cycles=2)
    await run_until_done(s)
    assert collect.calls == 2


async def test_jitter_is_bounded():
    s, _, _, _, _, delays = make([], max_cycles=1)
    s._rand = lambda: 1.0
    await run_until_done(s)
    assert delays[0] == pytest.approx(330)


async def test_stop_cancels_cleanly():
    gate = asyncio.Event()

    class Slow:
        async def run(self):
            await gate.wait()

    s = Scheduler(collect=Slow(), catch_up=Job(), backup=Job(), purge=Job(), interval=300)
    s.start()
    await asyncio.sleep(0)
    await s.stop()
    assert s.state.stopped_reason is None


async def test_crash_outside_try_is_logged_by_done_callback(caplog):
    s, *_ = make([], max_cycles=1)

    async def broken():
        raise RuntimeError("hors boucle")

    s._run = broken
    task = s.start()
    with pytest.raises(RuntimeError):
        await task
    await asyncio.sleep(0)
    assert s.state.stopped_reason == "crash: RuntimeError"
    assert "La boucle de collecte s'est arrêtée" in caplog.text
