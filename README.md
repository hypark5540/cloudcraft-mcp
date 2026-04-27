# cloudcraft-mcp

[![CI](https://github.com/hypark5540/cloudcraft-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/hypark5540/cloudcraft-mcp/actions/workflows/ci.yml)
[![tests](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/hypark5540/<GIST_ID>/raw/cloudcraft-mcp-tests.json)](https://github.com/hypark5540/cloudcraft-mcp/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/hypark5540/cloudcraft-mcp/branch/main/graph/badge.svg)](https://codecov.io/gh/hypark5540/cloudcraft-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Model Context Protocol (MCP) server for [Cloudcraft.co](https://cloudcraft.co) — list, read, export, and build cloud-architecture blueprints from Claude Desktop and other MCP clients.

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

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (`brew install uv`)
- Cloudcraft API key — generate one at <https://app.cloudcraft.co/> → User settings → API keys

## Install

Clone the repo and let `uv` resolve dependencies on first run — no explicit install step required.

```bash
git clone https://github.com/hypark5540/cloudcraft-mcp.git
cd cloudcraft-mcp
export CLOUDCRAFT_API_KEY='your-key-here'
uv run cloudcraft-mcp   # smoke test — Ctrl+C to exit
```

## Claude Desktop integration

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the equivalent on your platform:

```json
{
  "mcpServers": {
    "cloudcraft": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/cloudcraft-mcp",
        "run",
        "cloudcraft-mcp"
      ],
      "env": {
        "CLOUDCRAFT_API_KEY": "your-key-here"
      }
    }
  }
}
```

Restart Claude Desktop. The Developer tab should show `cloudcraft` as connected.

### Environment variables

| Name | Required | Default | Purpose |
| ---- | -------- | ------- | ------- |
| `CLOUDCRAFT_API_KEY` | yes | — | API key (Bearer). Generated in Cloudcraft User settings. |
| `CLOUDCRAFT_BASE_URL` | no | `https://api.cloudcraft.co` | Override for proxies or future API versions. |
| `CLOUDCRAFT_LOG_LEVEL` | no | `WARNING` | Stderr log verbosity (`DEBUG` / `INFO` / `WARNING` / `ERROR`). |

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
├── server.py               # back-compat shim -> cloudcraft_mcp.server:main
├── pyproject.toml
├── LICENSE
└── README.md
```

## Design notes

- **Transport / logic split.** `client.py` is a plain async HTTP client you can import from scripts or CLI tools without pulling the MCP runtime. `server.py` only owns the MCP tool surface.
- **Bearer-token auth.** Cloudcraft's API expects `Authorization: Bearer <key>` (not `Apikey`). The client sets this automatically.
- **No secrets in process args.** The API key is read from `CLOUDCRAFT_API_KEY`; never pass it on the command line.
- **Error surface.** Non-2xx responses raise `CloudcraftError` with status and body preserved, re-wrapped as `RuntimeError` at the MCP boundary so Claude sees a readable message.

## Security

- API keys grant full read / write over your Cloudcraft account. Treat them as secrets and rotate regularly.
- `delete_blueprint` is irreversible — when asking Claude to delete, be explicit about the target id.
- For read-heavy setups, create a dedicated Cloudcraft user with read-only scope (if/when Cloudcraft adds scoped keys) and use that key for MCP.

## Contributing

Issues and PRs welcome at <https://github.com/hypark5540/cloudcraft-mcp>. Please run `ruff`, `mypy`, and `pytest` before submitting.

## License

MIT — see [LICENSE](LICENSE).

## Related

- [Cloudcraft API documentation](https://developers.cloudcraft.co/)
- [Model Context Protocol specification](https://modelcontextprotocol.io/)
- [awslabs/mcp](https://github.com/awslabs/mcp) — AWS's collection of MCP servers
- [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) — reference MCP server implementations
