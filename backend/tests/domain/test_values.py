import pytest

from app.domain.model import Equipment, Gap, GapCause, Installation
from app.domain.values import (
    EnergyDay,
    EquipmentId,
    ErrorKind,
    Instant,
    MeasurementValue,
    MetricKey,
    PollOutcome,
    Tariff,
    ValueType,
)


def test_identifiers_are_validated():
    assert str(EquipmentId("dhw_0")) == "dhw_0"
    with pytest.raises(ValueError):
        EquipmentId("modbuslink://1234/1")
    with pytest.raises(ValueError):
        MetricKey("DHW Temperature")


def test_instant_rejects_non_integers():
    with pytest.raises(TypeError):
        Instant(1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Instant(True)  # type: ignore[arg-type]
    assert Instant(10) + 5 == Instant(15)
    assert Instant(15) - Instant(10) == 5


def test_measurement_value_types():
    assert MeasurementValue.of_number(3).type is ValueType.INTEGER
    assert MeasurementValue.of_number(3.5).type is ValueType.FLOAT
    assert MeasurementValue.of_bool(True).number == 1.0
    assert MeasurementValue.of_json({"b": 1, "a": 2}).text == '{"a": 2, "b": 1}'
    absent = MeasurementValue.absent()
    assert absent.type is ValueType.NULL and not absent.is_numeric
    with pytest.raises(ValueError):
        MeasurementValue(ValueType.FLOAT)
    with pytest.raises(ValueError):
        MeasurementValue(ValueType.NULL, number=1.0)


def test_same_reading_ignores_unit():
    assert MeasurementValue.of_number(53.17, "°C").same_reading(MeasurementValue.of_number(53.17))
    assert not MeasurementValue.of_number(53.17).same_reading(MeasurementValue.of_number(53.2))


def test_poll_outcome_consistency():
    ok = PollOutcome.success(Instant(0), 12, recorded=3)
    assert ok.ok and ok.error_kind is None
    ko = PollOutcome.failure(Instant(0), 12, ErrorKind.THROTTLED, "429")
    assert not ko.ok
    with pytest.raises(ValueError):
        PollOutcome(at=Instant(0), ok=False, duration_ms=0)


def test_energy_day_rejects_negative():
    from datetime import date

    with pytest.raises(ValueError):
        EnergyDay(date(2026, 10, 1), 1, Tariff.PEAK, -1.0)


def test_gap_must_have_positive_duration():
    with pytest.raises(ValueError):
        Gap(Instant(10), Instant(10), GapCause.DOWNTIME)
    g = Gap(Instant(10), Instant(20), GapCause.DOWNTIME)
    assert g.overlaps(Instant(15), Instant(30))
    assert not g.overlaps(Instant(20), Instant(30))


def test_installation_tracks_availability():
    inst = Installation()
    e = inst.observe(Equipment(EquipmentId("dhw_0"), "Ballon", "dhw", available=True), Instant(100))
    assert e.first_seen == Instant(100)
    inst.observe(Equipment(EquipmentId("dhw_0"), "Ballon", "dhw", available=False), Instant(200))
    assert inst.equipment[EquipmentId("dhw_0")].first_seen == Instant(100)
    assert inst.unavailable() == [EquipmentId("dhw_0")]
