from app.domain.services import ChangeDetector
from tests.builders import COUNTER, m


def test_first_measurement_is_recorded():
    d = ChangeDetector()
    assert d.filter([m(100, 53.0)]) == [m(100, 53.0)]


def test_same_provider_instant_is_never_recorded_twice():
    d = ChangeDetector()
    d.filter([m(100, 53.0, polled=100)])
    # même modificationDate, relue au poll suivant : rien à enregistrer
    assert d.filter([m(100, 53.0, polled=400)]) == []


def test_newer_provider_instant_is_recorded_even_if_value_equal():
    d = ChangeDetector()
    d.filter([m(100, 53.0)])
    assert len(d.filter([m(200, 53.0)])) == 1


def test_older_instant_is_ignored():
    d = ChangeDetector()
    d.filter([m(200, 53.0)])
    assert d.filter([m(100, 52.0)]) == []


def test_unstamped_values_recorded_only_on_change():
    d = ChangeDetector()
    d.filter([m(100, 1.0, stamped=False)])
    assert d.filter([m(400, 1.0, stamped=False)]) == []
    assert len(d.filter([m(700, 2.0, stamped=False)])) == 1


def test_series_are_independent():
    d = ChangeDetector()
    d.filter([m(100, 53.0)])
    assert len(d.filter([m(100, 190432, key=COUNTER)])) == 1


def test_reload_from_storage_prevents_duplicates_after_restart():
    stored = [m(100, 52.0), m(200, 53.0)]
    d = ChangeDetector()
    d.load(stored)
    assert d.filter([m(200, 53.0, polled=900)]) == []
    assert len(d.filter([m(300, 54.0)])) == 1
