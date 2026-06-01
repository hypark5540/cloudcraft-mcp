"""Regression test: the FastMCP server module must import cleanly.

FastMCP introspects each ``@mcp.tool()``-decorated function's signature with
pydantic. On Python < 3.12, pydantic refuses to introspect stdlib
``typing.TypedDict`` — ``BlueprintData`` must therefore come from
``typing_extensions.TypedDict``. This test guards that import path: if someone
ever flips ``types.py`` back to ``typing.TypedDict``, the module will fail to
import on 3.10 / 3.11 CI runners and this test will surface the regression.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.mark.unit
def test_server_module_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing ``cloudcraft_mcp.server`` triggers all ``@mcp.tool()`` registrations.

    A pydantic-incompatible ``TypedDict`` in any tool signature would raise
    ``PydanticUserError`` here, not at server runtime.
    """
    monkeypatch.setenv("CLOUDCRAFT_API_KEY", "test-key-for-startup")
    # Force a fresh import so the module-level ``_build_client`` runs under the
    # patched env. This mirrors how Claude Desktop invokes the entry point.
    import cloudcraft_mcp.server as server_module

    server_module = importlib.reload(server_module)
    assert server_module.mcp.name == "cloudcraft"


@pytest.mark.unit
def test_tool_annotations_describe_mutation_risk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLOUDCRAFT_API_KEY", "test-key-for-startup")
    import cloudcraft_mcp.server as server_module

    server_module = importlib.reload(server_module)
    annotations = {
        tool.name: tool.annotations
        for tool in server_module.mcp._tool_manager.list_tools()
    }

    for name in (
        "whoami",
        "list_blueprints",
        "get_blueprint",
        "list_aws_accounts",
        "snapshot_aws",
    ):
        assert annotations[name].readOnlyHint is True
        assert annotations[name].openWorldHint is True

    assert annotations["create_blueprint"].readOnlyHint is False
    assert annotations["create_blueprint"].destructiveHint is False
    assert annotations["create_blueprint"].idempotentHint is False

    assert annotations["update_blueprint"].readOnlyHint is False
    assert annotations["update_blueprint"].destructiveHint is True
    assert annotations["update_blueprint"].idempotentHint is True

    assert annotations["delete_blueprint"].readOnlyHint is False
    assert annotations["delete_blueprint"].destructiveHint is True
    assert annotations["delete_blueprint"].idempotentHint is False

    assert annotations["export_blueprint_image"].readOnlyHint is False
    assert annotations["export_blueprint_image"].destructiveHint is True


@pytest.mark.unit
def test_blueprintdata_is_pydantic_introspectable() -> None:
    """Guard against flipping ``BlueprintData`` back to ``typing.TypedDict``.

    On Python < 3.12, pydantic raises ``PydanticUserError`` (code
    ``typed-dict-version``) for stdlib ``typing.TypedDict``. ``typing_extensions``
    variant is always accepted. The most reliable runtime check is to ask
    pydantic to build a schema — this exactly reproduces the FastMCP tool
    registration path where the regression would bite.
    """
    from pydantic import TypeAdapter

    from cloudcraft_mcp.types import BlueprintData

    # TypedDict hallmark (sanity)
    assert hasattr(BlueprintData, "__required_keys__"), "BlueprintData must be a TypedDict"

    # Real guard: pydantic must accept it. Would raise PydanticUserError on
    # Python < 3.12 if BlueprintData were stdlib typing.TypedDict.
    TypeAdapter(BlueprintData)
