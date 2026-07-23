"""Command-line entry point for the Cloudcraft MCP server."""
from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__


def main(argv: Sequence[str] | None = None) -> None:
    """Parse informational flags before importing the API-key-gated server."""
    parser = argparse.ArgumentParser(
        prog="cloudcraft-mcp",
        description="Run the unofficial Cloudcraft MCP server over stdio.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"cloudcraft-mcp {__version__}",
    )
    parser.parse_args(argv)

    # Import lazily so --help and --version work without CLOUDCRAFT_API_KEY.
    from .server import main as run_server

    run_server()

if __name__ == "__main__":
    main()
