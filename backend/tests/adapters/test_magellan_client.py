"""Client HTTP contre un faux serveur Magellan local (aucun appel réseau réel)."""

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.adapters.outbound.magellan.client import MagellanClient
from app.domain.errors import CredentialsRejected, ProviderThrottled, ProviderUnavailable
from tests import magellan_fixture as fx


class Fake:
    def __init__(self):
        self.token_status = 200
        self.token_body = {"access_token": "t1", "token_type": "bearer", "expires_in": 28800}
        self.setup_status = 200
        self.headers = {}
        self.unauthorized_once = False
        self.token_calls = 0
        self.seen_auth = []
        self.form = None

    def app(self):
        app = web.Application()
        app.router.add_post("/users/token", self.token)
        app.router.add_get("/magellan/cozytouch/setupviewv2", self.setup)
        app.router.add_get("/magellan/productmodels/capabilities", self.catalogue)
        app.router.add_get("/magellan/setups/{sid}/consumptions", self.consumptions)
        return app

    async def token(self, request):
        self.token_calls += 1
        self.form = await request.post()
        return web.json_response(self.token_body, status=self.token_status, headers=self.headers)

    async def setup(self, request):
        self.seen_auth.append(request.headers.get("Authorization"))
        if self.unauthorized_once:
            self.unauthorized_once = False
            return web.json_response({}, status=401)
        return web.json_response([fx.setup_view()], status=self.setup_status, headers=self.headers)

    async def catalogue(self, request):
        return web.json_response(fx.catalogue())

    async def consumptions(self, request):
        assert request.query["periodicity"] == "daily"
        return web.json_response(fx.consumptions())


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
async def env():
    fake = Fake()
    server = TestServer(fake.app())
    await server.start_server()
    clock = Clock()
    async with aiohttp.ClientSession() as session:
        client = MagellanClient(
            session, "user@example.invalid", "secret", base_url=str(server.make_url("")), monotonic=clock
        )
        yield fake, client, clock
    await server.close()


async def test_login_then_reads_with_bearer_token(env):
    fake, client, _ = env
    setup = await client.setup_view()
    assert len(setup["devices"]) == 5
    assert fake.form["username"] == "GA-PRIVATEPERSON/user@example.invalid"
    assert fake.form["grant_type"] == "password"
    assert fake.seen_auth == ["Bearer t1"]
    assert len(await client.capability_catalogue()) > 100
    assert len(await client.daily_consumptions(1000)) == 2


async def test_token_is_reused_until_expiry(env):
    fake, client, clock = env
    await client.setup_view()
    await client.setup_view()
    assert fake.token_calls == 1
    clock.t = 28800 - 59
    await client.setup_view()
    assert fake.token_calls == 2


async def test_401_renews_token_once(env):
    fake, client, _ = env
    await client.setup_view()
    fake.unauthorized_once = True
    await client.setup_view()
    assert fake.token_calls == 2


async def test_invalid_grant_is_credentials_rejected(env):
    fake, client, _ = env
    fake.token_status, fake.token_body = 400, {"error": "invalid_grant", "error_description": "Bad credentials"}
    with pytest.raises(CredentialsRejected) as exc:
        await client.setup_view()
    assert "secret" not in str(exc.value) and "user@" not in str(exc.value)


async def test_429_is_throttled_with_retry_after(env):
    fake, client, _ = env
    await client.setup_view()
    fake.setup_status, fake.headers = 429, {"Retry-After": "120"}
    with pytest.raises(ProviderThrottled) as exc:
        await client.setup_view()
    assert exc.value.retry_after == 120


async def test_429_without_header_defaults_to_300(env):
    fake, client, _ = env
    fake.token_status = 429
    with pytest.raises(ProviderThrottled) as exc:
        await client.setup_view()
    assert exc.value.retry_after == 300


async def test_server_errors_are_unavailable(env):
    fake, client, _ = env
    fake.setup_status = 503
    with pytest.raises(ProviderUnavailable):
        await client.setup_view()


async def test_connection_refused_is_unavailable():
    async with aiohttp.ClientSession() as session:
        client = MagellanClient(session, "u", "p", base_url="http://127.0.0.1:9")
        with pytest.raises(ProviderUnavailable):
            await client.setup_view()
