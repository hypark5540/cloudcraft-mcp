# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.1]: https://github.com/hypark5540/cloudcraft-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/hypark5540/cloudcraft-mcp/releases/tag/v0.1.0
