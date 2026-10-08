"""HTTP client wrapping the Cloudcraft REST API.

Keeps the transport layer separate from MCP tool definitions so the client
can be unit-tested with respx and reused from non-MCP contexts (scripts,
CLI, etc.).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import urlparse

import httpx

__all__ = ["CloudcraftClient", "CloudcraftError"]

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.cloudcraft.co"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
DEFAULT_MAX_RESPONSE_BYTES = 25 * 1024 * 1024
_MAX_ERROR_BODY_BYTES = 4 * 1024

# ---- path-segment validation ------------------------------------------------
# Defense-in-depth against LLM-supplied values containing "..", "?", "/" etc.
# httpx normalises "/a/../b" to "/b" before sending, which would otherwise let
# a caller pivot to Cloudcraft endpoints this MCP server does not expose.
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# AWS region codes: e.g. ap-northeast-2, us-east-1, eu-west-3, us-gov-west-1.
_REGION_RE = re.compile(r"^[a-z]{2}(?:-[a-z]+)+-\d$")
# AWS/Cloudcraft service slugs are lowercase alphanumerics and dashes. Loose
# regex (no hard-coded whitelist) so we don't have to track every new service.
_SERVICE_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
# Azure region codes have no separators: eastus, koreacentral, usgovvirginia.
_AZURE_REGION_RE = re.compile(r"^[a-z][a-z0-9]{2,31}$")

# Export format as accepted from callers -> spelling the API expects in the path.
_EXPORT_FORMATS = {"png": "png", "svg": "svg", "pdf": "pdf", "mxgraph": "mxGraph"}
_BUDGET_FORMATS = ("csv", "xlsx")


def _validate_uuid(name: str, value: str) -> str:
    if not isinstance(value, str) or not _UUID_RE.match(value):
        raise ValueError(f"{name} must be a UUID (got {value!r})")
    return value


def _validate_region(value: str) -> str:
    if not isinstance(value, str) or not _REGION_RE.match(value):
        raise ValueError(f"region must look like 'ap-northeast-2' (got {value!r})")
    return value


def _validate_azure_region(value: str) -> str:
    if not isinstance(value, str) or not _AZURE_REGION_RE.match(value):
        raise ValueError(f"region must look like 'eastus' (got {value!r})")
    return value


def _validate_service(value: str) -> str:
    if not isinstance(value, str) or not _SERVICE_RE.match(value):
        raise ValueError(
            f"service must be a short lowercase slug like 'ec2' (got {value!r})"
        )
    return value


def _validate_base_url(value: str) -> str:
    """Return a normalized API URL that cannot leak Bearer auth over HTTP."""
    normalized = value.rstrip("/")
    parsed = urlparse(normalized)
    is_https = parsed.scheme == "https" and parsed.hostname is not None
    is_loopback_http = (
        parsed.scheme == "http"
        and parsed.hostname in ("localhost", "127.0.0.1")
    )
    if not (is_https or is_loopback_http):
        raise ValueError(
            "base_url must use https:// (or http://localhost for local testing)"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("base_url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("base_url must not contain a query string or fragment")
    return normalized


class CloudcraftError(RuntimeError):
    """Raised when the Cloudcraft API returns a non-2xx response."""

    def __init__(self, status: int, body: str, method: str, url: str) -> None:
        # Keep the untrusted response body out of the exception message: an
        # exception chain or debug traceback must not bypass the MCP-facing
        # redaction performed by server._format_error().
        super().__init__(f"{method} {url} -> {status}")
        self.status = status
        self.body = body
        self.method = method
        self.url = url


class CloudcraftClient:
    """Async HTTP client for Cloudcraft.

    Uses Bearer-token auth (Cloudcraft API keys from User settings → API keys).
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: httpx.Timeout | float | None = None,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        if isinstance(max_response_bytes, bool) or max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be a positive integer")
        self._base_url = _validate_base_url(base_url)
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        self._timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        self._max_response_bytes = max_response_bytes

    # ---- internal helpers ---------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        headers = dict(self._headers)
        if json is not None:
            headers["Content-Type"] = "application/json"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                logger.debug("%s %s", method, url)
                async with client.stream(
                    method, url, headers=headers, params=params, json=json
                ) as response:
                    declared_length = response.headers.get("content-length")
                    if declared_length is not None:
                        try:
                            declared_bytes = int(declared_length)
                        except ValueError:
                            declared_bytes = 0
                        if declared_bytes > self._max_response_bytes:
                            raise CloudcraftError(
                                status=502,
                                body=(
                                    "Cloudcraft response exceeded the configured "
                                    f"{self._max_response_bytes}-byte limit"
                                ),
                                method=method,
                                url=url,
                            )

                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > self._max_response_bytes:
                            raise CloudcraftError(
                                status=502,
                                body=(
                                    "Cloudcraft response exceeded the configured "
                                    f"{self._max_response_bytes}-byte limit"
                                ),
                                method=method,
                                url=url,
                            )
                        content.extend(chunk)
                    # ``content`` is already *decoded*: httpx ran the
                    # Content-Encoding decoders while streaming. Copying the
                    # headers verbatim would make httpx.Response.read() gunzip
                    # the plaintext a second time and raise DecodingError (#20).
                    buffered_headers = httpx.Headers(response.headers)
                    buffered_headers.pop("content-encoding", None)
                    buffered_headers["content-length"] = str(len(content))
                    buffered = httpx.Response(
                        status_code=response.status_code,
                        headers=buffered_headers,
                        content=bytes(content),
                        request=response.request,
                    )
        except httpx.HTTPError as exc:
            raise CloudcraftError(
                status=502,
                body=f"Cloudcraft transport failed ({type(exc).__name__})",
                method=method,
                url=url,
            ) from None
        if buffered.status_code >= 400:
            body = buffered.content[:_MAX_ERROR_BODY_BYTES].decode(
                buffered.encoding or "utf-8", errors="replace"
            )
            if buffered.status_code == 429:
                # Cloudcraft rate limits per key and sends the wait in seconds.
                retry_after = buffered.headers.get("retry-after", "60")
                body = f"rate limited; retry after {retry_after}s. {body}".rstrip()
            raise CloudcraftError(
                status=buffered.status_code, body=body, method=method, url=url
            )
        return buffered

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        envelope: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a JSON object; a bare JSON array is wrapped under ``envelope``."""
        response = await self._request(method, path, params=params, json=json)
        try:
            data = response.json()
        except ValueError:
            raise CloudcraftError(
                status=response.status_code,
                body="invalid JSON body",
                method=method,
                url=f"{self._base_url}{path}",
            ) from None
        if isinstance(data, list) and envelope is not None:
            return {envelope: data}
        if not isinstance(data, dict):
            raise CloudcraftError(
                status=response.status_code,
                body=f"expected JSON object, got {type(data).__name__}",
                method=method,
                url=f"{self._base_url}{path}",
            )
        return cast(dict[str, Any], data)

    # ---- user ---------------------------------------------------------------
    async def whoami(self) -> dict[str, Any]:
        return await self._request_json("GET", "/user/me")

    # ---- blueprints ---------------------------------------------------------
    async def list_blueprints(self) -> dict[str, Any]:
        return await self._request_json("GET", "/blueprint", envelope="blueprints")

    async def get_blueprint(self, blueprint_id: str) -> dict[str, Any]:
        blueprint_id = _validate_uuid("blueprint_id", blueprint_id)
        return await self._request_json("GET", f"/blueprint/{blueprint_id}")

    async def create_blueprint(self, data: Mapping[str, Any]) -> dict[str, Any]:
        return await self._request_json(
            "POST", "/blueprint", json={"data": dict(data)}
        )

    async def update_blueprint(
        self, blueprint_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]:
        blueprint_id = _validate_uuid("blueprint_id", blueprint_id)
        # Cloudcraft answers a successful PUT with 204 No Content, which
        # _request_json would report as "invalid JSON body" (#21).
        response = await self._request(
            "PUT", f"/blueprint/{blueprint_id}", json={"data": dict(data)}
        )
        try:
            payload = response.json() if response.content.strip() else None
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            return cast(dict[str, Any], payload)
        return {"id": blueprint_id, "updated": True}

    async def delete_blueprint(self, blueprint_id: str) -> None:
        blueprint_id = _validate_uuid("blueprint_id", blueprint_id)
        await self._request("DELETE", f"/blueprint/{blueprint_id}")

    async def export_blueprint(
        self,
        blueprint_id: str,
        fmt: str,
        *,
        scale: float | None = None,
        transparent: bool | None = None,
    ) -> bytes:
        if fmt not in _EXPORT_FORMATS:
            raise ValueError(f"unsupported format: {fmt!r}")
        blueprint_id = _validate_uuid("blueprint_id", blueprint_id)
        params: dict[str, Any] = {}
        if scale is not None:
            params["scale"] = scale
        if transparent is not None:
            params["transparent"] = "true" if transparent else "false"
        response = await self._request(
            "GET", f"/blueprint/{blueprint_id}/{_EXPORT_FORMATS[fmt]}", params=params
        )
        return response.content

    async def export_blueprint_budget(
        self,
        blueprint_id: str,
        fmt: str,
        *,
        currency: str | None = None,
        period: str | None = None,
        rate: str | None = None,
    ) -> bytes:
        if fmt not in _BUDGET_FORMATS:
            raise ValueError(f"unsupported format: {fmt!r}")
        blueprint_id = _validate_uuid("blueprint_id", blueprint_id)
        params = {
            key: value
            for key, value in (("currency", currency), ("period", period), ("rate", rate))
            if value is not None
        }
        response = await self._request(
            "GET", f"/blueprint/{blueprint_id}/budget/{fmt}", params=params
        )
        return response.content

    # ---- teams --------------------------------------------------------------
    async def list_teams(self) -> dict[str, Any]:
        return await self._request_json("GET", "/team", envelope="teams")

    # ---- live-scan snapshots --------------------------------------------------
    async def _snapshot(
        self,
        provider: str,
        account_id: str,
        region: str,
        *,
        filter: str | None,
        exclude: list[str] | None,
    ) -> dict[str, Any]:
        """GET /{provider}/account/{id}/{region}/json — a 202 body means retry."""
        account_id = _validate_uuid("account_id", account_id)
        params: dict[str, Any] = {}
        if filter is not None:
            params["filter"] = filter
        if exclude:
            params["exclude"] = ",".join(_validate_service(entry) for entry in exclude)
        return await self._request_json(
            "GET", f"/{provider}/account/{account_id}/{region}/json", params=params
        )

    async def list_aws_accounts(self) -> dict[str, Any]:
        return await self._request_json("GET", "/aws/account", envelope="accounts")

    async def snapshot_aws(
        self,
        account_id: str,
        region: str,
        *,
        filter: str | None = None,
        exclude: list[str] | None = None,
    ) -> dict[str, Any]:
        region = _validate_region(region)
        return await self._snapshot("aws", account_id, region, filter=filter, exclude=exclude)

    async def list_azure_accounts(self) -> dict[str, Any]:
        return await self._request_json("GET", "/azure/account", envelope="accounts")

    async def snapshot_azure(
        self,
        account_id: str,
        region: str,
        *,
        filter: str | None = None,
        exclude: list[str] | None = None,
    ) -> dict[str, Any]:
        region = _validate_azure_region(region)
        return await self._snapshot(
            "azure", account_id, region, filter=filter, exclude=exclude
        )
