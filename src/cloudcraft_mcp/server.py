"""MCP tool surface for Cloudcraft.

All tools are thin wrappers around :class:`CloudcraftClient`. The client
reads its API key from the ``CLOUDCRAFT_API_KEY`` env var at import time.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

from .client import CloudcraftClient, CloudcraftError, _validate_uuid
from .types import BlueprintData

__all__ = ["mcp", "main"]

logger = logging.getLogger("cloudcraft_mcp")

# Max characters of upstream error body forwarded to the MCP host. Prevents
# runaway HTML pages or unexpected fields from ballooning the LLM context.
_ERROR_BODY_CAP = 500

# Redact anything shaped like an Authorization header that the upstream might
# echo back in 4xx/5xx responses.
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)


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
    # Fix #4: reject non-HTTPS base URLs so a tampered env var cannot silently
    # downgrade the Bearer token to cleartext. Loopback HTTP is allowed for
    # local testing against a proxy or mock server.
    #
    # Parse the URL and match the hostname exactly. A naive startswith() check
    # on "http://localhost" / "http://127.0.0.1" matches attacker-controlled
    # hosts like "http://localhost.evil.example.com", which would silently
    # downgrade Bearer auth to cleartext over the public internet.
    parsed = urlparse(base_url)
    is_https = parsed.scheme == "https"
    is_loopback_http = (
        parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")
    )
    if not (is_https or is_loopback_http):
        print(
            f"ERROR: CLOUDCRAFT_BASE_URL must be https:// (or http://localhost for testing). "
            f"Got: {base_url!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    return CloudcraftClient(api_key=api_key, base_url=base_url)


# Directory that export_blueprint_image is allowed to write into. Defaults to
# the system temp dir; override with CLOUDCRAFT_EXPORT_DIR to, say, a project
# folder. Resolved once at import time so later symlink games cannot confuse
# the whitelist check.
_EXPORT_ROOT: Path = Path(
    os.environ.get("CLOUDCRAFT_EXPORT_DIR", tempfile.gettempdir())
).expanduser().resolve()


_client = _build_client()
mcp: FastMCP = FastMCP("cloudcraft")


# ---- helpers -----------------------------------------------------------------
def _format_error(exc: CloudcraftError) -> str:
    """Produce an MCP-safe error string from a CloudcraftError.

    Fix #3: cap the upstream body at _ERROR_BODY_CAP characters and redact
    anything that looks like a Bearer token, so an echo'd Authorization header
    in a 4xx response does not leak the live API key into the LLM context.
    """
    body = (exc.body or "")[:_ERROR_BODY_CAP]
    body = _BEARER_RE.sub("Bearer ***", body)
    suffix = " [truncated]" if exc.body and len(exc.body) > _ERROR_BODY_CAP else ""
    return f"Cloudcraft API error ({exc.status}): {body}{suffix}"


def _resolve_export_path(blueprint_id: str, ext: str, output_path: str | None) -> Path:
    """Return a safe absolute path inside _EXPORT_ROOT for writing the export.

    Fix #1: Both the caller-supplied ``output_path`` and the default path
    (which embeds ``blueprint_id`` in the filename) are resolved and checked
    to be strictly under ``_EXPORT_ROOT``. ``blueprint_id`` is additionally
    UUID-validated so ".." segments can never leak into the default filename.
    """
    _validate_uuid("blueprint_id", blueprint_id)
    if output_path is not None:
        candidate = Path(output_path).expanduser().resolve()
    else:
        candidate = (_EXPORT_ROOT / f"cloudcraft_{blueprint_id}.{ext}").resolve()
    # strict containment: candidate must be _EXPORT_ROOT itself or below it.
    if candidate != _EXPORT_ROOT and _EXPORT_ROOT not in candidate.parents:
        raise RuntimeError(
            f"output_path must be under {_EXPORT_ROOT}. "
            f"Set CLOUDCRAFT_EXPORT_DIR to allow a different directory."
        )
    return candidate


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
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


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
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


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
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    return {"deleted": blueprint_id}


@mcp.tool()
async def export_blueprint_image(
    blueprint_id: str,
    format: str = "png",
    output_path: str | None = None,
    scale: float | None = None,
    transparent: bool | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Render a Cloudcraft blueprint to an image file on disk.

    Writes are restricted to ``CLOUDCRAFT_EXPORT_DIR`` (default: system temp
    directory). Set ``CLOUDCRAFT_EXPORT_DIR=/path/to/dir`` in the MCP server
    environment to allow saving under a different directory.

    Args:
        blueprint_id: Blueprint UUID.
        format: One of ``png``, ``svg``, ``pdf``, ``mxgraph``. Default ``png``.
        output_path: Absolute path to save to, must resolve under the export
            directory. Default: ``<export_dir>/cloudcraft_<uuid>.<ext>``.
        scale: Optional PNG render scale (e.g. 1.0, 2.0). PNG only.
        transparent: PNG transparent background (bool). PNG only.
        overwrite: Set True to replace an existing file at ``output_path``.
            Default False — existing files are preserved.

    Returns:
        ``{"path": <saved_path>, "bytes": <size>, "format": <fmt>}``
    """
    fmt = format.lower()
    ext = "xml" if fmt == "mxgraph" else fmt
    # Resolve + validate destination BEFORE hitting the network so a bad path
    # fails fast without wasting a Cloudcraft quota / export credit.
    try:
        target = _resolve_export_path(blueprint_id, ext, output_path)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    if target.exists() and not overwrite:
        raise RuntimeError(
            f"{target} already exists. Pass overwrite=True to replace it."
        )
    try:
        content = await _client.export_blueprint(
            blueprint_id, fmt, scale=scale, transparent=transparent
        )
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from exc
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    target.parent.mkdir(parents=True, exist_ok=True)
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
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


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
