"""API HTTP sur les doublures en mémoire (aucun réseau)."""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.inbound.http import HttpApi, mount_spa, router
from app.adapters.outbound.fake import (
    FakeMetricCatalog,
    FakeStorageStats,
    InMemoryEnergyRepository,
    InMemoryEquipmentRepository,
    InMemoryGapRepository,
    InMemoryMeasurementRepository,
    InMemoryPollLogRepository,
)
from app.adapters.outbound.system import FixedClock
from app.application.ports import MetricInfo
from app.application.usecases.queries import (
    GetEnergy,
    GetEquipment,
    GetGaps,
    GetHealth,
    GetLatest,
    GetMetrics,
    GetSeries,
)
from app.domain.model import Equipment, Gap, GapCause
from app.domain.services import GapDetector
from app.domain.values import (
    EnergyDay,
    ErrorKind,
    Instant,
    Measurement,
    MeasurementValue,
    MetricKey,
    PollOutcome,
    Tariff,
    ValueType,
)
from tests.builders import COUNTER, DHW, TEMP, m, paris

INTERVAL = 300
NOW = paris(2026, 10, 18, 12)
MODE = MetricKey("dhw_mode")


class World:
    def __init__(self) -> None:
        self.clock = FixedClock(NOW)
        self.equipment = InMemoryEquipmentRepository()
        self.measurements = InMemoryMeasurementRepository()
        self.gaps = InMemoryGapRepository()
        self.poll_log = InMemoryPollLogRepository()
        self.energy = InMemoryEnergyRepository()
        self.catalog = FakeMetricCatalog(
            [
                MetricInfo(DHW, TEMP, "Température ECS", "°C"),
                MetricInfo(DHW, COUNTER, "Énergie ECS", "Wh", cumulative=True),
                MetricInfo(DHW, MODE, "Mode", None, enum={0: "Chauffage", 1: "Veille"}),
            ]
        )
        self.state = SimpleNamespace(
            running=True, stopped_reason=None, consecutive_failures=0, next_delay_seconds=290.5
        )
        detector = GapDetector(INTERVAL)
        self.api = HttpApi(
            get_health=GetHealth(
                poll_log=self.poll_log,
                gaps=self.gaps,
                equipment=self.equipment,
                storage=FakeStorageStats(4096),
                clock=self.clock,
                gap_detector=detector,
                poll_interval=INTERVAL,
            ),
            get_equipment=GetEquipment(self.equipment),
            get_latest=GetLatest(self.measurements, self.clock),
            get_series=GetSeries(
                measurements=self.measurements,
                gaps=self.gaps,
                poll_log=self.poll_log,
                clock=self.clock,
                gap_detector=detector,
                cumulative_metrics=[COUNTER],
            ),
            get_gaps=GetGaps(self.gaps, self.poll_log, self.clock, detector),
            get_energy=GetEnergy(self.energy),
            get_metrics=GetMetrics(self.catalog),
            scheduler_state=lambda: self.state,
            clock=self.clock,
        )

    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router)
        app.state.api = self.api
        return app


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def world() -> World:
    w = World()
    run(
        w.equipment.upsert(
            [
                Equipment(
                    DHW, "Ballon ECS", "dhw", available=True, last_seen=NOW, provider_ref={"deviceId": 4242, "x": "s"}
                )
            ]
        )
    )
    return w


@pytest.fixture
def client(world: World):
    return TestClient(world.app())


def test_health_ok_even_when_stale_with_ongoing_gap(world, client):
    last = Instant(NOW.epoch - 3600)
    run(world.poll_log.add(PollOutcome.success(last, 10, 3)))
    run(world.poll_log.add(PollOutcome.failure(Instant(NOW.epoch - 600), 10, ErrorKind.UNAVAILABLE, "HTTP 503")))
    world.state.consecutive_failures = 2
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["poller"] == {
        "running": True,
        "stale": True,
        "stopped_reason": None,
        "last_success": last.epoch,
        "consecutive_failures": 2,
        "next_poll_in_seconds": 290.5,
    }
    assert body["errors"]["counts"] == {"unavailable": 1}
    assert body["errors"]["last"]["unavailable"] == {"at": NOW.epoch - 600, "message": "HTTP 503"}
    assert body["equipment"] == [{"id": "dhw_0", "available": True}]
    assert body["db_size_bytes"] == 4096
    assert [g["ongoing"] for g in body["recent_gaps"]] == [True]
    assert set(body["recent_gaps"][0]) == {"start", "end", "duration_seconds", "cause", "recovered", "ongoing"}


def test_health_without_any_poll(client):
    body = client.get("/api/health").json()
    assert body["poller"]["stale"] is True and body["poller"]["last_success"] is None


def test_equipment_with_metrics_and_no_provider_ref(client):
    r = client.get("/api/equipment")
    assert r.status_code == 200
    (eq,) = r.json()
    assert (eq["id"], eq["label"], eq["kind"], eq["available"], eq["last_seen"]) == (
        "dhw_0",
        "Ballon ECS",
        "dhw",
        True,
        NOW.epoch,
    )
    by_key = {x["key"]: x for x in eq["metrics"]}
    assert by_key["dhw_mode"]["enum"] == {"0": "Chauffage", "1": "Veille"}
    assert by_key["energy_dhw_cumulative"]["cumulative"] is True
    assert by_key["dhw_temperature"] == {
        "key": "dhw_temperature",
        "label": "Température ECS",
        "unit": "°C",
        "cumulative": False,
        "enum": {},
    }
    assert "4242" not in r.text and "provider" not in r.text and "deviceId" not in r.text


def _put(world: World, *items: Measurement) -> None:
    run(world.measurements.append(list(items)))


def _mv(key, value: MeasurementValue, t: int = NOW.epoch - 120) -> Measurement:
    return Measurement(DHW, key, Instant(t), value, "1", Instant(t + 5))


def test_latest_typing_display_and_age(world, client):
    _put(
        world,
        _mv(TEMP, MeasurementValue.of_number(51.5, "°C")),
        _mv(MODE, MeasurementValue.of_number(0)),
        _mv(MetricKey("flag"), MeasurementValue.of_bool(True)),
        _mv(MetricKey("name"), MeasurementValue.of_text("abc")),
        _mv(MetricKey("blob"), MeasurementValue.of_json({"a": [1, 2]})),
        _mv(MetricKey("nothing"), MeasurementValue.absent()),
        _mv(MetricKey("day"), MeasurementValue(ValueType.DATE, number=20000.0)),
    )
    rows = {x["metric"]: x for x in client.get("/api/latest").json()}
    assert rows["dhw_temperature"]["value"] == 51.5 and rows["dhw_temperature"]["value_type"] == "FLOAT"
    assert rows["dhw_temperature"]["unit"] == "°C" and rows["dhw_temperature"]["label"] == "Température ECS"
    assert rows["dhw_temperature"]["display"] is None
    assert rows["dhw_temperature"]["age_seconds"] == 120
    assert rows["dhw_temperature"]["at"] == NOW.epoch - 120 and rows["dhw_temperature"]["polled_at"] == NOW.epoch - 115
    assert rows["dhw_mode"]["value"] == 0 and isinstance(rows["dhw_mode"]["value"], int)
    assert rows["dhw_mode"]["display"] == "Chauffage"
    assert rows["flag"]["value"] is True
    assert rows["name"]["value"] == "abc"
    assert rows["blob"]["value"] == {"a": [1, 2]}
    assert rows["nothing"]["value"] is None
    assert rows["day"]["value"] == 20000.0
    assert rows["name"]["label"] == "name"  # repli sans catalogue


def test_latest_filter_and_bad_id(world, client):
    _put(world, _mv(TEMP, MeasurementValue.of_number(50)))
    assert len(client.get("/api/latest", params={"equipment": "dhw_0"}).json()) == 1
    assert client.get("/api/latest", params={"equipment": "other_1"}).json() == []
    assert client.get("/api/latest", params={"equipment": "Bad Id"}).status_code == 400


def test_series_defaults_and_gaps(world, client):
    _put(world, m(NOW.epoch - 3600, 50.0), m(NOW.epoch - 1800, 52.0))
    run(world.gaps.add(Gap(Instant(NOW.epoch - 7200), Instant(NOW.epoch - 6000), GapCause.DOWNTIME)))
    r = client.get("/api/series", params={"equipment": "dhw_0", "metric": "dhw_temperature"})
    assert r.status_code == 200
    body = r.json()
    assert (body["from"], body["to"], body["bucket"]) == (NOW.epoch - 86400, NOW.epoch, "5m")
    assert (body["label"], body["unit"], body["cumulative"]) == ("Température ECS", "°C", False)
    assert len(body["points"]) == 288
    assert set(body["points"][0]) == {
        "start",
        "end",
        "avg",
        "min",
        "max",
        "last",
        "samples",
        "covered_seconds",
        "delta",
        "delta_spans_gap",
    }
    assert sum(p["samples"] for p in body["points"]) == 2
    assert [(g["cause"], g["ongoing"]) for g in body["gaps"]] == [("downtime", False)]


def test_series_cumulative_flag(client):
    body = client.get("/api/series", params={"equipment": "dhw_0", "metric": "energy_dhw_cumulative"}).json()
    assert body["cumulative"] is True


@pytest.mark.parametrize(
    ("days", "expected"), [(2, "5m"), (3, "1h"), (62, "1h"), (63, "1d")], ids=["2d", "3d", "62d", "63d"]
)
def test_series_bucket_auto(client, days, expected):
    r = client.get(
        "/api/series",
        params={"equipment": "dhw_0", "metric": "dhw_temperature", "from": NOW.epoch - days * 86400, "to": NOW.epoch},
    )
    assert r.status_code == 200 and r.json()["bucket"] == expected


@pytest.mark.parametrize(
    "params",
    [
        {"bucket": "2h"},
        {"from": 100, "to": 100},
        {"from": 200, "to": 100},
        {"from": "abc"},
        {"equipment": "Bad Id"},
        {"metric": "9bad"},
        {"bucket": "5m", "from": 0, "to": 8 * 86400},
        {"bucket": "1h", "from": 0, "to": 401 * 86400},
        {"bucket": "1d", "from": 0, "to": 3661 * 86400},
    ],
)
def test_series_validation(client, params):
    q = {"equipment": "dhw_0", "metric": "dhw_temperature", **params}
    r = client.get("/api/series", params=q)
    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)


def test_series_max_range_accepted(client):
    q = {"equipment": "dhw_0", "metric": "dhw_temperature", "bucket": "5m", "from": 0, "to": 7 * 86400}
    assert client.get("/api/series", params=q).status_code == 200


def test_gaps_default_window_and_ongoing(world, client):
    run(world.gaps.add(Gap(Instant(NOW.epoch - 3 * 86400), Instant(NOW.epoch - 3 * 86400 + 900), GapCause.DOWNTIME)))
    run(world.gaps.add(Gap(Instant(NOW.epoch - 20 * 86400), Instant(NOW.epoch - 20 * 86400 + 900), GapCause.UNKNOWN)))
    run(world.poll_log.add(PollOutcome.success(Instant(NOW.epoch - 1200), 10, 1)))
    rows = client.get("/api/gaps").json()
    assert [g["ongoing"] for g in rows] == [False, True]
    assert rows[0]["duration_seconds"] == 900
    assert client.get("/api/gaps", params={"from": 5, "to": 5}).status_code == 400


def test_energy_defaults_and_validation(world, client):
    run(
        world.energy.upsert(
            [
                EnergyDay(
                    date(2026, 10, 17),
                    1,
                    Tariff.PEAK,
                    3.5,
                    0.7,
                ),
                EnergyDay(date(2026, 9, 1), 1, Tariff.OFF_PEAK, 1.0),
            ]
        )
    )
    rows = client.get("/api/energy").json()  # 2026-09-18 -> 2026-10-18 : le 1er septembre est exclu
    assert rows == [{"day": "2026-10-17", "category": 1, "tariff": "peak", "kwh": 3.5, "cost": 0.7}]
    both = client.get("/api/energy", params={"from": "2026-09-01", "to": "2026-10-18"}).json()
    assert [r["cost"] for r in both] == [None, 0.7]
    for bad in ({"from": "2026-10-18", "to": "2026-10-01"}, {"from": "nope"}, {"to": "2026-13-01"}):
        assert client.get("/api/energy", params=bad).status_code == 400
    assert client.get("/api/energy", params={"from": "2010-01-01", "to": "2026-10-18"}).status_code == 400


def test_unknown_api_path_is_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}


@pytest.fixture
def spa_client(world, tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>INDEX</html>")
    (static / "assets" / "app.js").write_text("console.log(1)")
    (static / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret").write_text("TOP SECRET")
    app = world.app()
    mount_spa(app, static)
    return TestClient(app)


def test_spa_fallback_and_assets(spa_client):
    for path in ("/", "/historique", "/a/b/c"):
        r = spa_client.get(path)
        assert r.status_code == 200 and "INDEX" in r.text
    assert spa_client.get("/assets/app.js").text == "console.log(1)"
    assert spa_client.get("/favicon.svg").text == "<svg/>"
    assert spa_client.get("/api/health").json()["status"] == "ok"


def test_spa_api_404_is_json(spa_client):
    for path in ("/api/nope", "/api"):
        r = spa_client.get(path)
        assert r.status_code == 404 and r.json() == {"detail": "Not Found"}


@pytest.mark.parametrize("path", ["/../secret", "/%2e%2e/secret", "/..%2fsecret", "/assets/../../secret"])
def test_spa_no_path_traversal(spa_client, path):
    r = spa_client.get(path)
    assert "TOP SECRET" not in r.text


def test_spa_missing_dir_does_nothing(world, tmp_path):
    app = world.app()
    mount_spa(app, tmp_path / "absent")
    c = TestClient(app)
    assert c.get("/").status_code == 404
    assert c.get("/api/health").status_code == 200
