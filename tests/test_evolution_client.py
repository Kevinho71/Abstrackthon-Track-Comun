import json

import httpx
import pytest

from app.channels.evolution import EvolutionClient, EvolutionError


def make(handler):
    return EvolutionClient("http://evo:8080", "clave", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_create_instance_envia_clave_y_webhook():
    seen = {}

    def handler(request: httpx.Request):
        seen["apikey"] = request.headers["apikey"]
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"instance": {"instanceName": "x"}})

    await make(handler).create_instance("x", "http://app/webhook/evolution", number="59170000001", token="t")
    assert seen["apikey"] == "clave" and seen["path"] == "/instance/create"
    assert seen["body"]["instanceName"] == "x" and seen["body"]["number"] == "59170000001"
    assert seen["body"]["webhook"]["url"] == "http://app/webhook/evolution"
    assert seen["body"]["webhook"]["headers"]["x-webhook-token"] == "t"
    assert "MESSAGES_UPSERT" in seen["body"]["webhook"]["events"]


@pytest.mark.asyncio
async def test_state_y_connect():
    def handler(request: httpx.Request):
        if request.url.path.startswith("/instance/connectionState/"):
            return httpx.Response(200, json={"instance": {"instanceName": "x", "state": "open"}})
        return httpx.Response(200, json={"pairingCode": "ABCD1234", "code": "2@...", "count": 1})

    client = make(handler)
    assert await client.state("x") == "open"
    data = await client.connect("x", number="59170000001")
    assert data["pairingCode"] == "ABCD1234"


@pytest.mark.asyncio
async def test_error_http_se_convierte_en_evolution_error():
    client = make(lambda request: httpx.Response(401, json={"error": "Unauthorized"}))
    with pytest.raises(EvolutionError):
        await client.state("x")
