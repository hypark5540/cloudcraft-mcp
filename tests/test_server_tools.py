"""Coverage for the MCP tool wrappers in ``cloudcraft_mcp.server``.

FastMCP's ``@mcp.tool()`` decorator is transparent — it registers the function
with the server and returns it unchanged — so these tests call each tool
directly as a regular async function. We stub the module-level ``_client``
with ``AsyncMock`` so no network or env-var wiring is required.

Together with ``test_validation.py`` (which covers ``_format_error``,
``_resolve_export_path``, and startup paths) this brings server.py above
the 80% Codecov gate.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from cloudcraft_mcp.client import CloudcraftError

GOOD_UUID = "4e759c63-1f2b-4663-a54c-0122e11a5386"


@pytest.fixture
def server_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Reload server with a controlled API key + export dir."""
    monkeypatch.setenv("CLOUDCRAFT_API_KEY", "test-key-for-startup")
    monkeypatch.setenv("CLOUDCRAFT_EXPORT_DIR", str(tmp_path))
    import cloudcraft_mcp.server as module

    return importlib.reload(module)


def _fake_error(status: int = 500, body: str = "boom") -> CloudcraftError:
    return CloudcraftError(status=status, body=body, method="GET", url="x")


# ---- whoami ----------------------------------------------------------------


@pytest.mark.unit
async def test_whoami_success(server_module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        server_module._client, "whoami", AsyncMock(return_value={"id": "u1"})
    )
    assert await server_module.whoami() == {"id": "u1"}


@pytest.mark.unit
async def test_whoami_wraps_cloudcraft_error(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client, "whoami", AsyncMock(side_effect=_fake_error(401, "nope"))
    )
    with pytest.raises(RuntimeError, match="401"):
        await server_module.whoami()


# ---- list / get / create / update / delete blueprint -----------------------


@pytest.mark.unit
async def test_list_blueprints_reshapes_items(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = {
        "blueprints": [
            {
                "id": GOOD_UUID,
                "name": "prod",
                "tags": ["aws"],
                "updatedAt": "2026-04-23",
                "createdAt": "2026-04-20",
            }
        ]
    }
    monkeypatch.setattr(
        server_module._client, "list_blueprints", AsyncMock(return_value=raw)
    )
    out = await server_module.list_blueprints()
    assert out["count"] == 1
    assert out["blueprints"][0]["id"] == GOOD_UUID
    assert out["blueprints"][0]["tags"] == ["aws"]


@pytest.mark.unit
async def test_list_blueprints_error(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "list_blueprints",
        AsyncMock(side_effect=_fake_error(500, "upstream")),
    )
    with pytest.raises(RuntimeError, match="500"):
        await server_module.list_blueprints()


@pytest.mark.unit
async def test_get_blueprint_success(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "get_blueprint",
        AsyncMock(return_value={"id": GOOD_UUID}),
    )
    assert await server_module.get_blueprint(GOOD_UUID) == {"id": GOOD_UUID}


@pytest.mark.unit
async def test_get_blueprint_translates_value_error(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bad UUID raises ValueError from the validator; tool surfaces RuntimeError."""
    with pytest.raises(RuntimeError, match="must be a UUID"):
        await server_module.get_blueprint("not-a-uuid")


@pytest.mark.unit
async def test_get_blueprint_translates_cloudcraft_error(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "get_blueprint",
        AsyncMock(side_effect=_fake_error(404, "not found")),
    )
    with pytest.raises(RuntimeError, match="404"):
        await server_module.get_blueprint(GOOD_UUID)


@pytest.mark.unit
async def test_create_blueprint_merges_name(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    create = AsyncMock(return_value={"id": GOOD_UUID})
    monkeypatch.setattr(server_module._client, "create_blueprint", create)
    payload = {"grid": "infinite", "version": 6}
    await server_module.create_blueprint("new-bp", payload)  # type: ignore[arg-type]
    create.assert_awaited_once()
    merged = create.await_args.args[0]
    assert merged["name"] == "new-bp"
    assert merged["grid"] == "infinite"


@pytest.mark.unit
async def test_create_blueprint_error(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "create_blueprint",
        AsyncMock(side_effect=_fake_error(422, "bad payload")),
    )
    with pytest.raises(RuntimeError, match="422"):
        await server_module.create_blueprint("x", {"version": 6})  # type: ignore[arg-type]


@pytest.mark.unit
async def test_update_blueprint_success(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "update_blueprint",
        AsyncMock(return_value={"id": GOOD_UUID}),
    )
    assert await server_module.update_blueprint(GOOD_UUID, {"nodes": []}) == {  # type: ignore[arg-type]
        "id": GOOD_UUID
    }


@pytest.mark.unit
async def test_update_blueprint_rejects_bad_uuid(server_module) -> None:
    with pytest.raises(RuntimeError, match="must be a UUID"):
        await server_module.update_blueprint("bad-id", {"nodes": []})  # type: ignore[arg-type]


@pytest.mark.unit
async def test_update_blueprint_cloudcraft_error(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "update_blueprint",
        AsyncMock(side_effect=_fake_error(500, "boom")),
    )
    with pytest.raises(RuntimeError, match="500"):
        await server_module.update_blueprint(GOOD_UUID, {"nodes": []})  # type: ignore[arg-type]


@pytest.mark.unit
async def test_delete_blueprint_success(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client, "delete_blueprint", AsyncMock(return_value=None)
    )
    assert await server_module.delete_blueprint(GOOD_UUID) == {"deleted": GOOD_UUID}


@pytest.mark.unit
async def test_delete_blueprint_rejects_bad_uuid(server_module) -> None:
    with pytest.raises(RuntimeError, match="must be a UUID"):
        await server_module.delete_blueprint("../etc/passwd")


@pytest.mark.unit
async def test_delete_blueprint_cloudcraft_error(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "delete_blueprint",
        AsyncMock(side_effect=_fake_error(403, "forbidden")),
    )
    with pytest.raises(RuntimeError, match="403"):
        await server_module.delete_blueprint(GOOD_UUID)


# ---- export_blueprint_image -----------------------------------------------


@pytest.mark.unit
async def test_export_blueprint_image_writes_file(
    server_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "export_blueprint",
        AsyncMock(return_value=b"\x89PNGDATA"),
    )
    out = await server_module.export_blueprint_image(GOOD_UUID, "png")
    assert out["format"] == "png"
    assert out["bytes"] == len(b"\x89PNGDATA")
    assert Path(out["path"]).read_bytes() == b"\x89PNGDATA"


@pytest.mark.unit
async def test_export_blueprint_image_mxgraph_extension(
    server_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """mxgraph format must land on disk as a .xml file, not .mxgraph."""
    monkeypatch.setattr(
        server_module._client, "export_blueprint", AsyncMock(return_value=b"<mxGraph/>")
    )
    out = await server_module.export_blueprint_image(GOOD_UUID, "mxgraph")
    assert out["path"].endswith(".xml")


@pytest.mark.unit
async def test_export_blueprint_image_refuses_overwrite(
    server_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / f"cloudcraft_{GOOD_UUID}.png"
    target.write_bytes(b"existing")
    monkeypatch.setattr(
        server_module._client, "export_blueprint", AsyncMock(return_value=b"new")
    )
    with pytest.raises(RuntimeError, match="already exists"):
        await server_module.export_blueprint_image(GOOD_UUID, "png")
    # original file preserved
    assert target.read_bytes() == b"existing"


@pytest.mark.unit
async def test_export_blueprint_image_overwrite_flag(
    server_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / f"cloudcraft_{GOOD_UUID}.png"
    target.write_bytes(b"existing")
    monkeypatch.setattr(
        server_module._client, "export_blueprint", AsyncMock(return_value=b"new")
    )
    out = await server_module.export_blueprint_image(
        GOOD_UUID, "png", overwrite=True
    )
    assert Path(out["path"]).read_bytes() == b"new"


@pytest.mark.unit
async def test_export_blueprint_image_rejects_outside_export_dir(
    server_module, tmp_path: Path
) -> None:
    outside = "/etc/passwd"
    with pytest.raises(RuntimeError, match="must be under"):
        await server_module.export_blueprint_image(
            GOOD_UUID, "png", output_path=outside
        )


@pytest.mark.unit
async def test_export_blueprint_image_rejects_bad_uuid(server_module) -> None:
    with pytest.raises(RuntimeError, match="must be a UUID"):
        await server_module.export_blueprint_image("not-a-uuid", "png")


@pytest.mark.unit
async def test_export_blueprint_image_wraps_cloudcraft_error(
    server_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "export_blueprint",
        AsyncMock(side_effect=_fake_error(503, "busy")),
    )
    with pytest.raises(RuntimeError, match="503"):
        await server_module.export_blueprint_image(GOOD_UUID, "png")


@pytest.mark.unit
async def test_export_blueprint_image_wraps_value_error(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unsupported format comes from the client's ValueError path."""
    monkeypatch.setattr(
        server_module._client,
        "export_blueprint",
        AsyncMock(side_effect=ValueError("unsupported format: 'gif'")),
    )
    with pytest.raises(RuntimeError, match="unsupported format"):
        await server_module.export_blueprint_image(GOOD_UUID, "gif")


# ---- aws live-scan ---------------------------------------------------------


@pytest.mark.unit
async def test_list_aws_accounts_success(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "list_aws_accounts",
        AsyncMock(return_value={"accounts": []}),
    )
    assert await server_module.list_aws_accounts() == {"accounts": []}


@pytest.mark.unit
async def test_list_aws_accounts_error(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "list_aws_accounts",
        AsyncMock(side_effect=_fake_error(401, "key expired")),
    )
    with pytest.raises(RuntimeError, match="401"):
        await server_module.list_aws_accounts()


@pytest.mark.unit
async def test_snapshot_aws_success(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "snapshot_aws",
        AsyncMock(return_value={"service": "ec2", "count": 0}),
    )
    result = await server_module.snapshot_aws(GOOD_UUID, "ap-northeast-2", "ec2")
    assert result["service"] == "ec2"


@pytest.mark.unit
async def test_snapshot_aws_rejects_bad_region(server_module) -> None:
    with pytest.raises(RuntimeError, match="region must look like"):
        await server_module.snapshot_aws(GOOD_UUID, "AP-NORTHEAST-2", "ec2")


@pytest.mark.unit
async def test_snapshot_aws_wraps_cloudcraft_error(
    server_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_module._client,
        "snapshot_aws",
        AsyncMock(side_effect=_fake_error(500, "aws unreachable")),
    )
    with pytest.raises(RuntimeError, match="500"):
        await server_module.snapshot_aws(GOOD_UUID, "us-east-1", "s3")


# ---- startup error paths ---------------------------------------------------


@pytest.mark.unit
def test_build_client_exits_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing ``CLOUDCRAFT_API_KEY`` must terminate startup with exit(1)."""
    monkeypatch.delenv("CLOUDCRAFT_API_KEY", raising=False)
    import cloudcraft_mcp.server as module

    with pytest.raises(SystemExit):
        importlib.reload(module)


@pytest.mark.unit
def test_main_invokes_mcp_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The ``main`` entry point must wire logging and call ``mcp.run``."""
    monkeypatch.setenv("CLOUDCRAFT_API_KEY", "test-key-for-startup")
    monkeypatch.setenv("CLOUDCRAFT_EXPORT_DIR", str(tmp_path))
    import cloudcraft_mcp.server as module

    module = importlib.reload(module)

    run_calls: list[None] = []
    monkeypatch.setattr(module.mcp, "run", lambda: run_calls.append(None))
    module.main()
    assert run_calls == [None]
