"""Unit tests for CloudcraftClient.

Uses respx to mock httpx — no real network calls, no API key needed.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from cloudcraft_mcp.client import CloudcraftClient, CloudcraftError


@pytest.fixture
def client() -> CloudcraftClient:
    return CloudcraftClient(api_key="test-key", base_url="https://api.cloudcraft.co")


def test_init_requires_api_key() -> None:
    with pytest.raises(ValueError, match="api_key is required"):
        CloudcraftClient(api_key="")


@pytest.mark.unit
@respx.mock
async def test_whoami_bearer_auth(client: CloudcraftClient) -> None:
    route = respx.get("https://api.cloudcraft.co/user/me").mock(
        return_value=httpx.Response(200, json={"id": "u1", "name": "tester"})
    )
    result = await client.whoami()

    assert route.called
    assert route.calls.last.request.headers["authorization"] == "Bearer test-key"
    assert result == {"id": "u1", "name": "tester"}


@pytest.mark.unit
@respx.mock
async def test_list_blueprints(client: CloudcraftClient) -> None:
    respx.get("https://api.cloudcraft.co/blueprint").mock(
        return_value=httpx.Response(200, json={"blueprints": []})
    )
    assert await client.list_blueprints() == {"blueprints": []}


@pytest.mark.unit
@respx.mock
async def test_create_blueprint_wraps_in_data_envelope(client: CloudcraftClient) -> None:
    route = respx.post("https://api.cloudcraft.co/blueprint").mock(
        return_value=httpx.Response(200, json={"id": "bp1"})
    )
    data = {"name": "x", "nodes": [], "edges": []}
    await client.create_blueprint(data)

    assert route.called
    assert route.calls.last.request.content == b'{"data":{"name":"x","nodes":[],"edges":[]}}'


@pytest.mark.unit
@respx.mock
async def test_delete_blueprint(client: CloudcraftClient) -> None:
    route = respx.delete("https://api.cloudcraft.co/blueprint/abc").mock(
        return_value=httpx.Response(204)
    )
    await client.delete_blueprint("abc")
    assert route.called


@pytest.mark.unit
@respx.mock
async def test_error_response_raises_cloudcraft_error(client: CloudcraftClient) -> None:
    respx.get("https://api.cloudcraft.co/user/me").mock(
        return_value=httpx.Response(401, text='{"error":"unauthorized"}')
    )
    with pytest.raises(CloudcraftError) as exc_info:
        await client.whoami()
    assert exc_info.value.status == 401
    assert "unauthorized" in exc_info.value.body


@pytest.mark.unit
@respx.mock
async def test_export_blueprint_rejects_bad_format(client: CloudcraftClient) -> None:
    with pytest.raises(ValueError, match="unsupported format"):
        await client.export_blueprint("bp1", "jpg")


@pytest.mark.unit
@respx.mock
async def test_export_blueprint_returns_binary(client: CloudcraftClient) -> None:
    respx.get("https://api.cloudcraft.co/blueprint/bp1/png").mock(
        return_value=httpx.Response(200, content=b"\x89PNG...")
    )
    content = await client.export_blueprint("bp1", "png")
    assert content.startswith(b"\x89PNG")
