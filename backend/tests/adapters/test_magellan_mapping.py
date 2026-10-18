from datetime import date

import pytest

from app.adapters.outbound.magellan.mapping import (
    Catalogue,
    Semantics,
    energy_days_of,
    measurements_of,
    parse_value,
    resolve_equipment,
)
from app.domain.values import EquipmentId, Instant, MetricKey, Tariff, ValueType
from tests import magellan_fixture as fx

SEM = Semantics.load()
CAT = Catalogue(fx.catalogue())
NOW = Instant(fx.fixture()["setupview_1"]["at"])


def resolved():
    return {r.equipment.id: r for r in resolve_equipment(fx.setup_view()["devices"], SEM)}


def test_semantics_file_is_valid():
    ids = [s.id for s in SEM.equipment]
    assert len(ids) == len(set(ids))
    assert SEM.cumulative_metrics() == {MetricKey("energy_heating_cumulative"), MetricKey("energy_dhw_cumulative")}


def test_all_five_devices_are_recognised_by_product_id():
    r = resolved()
    assert set(r) == {EquipmentId(x) for x in ("heat_pump", "generator", "dhw", "circuit_1", "room_1")}
    assert r[EquipmentId("dhw")].equipment.kind == "dhw"
    assert r[EquipmentId("dhw")].equipment.available is True
    # le libellé vient de semantics.yaml, jamais du nom personnalisable chez le fournisseur
    assert r[EquipmentId("dhw")].equipment.label == "Ballon ECS"


def test_every_semantic_capability_exists_in_the_dump_and_catalogue():
    r = resolved()
    for spec in SEM.equipment:
        eq = next(x for x in r.values() if x.spec is spec)
        for metric in spec.metrics:
            assert metric.capability in eq.capabilities, (spec.id, metric.key)
            assert CAT.get(metric.capability) is not None, metric.capability


def test_measurements_are_typed_and_stamped_by_provider():
    ms = {
        (m.equipment_id.value, m.metric_key.value): m for r in resolved().values() for m in measurements_of(r, CAT, NOW)
    }
    t = ms[("dhw", "dhw_temperature")]
    assert t.value.type is ValueType.FLOAT and t.value.number == pytest.approx(53.17) and t.value.unit == "°C"
    assert t.provider_timestamped and t.instant < NOW and t.polled_at == NOW and t.source == "111"
    assert ms[("heat_pump", "generator_status")].value.type is ValueType.INTEGER
    assert ms[("dhw", "dhw_on")].value.type is ValueType.BOOLEAN
    assert ms[("heat_pump", "energy_dhw_cumulative")].value.unit == "Wh"  # correction du catalogue
    assert ms[("room_1", "room_temperature")].value.number == pytest.approx(20.69)


def test_unknown_product_ids_are_ignored():
    devices = fx.setup_view()["devices"]
    devices.append({**devices[0], "productId": 9999, "deviceId": 1})
    assert len(resolve_equipment(devices, SEM)) == 5


def test_missing_or_future_modification_date_falls_back_to_poll_time():
    setup = fx.setup_view()
    for d in setup["devices"]:
        for c in d["capabilities"]:
            c.pop("modificationDate", None)
    ms = [m for r in resolve_equipment(setup["devices"], SEM) for m in measurements_of(r, CAT, NOW)]
    assert ms and all(m.instant == NOW and not m.provider_timestamped for m in ms)


@pytest.mark.parametrize(
    ("raw", "cat_type", "expected"),
    [
        ("53.17", 2, ValueType.FLOAT),
        ("3000", 1, ValueType.INTEGER),
        ("10.000000000", 1, ValueType.INTEGER),
        ("1", 4, ValueType.BOOLEAN),
        ("Heat", 3, ValueType.STRING),
        ('{"a": 1}', 7, ValueType.JSON),
        (None, 2, ValueType.NULL),
    ],
)
def test_parse_value(raw, cat_type, expected):
    from app.adapters.outbound.magellan.mapping import CapabilityInfo

    assert parse_value(raw, CapabilityInfo(1, "x", cat_type, None), None).type is expected


def test_unparseable_values_are_rejected_not_raised():
    from app.adapters.outbound.magellan.mapping import CapabilityInfo

    assert parse_value("abc", CapabilityInfo(1, "x", 2, None), None) is None
    assert parse_value("2", CapabilityInfo(1, "x", 4, None), None) is None


def test_energy_days_from_fixture():
    days = energy_days_of(fx.consumptions())
    assert {d.category for d in days} == {1, 2}
    assert {d.tariff for d in days} <= {Tariff.PEAK, Tariff.OFF_PEAK}
    assert min(d.day for d in days) == date(2026, 9, 17) and max(d.day for d in days) == date(2026, 10, 18)
    total_cat1 = sum(d.kwh for d in days if d.category == 1)
    assert total_cat1 == pytest.approx(71.66, abs=0.01)


def test_energy_days_ignore_other_series_and_bad_periods():
    series = [
        {"type": 4, "unit": 2, "category": 2, "consumptionPeriods": [{"date": 0, "consumedQuantity": 90, "mode": 0}]},
        {
            "type": 1,
            "unit": 1,
            "category": 1,
            "consumptionPeriods": [{"date": "x"}, {"date": 86400, "consumedQuantity": -1}],
        },
    ]
    assert energy_days_of(series) == []
