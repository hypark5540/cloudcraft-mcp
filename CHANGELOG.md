# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-04-29

### Security
- **Harden HTTPS allowlist against substring-prefix bypass**
- Reject http://localhost.* / http://127.0.0.1.* lookalikes via urlparse


## [0.1.3] - 2026-04-23

### Security
- **Path-traversal hardening in ``export_blueprint_image``.** Writes are now
  constrained to a single export root directory (system temp dir by default,
  overridable via the ``CLOUDCRAFT_EXPORT_DIR`` environment variable). Both
  the caller-supplied ``output_path`` and the default filename are resolved
  and verified to be strictly under that root before any bytes are written.
  A new ``overwrite: bool = False`` parameter stops the tool from silently
  clobbering an existing file. Together this closes a prompt-injection hole
  where an LLM could direct a PNG/SVG payload at ``~/.ssh/authorized_keys``
  or other arbitrary paths.
- **Path-segment validation on all URL-building client methods.** httpx
  normalises ``..`` segments in URL paths per RFC 3986 before dispatching
  the request, which meant an attacker-controlled ``blueprint_id`` of
  ``"../user/me"`` would reach the upstream as ``GET /user/me`` and let the
  caller pivot to Cloudcraft endpoints this MCP server does not expose.
  ``blueprint_id`` and ``account_id`` are now UUID-validated, ``region``
  matches an AWS region regex, and ``service`` matches a short lowercase
  slug regex. Invalid inputs raise ``ValueError`` before any HTTP call.
- **Error-body truncation and Bearer-token redaction.** ``_format_error``
  caps the upstream response body at 500 characters and replaces anything
  matching ``Bearer <token>`` with ``Bearer ***`` before surfacing it to
  the MCP host, so an Authorization header echoed in a 4xx body can no
  longer leak the live API key into the LLM context.
- **HTTPS enforcement on ``CLOUDCRAFT_BASE_URL``.** A tampered env var can
  no longer silently downgrade Bearer-token traffic to cleartext; non-
  ``https://`` values are rejected at startup. ``http://localhost`` and
  ``http://127.0.0.1`` remain allowed for local proxy / mock-server testing.

### Added
- ``CLOUDCRAFT_EXPORT_DIR`` environment variable to control where
  ``export_blueprint_image`` may write.
- ``overwrite`` parameter on ``export_blueprint_image`` (default ``False``).
- Unit tests for all new input-validation and redaction paths.

### Changed
- ``get_blueprint``, ``update_blueprint``, ``delete_blueprint``, and
  ``snapshot_aws`` now translate ``ValueError`` from client-side validation
  into a ``RuntimeError`` with a human-readable message, matching the
  existing pattern used by ``export_blueprint_image``.

### Fixed
- ``CHANGELOG`` note for 0.1.2 incorrectly read ``astral-sh/setup-uv@v5``
  whereas both workflows actually bumped to ``@v6``.

## [0.1.2] - 2026-04-22

### Fixed
- Restored missing ``import httpx`` in ``client.py`` — prior 0.1.1 candidate
  would have failed at import time on every install (build succeeded but
  runtime ``NameError`` on ``httpx.Timeout``).
- Corrected ``tests/test_server_startup.py`` regression guard: the old
  ``__mro_entries__`` check raised ``AttributeError`` on completed TypedDict
  classes. Replaced with a direct ``pydantic.TypeAdapter(BlueprintData)``
  probe that reproduces the exact FastMCP tool-registration codepath.

### Changed
- Synchronised ``cloudcraft_mcp.__version__`` with ``pyproject.toml``.
- Bumped ``astral-sh/setup-uv`` to ``@v6`` in ``publish.yml`` (matches CI).

## [0.1.1] - 2026-04-22

### Added
- `CloudcraftClient._request_json` helper that centralises JSON parsing,
  validates the body is a JSON object, and raises `CloudcraftError` on
  malformed payloads or unexpected shapes (previously such cases would
  surface later as `KeyError` / `TypeError` in tool code).
- PyPI Trusted Publishing workflow (`.github/workflows/publish.yml`) — pushing
  a `v*.*.*` tag now builds and publishes the package to PyPI via OIDC,
  no API tokens required.

### Changed
- `create_blueprint` and `update_blueprint` now accept `Mapping[str, Any]`
  for the `data` parameter instead of `dict[str, Any]`. This is a
  source-compatible widening — existing `dict` callers keep working, and
  read-only mappings (`TypedDict`, `MappingProxyType`, etc.) are now accepted.
- All seven JSON-returning client methods (`whoami`, `list_blueprints`,
  `get_blueprint`, `create_blueprint`, `update_blueprint`,
  `list_aws_accounts`, `snapshot_aws`) route through `_request_json`,
  removing duplicated `cast(dict[str, Any], response.json())` boilerplate
  and gaining the shape guard for free.

### Fixed
- Stricter typing — `response.json()` is no longer returned as bare `Any`,
  silencing mypy `warn_return_any` and preventing a class of "wrong shape
  from upstream" bugs from leaking into MCP tool handlers.

### Notes
- No behaviour change for `delete_blueprint` (no body) or `export_blueprint`
  (returns `bytes`); both still go through `_request` directly.
- Cloudcraft API envelope (`json={"data": ...}`) is preserved.

## [0.1.0] - 2026-04-22

### Added
- Initial public release.
- `CloudcraftClient` async HTTP wrapper for the Cloudcraft REST API
  (Bearer auth, configurable base URL and timeout).
- MCP server exposing blueprint CRUD (`list_blueprints`, `get_blueprint`,
  `create_blueprint`, `update_blueprint`, `delete_blueprint`),
  blueprint export (`export_blueprint` — png/svg/pdf/mxgraph), AWS
  live-scan (`list_aws_accounts`, `snapshot_aws`), and a `whoami`
  identity probe.
- `cloudcraft-mcp` console script entry point.
- Project metadata, MIT license, and CI workflow.

[0.1.3]: https://github.com/hypark5540/cloudcraft-mcp/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/hypark5540/cloudcraft-mcp/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/hypark5540/cloudcraft-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/hypark5540/cloudcraft-mcp/releases/tag/v0.1.0
