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

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import __version__
from .client import (
    DEFAULT_MAX_RESPONSE_BYTES,
    CloudcraftClient,
    CloudcraftError,
    _validate_uuid,
)
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
    try:
        max_response_bytes = int(
            os.environ.get(
                "CLOUDCRAFT_MAX_RESPONSE_BYTES", str(DEFAULT_MAX_RESPONSE_BYTES)
            )
        )
        return CloudcraftClient(
            api_key=api_key,
            base_url=base_url,
            max_response_bytes=max_response_bytes,
        )
    except ValueError as exc:
        print(
            f"ERROR: invalid Cloudcraft MCP configuration: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


_client = _build_client()

# Directory that export_blueprint_image is allowed to write into. The default
# is a process-private 0700 directory rather than the shared system temp root.
_export_root_override = os.environ.get("CLOUDCRAFT_EXPORT_DIR")
if _export_root_override:
    _EXPORT_ROOT = Path(_export_root_override).expanduser().resolve()
else:
    _EXPORT_ROOT = Path(tempfile.mkdtemp(prefix="cloudcraft-mcp-exports-")).resolve()

mcp: FastMCP = FastMCP("cloudcraft")
# FastMCP 1.x does not expose the low-level Server ``version`` parameter, but
# does expose its Server instance. Keep the MCP initialize metadata aligned
# with the package version instead of reporting the SDK's own version.
mcp._mcp_server.version = __version__

_READ_ONLY_EXTERNAL_TOOL = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
_CREATE_BLUEPRINT_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)
_UPDATE_BLUEPRINT_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=True,
)
_DELETE_BLUEPRINT_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)
_EXPORT_IMAGE_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)
_SNAPSHOT_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


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


def _write_export_file(target: Path, content: bytes, *, overwrite: bool) -> Path:
    """Write an export without following a raced final-component symlink."""
    target.parent.mkdir(parents=True, exist_ok=True)
    parent = target.parent.resolve()
    if parent != _EXPORT_ROOT and _EXPORT_ROOT not in parent.parents:
        raise RuntimeError(f"output_path must be under {_EXPORT_ROOT}")
    final_target = parent / target.name

    if overwrite:
        fd, temporary_name = tempfile.mkstemp(
            dir=parent, prefix=".cloudcraft-mcp-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, final_target)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        return final_target

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(final_target, flags, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(
            f"{final_target} already exists. Pass overwrite=True to replace it."
        ) from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        final_target.unlink(missing_ok=True)
        raise
    return final_target


def _enabled(name: str) -> bool:
    value = os.environ.get(name, "false").strip().lower()
    if value not in {"true", "false"}:
        raise RuntimeError(f"{name} must be either 'true' or 'false'")
    return value == "true"


def _require_write_enabled(*, delete: bool = False) -> None:
    if not _enabled("CLOUDCRAFT_ENABLE_WRITES"):
        raise RuntimeError(
            "Cloudcraft mutations are disabled. Set CLOUDCRAFT_ENABLE_WRITES=true "
            "in the MCP server environment to enable them."
        )
    if delete and not _enabled("CLOUDCRAFT_ENABLE_DELETES"):
        raise RuntimeError(
            "Cloudcraft deletes are disabled. Also set "
            "CLOUDCRAFT_ENABLE_DELETES=true to enable them."
        )


# ---- user --------------------------------------------------------------------
@mcp.tool(annotations=_READ_ONLY_EXTERNAL_TOOL)
async def whoami() -> dict[str, Any]:
    """Return the Cloudcraft user profile for the current API key.

    Useful as a sanity check after configuring a new key.
    """
    try:
        return await _client.whoami()
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from None


# ---- blueprints --------------------------------------------------------------
@mcp.tool(annotations=_READ_ONLY_EXTERNAL_TOOL)
async def list_blueprints() -> dict[str, Any]:
    """List every Cloudcraft blueprint (diagram) in the authenticated account.

    Returns a compact summary per blueprint (id, name, tags, updatedAt).
    Use :func:`get_blueprint` afterwards to pull the full node / edge JSON.
    """
    try:
        data = await _client.list_blueprints()
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from None

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


@mcp.tool(annotations=_READ_ONLY_EXTERNAL_TOOL)
async def get_blueprint(blueprint_id: str) -> dict[str, Any]:
    """Fetch the full blueprint payload (nodes, edges, groups, layout).

    Args:
        blueprint_id: Blueprint UUID from :func:`list_blueprints`.
    """
    try:
        return await _client.get_blueprint(blueprint_id)
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from None
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


@mcp.tool(annotations=_CREATE_BLUEPRINT_TOOL)
async def create_blueprint(name: str, data: BlueprintData) -> dict[str, Any]:
    """Create a new Cloudcraft blueprint.

    Args:
        name: Display name for the new blueprint.
        data: Full blueprint payload (nodes, edges, groups, surfaces, text,
            icons, connectors, theme, projection, etc.). See README for a
            minimal example.

    Returns the created blueprint metadata including the assigned id.
    """
    _require_write_enabled()
    payload = {**data, "name": name}
    try:
        return await _client.create_blueprint(payload)
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from None


@mcp.tool(annotations=_UPDATE_BLUEPRINT_TOOL)
async def update_blueprint(blueprint_id: str, data: BlueprintData) -> dict[str, Any]:
    """Replace the full data payload of an existing blueprint.

    Args:
        blueprint_id: Blueprint UUID.
        data: Full blueprint payload (same shape as :func:`create_blueprint`).
    """
    _require_write_enabled()
    try:
        return await _client.update_blueprint(blueprint_id, data)
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from None
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


@mcp.tool(annotations=_DELETE_BLUEPRINT_TOOL)
async def delete_blueprint(
    blueprint_id: str, confirm_blueprint_id: str
) -> dict[str, Any]:
    """Delete a Cloudcraft blueprint after exact-id confirmation.

    Args:
        blueprint_id: Blueprint UUID.
        confirm_blueprint_id: Repeat the exact UUID to acknowledge the
            irreversible operation.
    """
    _require_write_enabled(delete=True)
    if confirm_blueprint_id != blueprint_id:
        raise RuntimeError("confirm_blueprint_id must exactly match blueprint_id")
    try:
        await _client.delete_blueprint(blueprint_id)
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from None
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    return {"deleted": blueprint_id}


@mcp.tool(annotations=_EXPORT_IMAGE_TOOL)
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
        raise RuntimeError(_format_error(exc)) from None
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    target = _write_export_file(target, content, overwrite=overwrite)
    return {"path": str(target), "bytes": len(content), "format": fmt}


# ---- aws live-scan ----------------------------------------------------------
@mcp.tool(annotations=_READ_ONLY_EXTERNAL_TOOL)
async def list_aws_accounts() -> dict[str, Any]:
    """List AWS accounts registered with Cloudcraft for live-scan snapshots."""
    try:
        return await _client.list_aws_accounts()
    except CloudcraftError as exc:
        raise RuntimeError(_format_error(exc)) from None


@mcp.tool(annotations=_SNAPSHOT_TOOL)
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
        raise RuntimeError(_format_error(exc)) from None
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
