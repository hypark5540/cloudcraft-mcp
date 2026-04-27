"""Unit tests for CloudcraftClient.

Uses respx to mock httpx — no real network calls, no API key needed.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from cloudcraft_mcp.client import CloudcraftClient, CloudcraftError

# Real UUID used across client tests — satisfies the 0.1.3 path-segment
# validator on blueprint_id / account_id URL segments.
GOOD_UUID = "4e759c63-1f2b-4663-a54c-0122e11a5386"


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
    route = respx.delete(f"https://api.cloudcraft.co/blueprint/{GOOD_UUID}").mock(
        return_value=httpx.Response(204)
    )
    await client.delete_blueprint(GOOD_UUID)
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
    # Bad format must fail BEFORE UUID validation so the caller sees the
    # more actionable error message.
    with pytest.raises(ValueError, match="unsupported format"):
        await client.export_blueprint(GOOD_UUID, "jpg")


@pytest.mark.unit
@respx.mock
async def test_export_blueprint_returns_binary(client: CloudcraftClient) -> None:
    respx.get(f"https://api.cloudcraft.co/blueprint/{GOOD_UUID}/png").mock(
        return_value=httpx.Response(200, content=b"\x89PNG...")
    )
    content = await client.export_blueprint(GOOD_UUID, "png")
    assert content.startswith(b"\x89PNG")


@pytest.mark.unit
@respx.mock
async def test_export_blueprint_passes_optional_params(client: CloudcraftClient) -> None:
    """scale + transparent should reach the wire as query params."""
    route = respx.get(f"https://api.cloudcraft.co/blueprint/{GOOD_UUID}/png").mock(
        return_value=httpx.Response(200, content=b"\x89PNG")
    )
    await client.export_blueprint(GOOD_UUID, "png", scale=2.0, transparent=True)
    assert route.called
    req = route.calls.last.request
    assert req.url.params["scale"] == "2.0"
    assert req.url.params["transparent"] == "true"


@pytest.mark.unit
@respx.mock
async def test_request_json_rejects_invalid_json(client: CloudcraftClient) -> None:
    """Upstream 200 with non-JSON body must be surfaced as CloudcraftError."""
    respx.get("https://api.cloudcraft.co/user/me").mock(
        return_value=httpx.Response(200, text="not-json-at-all")
    )
    with pytest.raises(CloudcraftError, match="invalid JSON"):
        await client.whoami()


@pytest.mark.unit
@respx.mock
async def test_request_json_rejects_non_object(client: CloudcraftClient) -> None:
    """Upstream returning a JSON array (not an object) must be rejected."""
    respx.get("https://api.cloudcraft.co/user/me").mock(
        return_value=httpx.Response(200, json=["not", "a", "dict"])
    )
    with pytest.raises(CloudcraftError, match="expected JSON object"):
        await client.whoami()


@pytest.mark.unit
@respx.mock
async def test_get_blueprint_happy_path(client: CloudcraftClient) -> None:
    respx.get(f"https://api.cloudcraft.co/blueprint/{GOOD_UUID}").mock(
        return_value=httpx.Response(200, json={"id": GOOD_UUID, "name": "x"})
    )
    result = await client.get_blueprint(GOOD_UUID)
    assert result["id"] == GOOD_UUID


@pytest.mark.unit
@respx.mock
async def test_update_blueprint_wraps_in_data_envelope(client: CloudcraftClient) -> None:
    route = respx.put(f"https://api.cloudcraft.co/blueprint/{GOOD_UUID}").mock(
        return_value=httpx.Response(200, json={"id": GOOD_UUID})
    )
    await client.update_blueprint(GOOD_UUID, {"nodes": []})
    assert route.called
    assert route.calls.last.request.content == b'{"data":{"nodes":[]}}'


@pytest.mark.unit
@respx.mock
async def test_list_aws_accounts(client: CloudcraftClient) -> None:
    respx.get("https://api.cloudcraft.co/aws/account").mock(
        return_value=httpx.Response(200, json={"accounts": []})
    )
    assert await client.list_aws_accounts() == {"accounts": []}
