"""HTTP client wrapping the Cloudcraft REST API.

Keeps the transport layer separate from MCP tool definitions so the client
can be unit-tested with respx and reused from non-MCP contexts (scripts,
CLI, etc.).
"""
from __future__ import annotations

import logging
from typing import Any, cast
from collections.abc import Mapping


__all__ = ["CloudcraftClient", "CloudcraftError"]

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.cloudcraft.co"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class CloudcraftError(RuntimeError):
    """Raised when the Cloudcraft API returns a non-2xx response."""

    def __init__(self, status: int, body: str, method: str, url: str) -> None:
        super().__init__(f"{method} {url} -> {status}: {body}")
        self.status = status
        self.body = body


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
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        self._timeout = timeout if timeout is not None else DEFAULT_TIMEOUT

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
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            logger.debug("%s %s", method, url)
            response = await client.request(
                method, url, headers=headers, params=params, json=json
            )
        if response.status_code >= 400:
            raise CloudcraftError(
                status=response.status_code,
                body=response.text,
                method=method,
                url=url,
            )
        return response

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._request(method, path, params=params, json=json)
        try:
            data = response.json()
        except ValueError as exc:
            raise CloudcraftError(
                status=response.status_code,
                body=f"invalid JSON body: {exc}",
                method=method,
                url=f"{self._base_url}{path}",
            ) from exc
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
        return await self._request_json("GET", "/blueprint")

    async def get_blueprint(self, blueprint_id: str) -> dict[str, Any]:
        return await self._request_json("GET", f"/blueprint/{blueprint_id}")

    async def create_blueprint(self, data: Mapping[str, Any]) -> dict[str, Any]:
        return await self._request_json(
            "POST", "/blueprint", json={"data": dict(data)}
        )

    async def update_blueprint(
        self, blueprint_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]:
        return await self._request_json(
            "PUT", f"/blueprint/{blueprint_id}", json={"data": dict(data)}
        )

    async def delete_blueprint(self, blueprint_id: str) -> None:
        await self._request("DELETE", f"/blueprint/{blueprint_id}")

    async def export_blueprint(
        self,
        blueprint_id: str,
        fmt: str,
        *,
        scale: float | None = None,
        transparent: bool | None = None,
    ) -> bytes:
        if fmt not in ("png", "svg", "pdf", "mxgraph"):
            raise ValueError(f"unsupported format: {fmt!r}")
        params: dict[str, Any] = {}
        if scale is not None:
            params["scale"] = scale
        if transparent is not None:
            params["transparent"] = "true" if transparent else "false"
        response = await self._request(
            "GET", f"/blueprint/{blueprint_id}/{fmt}", params=params
        )
        return response.content

    # ---- aws live-scan ------------------------------------------------------
    async def list_aws_accounts(self) -> dict[str, Any]:
        return await self._request_json("GET", "/aws/account")

    async def snapshot_aws(
        self, account_id: str, region: str, service: str
    ) -> dict[str, Any]:
        return await self._request_json(
            "GET", f"/aws/account/{account_id}/snapshot/{region}/{service}"
        )
