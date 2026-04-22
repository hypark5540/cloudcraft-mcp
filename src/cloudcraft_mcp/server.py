"""MCP tool surface for Cloudcraft.

All tools are thin wrappers around :class:`CloudcraftClient`. The client
reads its API key from the ``CLOUDCRAFT_API_KEY`` env var at import time.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import CloudcraftClient, CloudcraftError
from .types import BlueprintData

__all__ = ["mcp", "main"]

logger = logging.getLogger("cloudcraft_mcp")


def _build_client() -> CloudcraftClient:
    api_key = os.environ.get("CLOUDCRAFT_API_KEY")
    if not api_key:
        print(
            "ERROR: CLOUDCRAFT_API_KEY environment variable is required. "
            "Generate one at https://app.cloudcraft.co/ → User settings → API keys.",
            file=sys.stderr,
        )
        sys.exit(1)
    base_url = os.environ.get("CLOUDCRAFT_BASE_URL", "https://api.cloudcraft.co")
    return CloudcraftClient(api_key=api_key, base_url=base_url)


_client = _build_client()
mcp: FastMCP = FastMCP("cloudcraft")


# ---- helpers -----------------------------------------------------------------
def _format_error(exc: CloudcraftError) -> str:
    return f"Cloudcraft API error ({exc.status}): {exc.body}"


# ---- user --------------------------------------------------------------------
@mcp.tool()
async def whoami() -> dict[str, Any]:
    """Return the Cloudcraft user profile for the current API key.

    Useful as a sanity check after configuring a new key.
    """
    try:
        return await _client.whoami()
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from exc


# ---- blueprints --------------------------------------------------------------
@mcp.tool()
async def list_blueprints() -> dict[str, Any]:
    """List every Cloudcraft blueprint (diagram) in the authenticated account.

    Returns a compact summary per blueprint (id, name, tags, updatedAt).
    Use :func:`get_blueprint` afterwards to pull the full node / edge JSON.
    """
    try:
        data = await _client.list_blueprints()
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from exc

    items = data.get("blueprints", data if isinstance(data, list) else [])
    return {
        "count": len(items),
        "blueprints": [
            {
                "id": b.get("id"),
                "name": b.get("name"),
                "tags": b.get("tags", []),
                "updatedAt": b.get("updatedAt") or b.get("updated_at"),
                "createdAt": b.get("createdAt") or b.get("created_at"),
            }
            for b in items
        ],
    }


@mcp.tool()
async def get_blueprint(blueprint_id: str) -> dict[str, Any]:
    """Fetch the full blueprint payload (nodes, edges, groups, layout).

    Args:
        blueprint_id: Blueprint UUID from :func:`list_blueprints`.
    """
    try:
        return await _client.get_blueprint(blueprint_id)
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from exc


@mcp.tool()
async def create_blueprint(name: str, data: BlueprintData) -> dict[str, Any]:
    """Create a new Cloudcraft blueprint.

    Args:
        name: Display name for the new blueprint.
        data: Full blueprint payload (nodes, edges, groups, surfaces, text,
            icons, connectors, theme, projection, etc.). See README for a
            minimal example.

    Returns the created blueprint metadata including the assigned id.
    """
    payload = {**data, "name": name}
    try:
        return await _client.create_blueprint(payload)
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from exc


@mcp.tool()
async def update_blueprint(blueprint_id: str, data: BlueprintData) -> dict[str, Any]:
    """Replace the full data payload of an existing blueprint.

    Args:
        blueprint_id: Blueprint UUID.
        data: Full blueprint payload (same shape as :func:`create_blueprint`).
    """
    try:
        return await _client.update_blueprint(blueprint_id, data)
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from exc


@mcp.tool()
async def delete_blueprint(blueprint_id: str) -> dict[str, Any]:
    """Delete a Cloudcraft blueprint. Irreversible — confirm before calling.

    Args:
        blueprint_id: Blueprint UUID.
    """
    try:
        await _client.delete_blueprint(blueprint_id)
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from exc
    return {"deleted": blueprint_id}


@mcp.tool()
async def export_blueprint_image(
    blueprint_id: str,
    format: str = "png",
    output_path: str | None = None,
    scale: float | None = None,
    transparent: bool | None = None,
) -> dict[str, Any]:
    """Render a Cloudcraft blueprint to an image file on disk.

    Args:
        blueprint_id: Blueprint UUID.
        format: One of ``png``, ``svg``, ``pdf``, ``mxgraph``. Default ``png``.
        output_path: Absolute path to save to. Default: ``/tmp/cloudcraft_<id>.<ext>``.
        scale: Optional PNG render scale (e.g. 1.0, 2.0). PNG only.
        transparent: PNG transparent background (bool). PNG only.

    Returns:
        ``{"path": <saved_path>, "bytes": <size>, "format": <fmt>}``
    """
    fmt = format.lower()
    try:
        content = await _client.export_blueprint(
            blueprint_id, fmt, scale=scale, transparent=transparent
        )
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from exc
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    ext = "xml" if fmt == "mxgraph" else fmt
    target = Path(output_path) if output_path else Path(f"/tmp/cloudcraft_{blueprint_id}.{ext}")
    target.write_bytes(content)
    return {"path": str(target), "bytes": len(content), "format": fmt}


# ---- aws live-scan ----------------------------------------------------------
@mcp.tool()
async def list_aws_accounts() -> dict[str, Any]:
    """List AWS accounts registered with Cloudcraft for live-scan snapshots."""
    try:
        return await _client.list_aws_accounts()
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from exc


@mcp.tool()
async def snapshot_aws(account_id: str, region: str, service: str) -> dict[str, Any]:
    """Take a live-scan snapshot of one AWS service via Cloudcraft.

    Args:
        account_id: Cloudcraft AWS account id (from :func:`list_aws_accounts`).
        region: AWS region code, e.g. ``ap-northeast-2``.
        service: Service to snapshot, e.g. ``ec2``, ``s3``, ``rds``, ``lambda``, ``vpc``.
    """
    try:
        return await _client.snapshot_aws(account_id, region, service)
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from exc


def main() -> None:
    """Entry point used by the ``cloudcraft-mcp`` console script."""
    logging.basicConfig(
        level=os.environ.get("CLOUDCRAFT_LOG_LEVEL", "WARNING"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    mcp.run()


if __name__ == "__main__":
    main()
