"""Backward-compatibility shim.

Previous versions of this project exposed the MCP server at the repo root as
``server.py``. The canonical entry point is now ``cloudcraft_mcp.server:main``.
This shim keeps the old ``uv run server.py`` command working so existing
``claude_desktop_config.json`` entries continue to function after upgrading.

Prefer the new forms in new configs:

    uv run cloudcraft-mcp
    # or
    python -m cloudcraft_mcp
"""
from __future__ import annotations

from cloudcraft_mcp.server import main

if __name__ == "__main__":
    main()
