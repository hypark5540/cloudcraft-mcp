"""Security regression tests for 0.1.3 hardening.

Covers the four fixes landed in ``## [0.1.3]`` of CHANGELOG.md:

1. Path-traversal whitelist in ``export_blueprint_image``.
2. UUID / region / service validation on URL-building client methods.
3. Error-body truncation and Bearer-token redaction in ``_format_error``.
4. HTTPS enforcement on ``CLOUDCRAFT_BASE_URL``.
"""
from __future__ import annotations

import importlib
import tempfile
from pathlib import Path

import httpx
import pytest
import respx

from cloudcraft_mcp.client import (
    CloudcraftClient,
    CloudcraftError,
    _validate_region,
    _validate_service,
    _validate_uuid,
)

GOOD_UUID = "4e759c63-1f2b-4663-a54c-0122e11a5386"


# ---- Fix #2: input validation on URL-building client methods ----------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not-a-uuid",
        "../user/me",
        "abc?admin=true",
        "4e759c63-1f2b-4663-a54c-0122e11a5386/../../user/me",
        "4e759c63_1f2b_4663_a54c_0122e11a5386",  # underscores not hyphens
        "4e759c63-1f2b-4663-a54c-0122e11a5386xx",  # trailing junk
    ],
)
def test_validate_uuid_rejects_bad_inputs(bad: str) -> None:
    with pytest.raises(ValueError, match="must be a UUID"):
        _validate_uuid("blueprint_id", bad)


@pytest.mark.unit
def test_validate_uuid_accepts_good() -> None:
    assert _validate_uuid("blueprint_id", GOOD_UUID) == GOOD_UUID
    # case-insensitive hex is fine
    upper = GOOD_UUID.upper()
    assert _validate_uuid("blueprint_id", upper) == upper


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad",
    ["", "ap-northeast", "AP-NORTHEAST-2", "ap_northeast_2", "../ec2", "us-east-1a"],
)
def test_validate_region_rejects_bad(bad: str) -> None:
    with pytest.raises(ValueError, match="region must look like"):
        _validate_region(bad)


@pytest.mark.unit
@pytest.mark.parametrize(
    "good",
    ["ap-northeast-2", "us-east-1", "eu-west-3", "us-gov-west-1", "cn-north-1"],
)
def test_validate_region_accepts_aws_regions(good: str) -> None:
    assert _validate_region(good) == good


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad",
    ["", "EC2", "../etc/passwd", "ec2?x=1", "1ec2", "-ec2", "ec 2"],
)
def test_validate_service_rejects_bad(bad: str) -> None:
    with pytest.raises(ValueError, match="service must be"):
        _validate_service(bad)


@pytest.mark.unit
@pytest.mark.parametrize("good", ["ec2", "s3", "rds", "lambda", "vpc", "elb-v2"])
def test_validate_service_accepts_slugs(good: str) -> None:
    assert _validate_service(good) == good


@pytest.mark.unit
async def test_get_blueprint_rejects_traversal() -> None:
    client = CloudcraftClient(api_key="test-key")
    with pytest.raises(ValueError):
        await client.get_blueprint("../user/me")


@pytest.mark.unit
async def test_snapshot_aws_rejects_bad_region() -> None:
    client = CloudcraftClient(api_key="test-key")
    with pytest.raises(ValueError):
        await client.snapshot_aws(GOOD_UUID, "AP-NORTHEAST-2", "ec2")


@pytest.mark.unit
@respx.mock
async def test_valid_inputs_reach_the_network() -> None:
    """Sanity: good UUID/region/service actually dispatches a request."""
    client = CloudcraftClient(api_key="test-key")
    route = respx.get(
        f"https://api.cloudcraft.co/aws/account/{GOOD_UUID}/snapshot/ap-northeast-2/ec2"
    ).mock(return_value=httpx.Response(200, json={"ok": True}))
    assert await client.snapshot_aws(GOOD_UUID, "ap-northeast-2", "ec2") == {"ok": True}
    assert route.called


# ---- Fix #3: error-body truncation + Bearer redaction -----------------------


@pytest.mark.unit
def test_format_error_truncates_long_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDCRAFT_API_KEY", "test-key-for-startup")
    import cloudcraft_mcp.server as server_module

    server_module = importlib.reload(server_module)

    long_body = "x" * 2000
    exc = CloudcraftError(
        status=500, body=long_body, method="GET", url="https://api.cloudcraft.co/x"
    )
    msg = server_module._format_error(exc)
    assert "[truncated]" in msg
    assert len(msg) < 700  # header + 500-char cap + suffix


@pytest.mark.unit
def test_format_error_redacts_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDCRAFT_API_KEY", "test-key-for-startup")
    import cloudcraft_mcp.server as server_module

    server_module = importlib.reload(server_module)

    # Use a deliberately non-Stripe-looking token here — GitHub's push
    # protection flags ``sk_live_…`` even in test fixtures, so we use a
    # neutral hex blob that still exercises the Bearer-redaction regex.
    fake_token = "deadbeefCAFEBABE1234567890xyz0123456789"
    body = f'echo: {{"Authorization": "Bearer {fake_token}"}}'
    exc = CloudcraftError(status=401, body=body, method="GET", url="x")
    msg = server_module._format_error(exc)
    assert fake_token not in msg
    assert "Bearer ***" in msg


@pytest.mark.unit
def test_format_error_preserves_short_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDCRAFT_API_KEY", "test-key-for-startup")
    import cloudcraft_mcp.server as server_module

    server_module = importlib.reload(server_module)

    exc = CloudcraftError(status=404, body='{"error":"not found"}', method="GET", url="x")
    msg = server_module._format_error(exc)
    assert "not found" in msg
    assert "[truncated]" not in msg


# ---- Fix #4: HTTPS enforcement on CLOUDCRAFT_BASE_URL -----------------------


@pytest.mark.unit
def test_base_url_rejects_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDCRAFT_API_KEY", "k")
    monkeypatch.setenv("CLOUDCRAFT_BASE_URL", "http://api.evil.example.com")
    import cloudcraft_mcp.server as server_module

    with pytest.raises(SystemExit):
        importlib.reload(server_module)


@pytest.mark.unit
def test_base_url_allows_localhost_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDCRAFT_API_KEY", "k")
    monkeypatch.setenv("CLOUDCRAFT_BASE_URL", "http://localhost:8080")
    import cloudcraft_mcp.server as server_module

    server_module = importlib.reload(server_module)
    assert server_module._client._base_url == "http://localhost:8080"


@pytest.mark.unit
def test_base_url_allows_loopback_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDCRAFT_API_KEY", "k")
    monkeypatch.setenv("CLOUDCRAFT_BASE_URL", "http://127.0.0.1:9000")
    import cloudcraft_mcp.server as server_module

    server_module = importlib.reload(server_module)
    assert server_module._client._base_url == "http://127.0.0.1:9000"


# ---- Fix #1: export_blueprint_image path-traversal whitelist ----------------


@pytest.fixture
def server_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Import the server with a controlled export directory."""
    monkeypatch.setenv("CLOUDCRAFT_API_KEY", "test-key-for-startup")
    monkeypatch.setenv("CLOUDCRAFT_EXPORT_DIR", str(tmp_path))
    import cloudcraft_mcp.server as module

    return importlib.reload(module)


@pytest.mark.unit
def test_resolve_export_path_rejects_outside_root(server_module, tmp_path: Path) -> None:
    outside = tempfile.gettempdir() + "/definitely-not-under-tmp-path.png"
    # `outside` is a sibling tmp path — make sure it doesn't accidentally land
    # under the fixture's tmp_path
    assert not Path(outside).resolve().is_relative_to(tmp_path)
    with pytest.raises(RuntimeError, match="must be under"):
        server_module._resolve_export_path(GOOD_UUID, "png", outside)


@pytest.mark.unit
def test_resolve_export_path_rejects_dotdot(server_module, tmp_path: Path) -> None:
    escape = str(tmp_path / ".." / ".." / "etc" / "passwd")
    with pytest.raises(RuntimeError, match="must be under"):
        server_module._resolve_export_path(GOOD_UUID, "png", escape)


@pytest.mark.unit
def test_resolve_export_path_rejects_bad_blueprint_id(server_module) -> None:
    with pytest.raises(ValueError, match="must be a UUID"):
        server_module._resolve_export_path("../etc/passwd", "png", None)


@pytest.mark.unit
def test_resolve_export_path_accepts_default(server_module, tmp_path: Path) -> None:
    target = server_module._resolve_export_path(GOOD_UUID, "png", None)
    assert target.parent == tmp_path
    assert target.name == f"cloudcraft_{GOOD_UUID}.png"


@pytest.mark.unit
def test_resolve_export_path_accepts_inside_root(server_module, tmp_path: Path) -> None:
    target = server_module._resolve_export_path(
        GOOD_UUID, "png", str(tmp_path / "sub" / "out.png")
    )
    assert target == (tmp_path / "sub" / "out.png").resolve()
