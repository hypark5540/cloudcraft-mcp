<!-- mcp-name: io.github.hypark5540/cloudcraft-mcp -->

# cloudcraft-mcp

[![CI](https://github.com/hypark5540/cloudcraft-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/hypark5540/cloudcraft-mcp/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/hypark5540/cloudcraft-mcp/branch/main/graph/badge.svg)](https://codecov.io/gh/hypark5540/cloudcraft-mcp)
[![PyPI](https://img.shields.io/pypi/v/cloudcraft-mcp)](https://pypi.org/project/cloudcraft-mcp/)
[![npm](https://img.shields.io/npm/v/%40hypark5540%2Fcloudcraft-mcp)](https://www.npmjs.com/package/@hypark5540/cloudcraft-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Unofficial Model Context Protocol (MCP) server for
[Cloudcraft](https://cloudcraft.co) — list, read, export, and build cloud
architecture blueprints from Claude Desktop and other MCP clients.

## Features

Nine tools exposed to the MCP host:

| Tool | Description |
| ---- | ----------- |
| `whoami` | Return the Cloudcraft user profile for the configured key. |
| `list_blueprints` | List every blueprint in the account. |
| `get_blueprint` | Fetch a blueprint's full node / edge JSON. |
| `create_blueprint` | Create a new blueprint from a JSON payload. |
| `update_blueprint` | Replace an existing blueprint's payload. |
| `delete_blueprint` | Delete a blueprint (irreversible). |
| `export_blueprint_image` | Render a blueprint to PNG / SVG / PDF / mxgraph on disk. |
| `list_aws_accounts` | List AWS accounts connected for live-scan snapshots. |
| `snapshot_aws` | Take a live-scan snapshot of one AWS service. |

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) for the
  recommended `uvx` and npm launchers
- Node.js 22+ only when using the npm launcher
- Cloudcraft API key — generate one at <https://app.cloudcraft.co/> → User settings → API keys

## Install

Use an immutable version in client configuration so upgrades are deliberate.

| Channel | Command |
| ------- | ------- |
| PyPI / uvx | `uvx --from cloudcraft-mcp==0.1.6 cloudcraft-mcp` |
| pipx | `pipx run --spec cloudcraft-mcp==0.1.6 cloudcraft-mcp` |
| npm / npx | `npx -y @hypark5540/cloudcraft-mcp@0.1.6` |
| Docker / GHCR | `docker run --rm -i -e CLOUDCRAFT_API_KEY ghcr.io/hypark5540/cloudcraft-mcp:0.1.6` |
| Claude Desktop | Download `cloudcraft-mcp.mcpb` from the matching GitHub release |

`uvx` is delivered by the PyPI package; there is no separate uvx registry.
The npm package embeds the byte-identical Python wheel and invokes it through
`uv`, so the npm path requires both Node.js and uv. It does not download code
in a `postinstall` hook.

For development from a checkout:

```bash
git clone https://github.com/hypark5540/cloudcraft-mcp.git
cd cloudcraft-mcp
export CLOUDCRAFT_API_KEY='your-key-here'
uv run --frozen cloudcraft-mcp   # Ctrl+C to exit
```

## Claude Desktop integration

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then add
this entry to Claude Desktop's configuration. Prefer Claude's secret storage
when available; the literal below is only a portable example.

```json
{
  "mcpServers": {
    "cloudcraft": {
      "command": "uv",
      "args": [
        "tool",
        "run",
        "--isolated",
        "--from",
        "cloudcraft-mcp==0.1.6",
        "cloudcraft-mcp"
      ],
      "env": {
        "CLOUDCRAFT_API_KEY": "your-key-here",
        "CLOUDCRAFT_ENABLE_WRITES": "false",
        "CLOUDCRAFT_ENABLE_DELETES": "false"
      }
    }
  }
}
```

Restart Claude Desktop. The Developer tab should show `cloudcraft` as connected.

See [client setup](docs/clients.md) for Cursor, Gemini CLI, npm, Docker, and
MCPB examples.

### Environment variables

| Name | Required | Default | Purpose |
| ---- | -------- | ------- | ------- |
| `CLOUDCRAFT_API_KEY` | yes | — | API key (Bearer). Generated in Cloudcraft User settings. |
| `CLOUDCRAFT_BASE_URL` | no | `https://api.cloudcraft.co` | Override for proxies or future API versions. |
| `CLOUDCRAFT_LOG_LEVEL` | no | `WARNING` | Stderr log verbosity (`DEBUG` / `INFO` / `WARNING` / `ERROR`). |
| `CLOUDCRAFT_EXPORT_DIR` | no | private temp subdirectory | Directory that `export_blueprint_image` may write under. |
| `CLOUDCRAFT_ENABLE_WRITES` | no | `false` | Permit `create_blueprint` and `update_blueprint`. |
| `CLOUDCRAFT_ENABLE_DELETES` | no | `false` | Permit deletes when writes are also enabled. |
| `CLOUDCRAFT_MAX_RESPONSE_BYTES` | no | `26214400` | Reject oversized Cloudcraft responses before they exhaust memory or disk. |

## Usage examples (in Claude)

Once the server is connected, ask Claude things like:

> *"List my Cloudcraft blueprints and summarize what each represents."*

> *"Export blueprint `f0086b32-...` as PNG and save it to my Desktop."*

> *"Take the architecture I just designed and create a new Cloudcraft blueprint called 'Prod 2026'."*

> *"Snapshot the EC2 instances in `ap-northeast-2` for my connected AWS account."*

## Blueprint payload shape

`create_blueprint` / `update_blueprint` accept the full Cloudcraft `data` object. A minimal payload:

```json
{
  "grid": "infinite",
  "projection": "isometric",
  "theme": {"base": "light"},
  "version": 6,
  "nodes": [
    {"id": "...", "type": "ec2", "mapPos": [3, 3], "region": "ap-northeast-2",
     "instanceType": "m7g", "instanceSize": "large", "platform": "linux"},
    {"id": "...", "type": "s3",  "mapPos": [1, 8], "region": "ap-northeast-2",
     "volumeType": "Standard", "dataGb": 100}
  ],
  "edges": [
    {"from": "...ec2-id...", "to": "...s3-id...", "type": "edge",
     "width": 2, "dashed": false, "endCap": "arrow"}
  ],
  "groups": [], "surfaces": [], "text": [], "icons": [],
  "connectors": [], "images": [], "disabledLayers": [],
  "shareDocs": false
}
```

Refer to [Cloudcraft's API docs](https://developers.cloudcraft.co/) for the full node-type catalog and service-specific fields.

## Development

```bash
uv sync --extra dev
uv run pytest            # unit tests (no network)
uv run ruff check .      # lint
uv run mypy src          # type check
```

Tests mock the HTTP layer with [respx](https://lundberg.github.io/respx/) so no API key is required.

#### Coverage

CI uploads `coverage.xml` from the Python 3.12 matrix cell to
[Codecov](https://codecov.io/gh/hypark5540/cloudcraft-mcp). The project gate
is **80% or higher** — a PR that drops overall or patch coverage by more
than 1 percentage point below that line fails the Codecov check
(`codecov.yml`).

Run the same report locally:

```bash
uv run pytest --cov=cloudcraft_mcp --cov-report=term-missing --cov-report=xml
```

### Project layout

```
cloudcraft-mcp/
├── src/cloudcraft_mcp/
│   ├── __init__.py
│   ├── __main__.py         # python -m cloudcraft_mcp
│   ├── server.py           # MCP tool definitions (FastMCP)
│   ├── client.py           # CloudcraftClient — async httpx wrapper
│   ├── types.py            # TypedDicts for blueprint payloads
│   └── py.typed
├── tests/
│   └── test_client.py
├── bin/cloudcraft-mcp.mjs # npm-to-uv launcher
├── mcpb/manifest.json     # Claude Desktop bundle metadata
├── server.json            # official MCP Registry metadata
├── package.json           # npm distribution
├── server.py               # back-compat shim -> cloudcraft_mcp.server:main
├── pyproject.toml
├── LICENSE
└── README.md
```

## Design notes

- **Transport / logic split.** `client.py` is a plain async HTTP client you can import from scripts or CLI tools without pulling the MCP runtime. `server.py` only owns the MCP tool surface.
- **Bearer-token auth.** Cloudcraft's API expects `Authorization: Bearer <key>` (not `Apikey`). The client sets this automatically.
- **No secrets in process args.** The API key is read from `CLOUDCRAFT_API_KEY`; never pass it on the command line.
- **One implementation.** PyPI, npm, MCPB, and the container all launch the
  same versioned Python package rather than maintaining language-specific forks.
- **Error surface.** Non-2xx responses raise `CloudcraftError` with status and body preserved, re-wrapped as `RuntimeError` at the MCP boundary so Claude sees a readable message.

## Security

- API keys grant full read / write over your Cloudcraft account. Treat them as secrets and rotate regularly.
- MCP tool annotations mark read-only tools and mutating/destructive tools so compatible hosts can present better approval prompts. These annotations are hints, not an enforcement layer.
- Environment gates and exact-ID delete confirmation are defense in depth, not
  an interactive approval workflow; keep the MCP host's tool approval UX enabled.
- Cloudcraft mutations are disabled by default. Set `CLOUDCRAFT_ENABLE_WRITES=true`
  only for clients that need create/update access. Deletes additionally require
  `CLOUDCRAFT_ENABLE_DELETES=true` and an exact repeated blueprint ID on every call.
- `delete_blueprint` is irreversible — when asking Claude to delete, be explicit about the target id.
- `export_blueprint_image` writes are sandboxed under `CLOUDCRAFT_EXPORT_DIR`
  (a process-private temporary subdirectory by default) and refuse to overwrite
  existing files unless `overwrite=True`.
- For read-heavy setups, create a dedicated Cloudcraft user with read-only scope (if/when Cloudcraft adds scoped keys) and use that key for MCP.
- Supported versions and private reporting instructions are in
  [SECURITY.md](SECURITY.md); data flow is documented in [PRIVACY.md](PRIVACY.md).

## Contributing

Issues and PRs welcome at <https://github.com/hypark5540/cloudcraft-mcp>. Please run `ruff`, `mypy`, and `pytest` before submitting.

## License

MIT — see [LICENSE](LICENSE).

## Related

- [Cloudcraft API documentation](https://developers.cloudcraft.co/)
- [Model Context Protocol specification](https://modelcontextprotocol.io/)
- [awslabs/mcp](https://github.com/awslabs/mcp) — AWS's collection of MCP servers
- [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) — reference MCP server implementations
