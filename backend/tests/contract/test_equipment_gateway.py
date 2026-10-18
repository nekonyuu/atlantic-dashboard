"""Contrat du port ``EquipmentGateway`` (PLAN.md §3.5).

La même suite passe sur l'adaptateur ``fake`` et sur l'adaptateur Magellan
alimenté par la fixture enregistrée : si Magellan change, c'est ici que ça casse.
"""

import pytest

from app.adapters.outbound.fake import FakeEquipmentGateway
from app.adapters.outbound.magellan.gateway import MagellanGateway
from app.adapters.outbound.magellan.mapping import Semantics
from app.adapters.outbound.system import FixedClock
from app.domain.errors import ProviderError, ProviderUnavailable
from app.domain.model import Equipment
from app.domain.values import EquipmentId, Instant
from tests import magellan_fixture as fx
from tests.builders import m

NOW = Instant(fx.fixture()["setupview_1"]["at"])


def make_fake():
    eq = [
        Equipment(EquipmentId("dhw"), "Ballon ECS", "dhw", available=True),
        Equipment(EquipmentId("room_1"), "Pièce 1", "room", available=True),
    ]
    gw = FakeEquipmentGateway(eq, [m(NOW.epoch - 60, 53.0, eq=EquipmentId("dhw"), polled=NOW)])
    return gw, lambda exc: setattr(gw, "fail_with", exc)


def make_magellan():
    client = fx.FixtureClient()
    gw = MagellanGateway(client, Semantics.load(), FixedClock(NOW))
    return gw, lambda exc: setattr(client, "fail_with", exc)


@pytest.fixture(params=["fake", "magellan"])
def gateway(request):
    return {"fake": make_fake, "magellan": make_magellan}[request.param]()


async def test_lists_equipment_with_unique_safe_ids(gateway):
    gw, _ = gateway
    eqs = await gw.list_equipment()
    assert eqs and len({e.id for e in eqs}) == len(eqs)
    for e in eqs:
        assert e.label and e.kind
        assert "://" not in e.id.value


async def test_measurements_belong_to_listed_equipment(gateway):
    gw, _ = gateway
    ids = {e.id for e in await gw.list_equipment()}
    ms = await gw.read_measurements()
    assert ms
    for x in ms:
        assert x.equipment_id in ids
        assert x.instant <= x.polled_at
        assert x.value is not None


async def test_measurements_can_be_filtered(gateway):
    gw, _ = gateway
    ms = await gw.read_measurements([EquipmentId("dhw")])
    assert ms and {x.equipment_id for x in ms} == {EquipmentId("dhw")}


async def test_availability_covers_known_equipment(gateway):
    gw, _ = gateway
    ids = {e.id for e in await gw.list_equipment()}
    av = await gw.availability()
    assert set(av) <= ids and all(isinstance(v, bool) for v in av.values())


async def test_failures_surface_as_domain_errors(gateway):
    gw, fail = gateway
    fail(ProviderUnavailable("down"))
    with pytest.raises(ProviderError):
        await gw.list_equipment()


async def test_magellan_reads_setup_once_per_cycle():
    gw, _ = make_magellan()
    await gw.list_equipment()
    await gw.read_measurements()
    await gw.availability()
    assert gw._client.calls.count("setup") == 1


async def test_magellan_catalogue_cached_through_store():
    class Store:
        def __init__(self):
            self.saved = None

        async def load(self):
            return self.saved

        async def save(self, entries, fetched_at):
            self.saved = entries

    store = Store()
    client = fx.FixtureClient()
    gw = MagellanGateway(client, Semantics.load(), FixedClock(NOW), store)
    await gw.read_measurements()
    assert store.saved and client.calls.count("catalogue") == 1
    # redémarrage : le catalogue vient du cache, pas du fournisseur
    client2 = fx.FixtureClient()
    gw2 = MagellanGateway(client2, Semantics.load(), FixedClock(NOW), store)
    await gw2.read_measurements()
    assert client2.calls.count("catalogue") == 0


async def test_magellan_history_source_reads_daily_energy():
    from datetime import date

    from app.adapters.outbound.magellan.gateway import MagellanHistorySource

    gw, _ = make_magellan()
    hist = MagellanHistorySource(gw._client, gw)
    assert hist.capabilities().energy_daily
    days = await hist.fetch_energy_days(date(2026, 10, 1), date(2026, 10, 18))
    assert days and all(date(2026, 10, 1) <= d.day <= date(2026, 10, 18) for d in days)
