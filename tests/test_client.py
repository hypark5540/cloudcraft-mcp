"""Unit tests for CloudcraftClient.

Uses respx to mock httpx — no real network calls, no API key needed.
"""
from __future__ import annotations

import gzip
import json

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
def test_client_rejects_insecure_base_url() -> None:
    with pytest.raises(ValueError, match="must use https"):
        CloudcraftClient(api_key="test-key", base_url="http://api.example.com")


@pytest.mark.unit
def test_cloudcraft_error_string_omits_untrusted_body() -> None:
    secret = "Bearer should-not-appear"
    exc = CloudcraftError(status=401, body=secret, method="GET", url="https://x")
    assert secret not in str(exc)
    assert exc.body == secret


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
    with pytest.raises(CloudcraftError) as exc_info:
        await client.whoami()
    assert exc_info.value.body == "invalid JSON body"


@pytest.mark.unit
@respx.mock
async def test_request_json_rejects_non_object(client: CloudcraftClient) -> None:
    """Upstream returning a JSON array (not an object) must be rejected."""
    respx.get("https://api.cloudcraft.co/user/me").mock(
        return_value=httpx.Response(200, json=["not", "a", "dict"])
    )
    with pytest.raises(CloudcraftError) as exc_info:
        await client.whoami()
    assert "expected JSON object" in exc_info.value.body


@pytest.mark.unit
@respx.mock
async def test_response_size_is_bounded() -> None:
    client = CloudcraftClient(api_key="test-key", max_response_bytes=4)
    respx.get("https://api.cloudcraft.co/user/me").mock(
        return_value=httpx.Response(200, content=b"12345")
    )

    with pytest.raises(CloudcraftError) as exc_info:
        await client.whoami()

    assert exc_info.value.status == 502
    assert "4-byte limit" in exc_info.value.body


@pytest.mark.unit
@respx.mock
async def test_transport_error_does_not_expose_request_details(
    client: CloudcraftClient,
) -> None:
    request = httpx.Request(
        "GET",
        "https://api.cloudcraft.co/user/me",
        headers={"Authorization": "Bearer do-not-leak"},
    )
    respx.get("https://api.cloudcraft.co/user/me").mock(
        side_effect=httpx.ConnectError("connection failed", request=request)
    )

    with pytest.raises(CloudcraftError) as exc_info:
        await client.whoami()

    assert exc_info.value.status == 502
    assert exc_info.value.body == "Cloudcraft transport failed (ConnectError)"
    assert "do-not-leak" not in str(exc_info.value)


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


# ---- regressions for GitHub issues #20 / #21 ---------------------------------


@pytest.mark.unit
@respx.mock
async def test_gzip_response_is_decoded_only_once(client: CloudcraftClient) -> None:
    """Issue #20: the buffered copy must not re-run the Content-Encoding decoder."""
    body = gzip.compress(json.dumps({"ok": True}).encode())
    respx.get("https://api.cloudcraft.co/user/me").mock(
        return_value=httpx.Response(
            200,
            content=body,
            headers={
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
                "Content-Length": str(len(body)),
            },
        )
    )
    assert await client.whoami() == {"ok": True}


@pytest.mark.unit
@respx.mock
async def test_update_blueprint_accepts_204_no_content(client: CloudcraftClient) -> None:
    """Issue #21: Cloudcraft answers a successful PUT with 204 and an empty body."""
    respx.put(f"https://api.cloudcraft.co/blueprint/{GOOD_UUID}").mock(
        return_value=httpx.Response(204)
    )
    assert await client.update_blueprint(GOOD_UUID, {"nodes": []}) == {
        "id": GOOD_UUID,
        "updated": True,
    }


@pytest.mark.unit
@respx.mock
async def test_rate_limit_error_surfaces_retry_after(client: CloudcraftClient) -> None:
    respx.get("https://api.cloudcraft.co/user/me").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "7"})
    )
    with pytest.raises(CloudcraftError) as exc_info:
        await client.whoami()
    assert exc_info.value.status == 429
    assert "7" in exc_info.value.body


# ---- endpoint paths verified against docs.datadoghq.com/cloudcraft/api -------


@pytest.mark.unit
@respx.mock
async def test_export_blueprint_mxgraph_uses_api_spelling(client: CloudcraftClient) -> None:
    route = respx.get(f"https://api.cloudcraft.co/blueprint/{GOOD_UUID}/mxGraph").mock(
        return_value=httpx.Response(200, content=b"<mxGraphModel/>")
    )
    assert await client.export_blueprint(GOOD_UUID, "mxgraph") == b"<mxGraphModel/>"
    assert route.called


@pytest.mark.unit
@respx.mock
async def test_snapshot_aws_uses_documented_path_and_params(client: CloudcraftClient) -> None:
    route = respx.get(
        f"https://api.cloudcraft.co/aws/account/{GOOD_UUID}/ap-northeast-2/json"
    ).mock(return_value=httpx.Response(200, json={"nodes": []}))
    result = await client.snapshot_aws(
        GOOD_UUID, "ap-northeast-2", filter="env=dev", exclude=["ec2", "sg"]
    )
    assert result == {"nodes": []}
    params = route.calls.last.request.url.params
    assert params["filter"] == "env=dev"
    assert params["exclude"] == "ec2,sg"


@pytest.mark.unit
async def test_snapshot_aws_rejects_bad_exclude_entry(client: CloudcraftClient) -> None:
    with pytest.raises(ValueError, match="service must be"):
        await client.snapshot_aws(GOOD_UUID, "us-east-1", exclude=["../etc"])


@pytest.mark.unit
@respx.mock
async def test_snapshot_azure_uses_documented_path(client: CloudcraftClient) -> None:
    respx.get(f"https://api.cloudcraft.co/azure/account/{GOOD_UUID}/eastus/json").mock(
        return_value=httpx.Response(200, json={"nodes": []})
    )
    assert await client.snapshot_azure(GOOD_UUID, "eastus") == {"nodes": []}


@pytest.mark.unit
async def test_snapshot_azure_rejects_bad_region(client: CloudcraftClient) -> None:
    with pytest.raises(ValueError, match="region"):
        await client.snapshot_azure(GOOD_UUID, "East US")


@pytest.mark.unit
@respx.mock
async def test_export_blueprint_budget(client: CloudcraftClient) -> None:
    route = respx.get(f"https://api.cloudcraft.co/blueprint/{GOOD_UUID}/budget/csv").mock(
        return_value=httpx.Response(200, content=b"service,cost\n")
    )
    content = await client.export_blueprint_budget(
        GOOD_UUID, "csv", currency="EUR", period="y", rate="stated"
    )
    assert content == b"service,cost\n"
    params = route.calls.last.request.url.params
    assert (params["currency"], params["period"], params["rate"]) == ("EUR", "y", "stated")


@pytest.mark.unit
async def test_export_blueprint_budget_rejects_bad_format(client: CloudcraftClient) -> None:
    with pytest.raises(ValueError, match="unsupported format"):
        await client.export_blueprint_budget(GOOD_UUID, "pdf")


@pytest.mark.unit
@respx.mock
async def test_list_teams_wraps_bare_array(client: CloudcraftClient) -> None:
    respx.get("https://api.cloudcraft.co/team").mock(
        return_value=httpx.Response(200, json=[{"id": "t1"}])
    )
    assert await client.list_teams() == {"teams": [{"id": "t1"}]}


@pytest.mark.unit
@respx.mock
async def test_list_azure_accounts(client: CloudcraftClient) -> None:
    respx.get("https://api.cloudcraft.co/azure/account").mock(
        return_value=httpx.Response(200, json={"accounts": []})
    )
    assert await client.list_azure_accounts() == {"accounts": []}
