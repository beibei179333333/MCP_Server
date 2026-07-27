"""Entry point for the fleet management MCP server.

Usage::

    python -m mcp_server                 # stdio transport (for Claude Desktop / Claude Code)
    python -m mcp_server --http          # streamable-HTTP transport on 127.0.0.1:8000
    python -m mcp_server --http --host 0.0.0.0 --port 9000
    python -m mcp_server --check         # validate the inventory and exit
    python -m mcp_server --list          # print the configured servers and exit

Stdio is the default because that is how desktop MCP clients launch a local
server (as a subprocess). Use --http to run it once and share it with several
clients / remote agents.
"""
from __future__ import annotations

import argparse
import sys


def _print_inventory() -> int:
    from .manager import ServerManager
    try:
        mgr = ServerManager.from_config()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    inv = mgr.inv
    print(f"inventory: {inv.source_path}")
    print(f"backend:   {mgr.backend.name}   read_only: {inv.read_only}")
    print(f"servers:   {len(inv.servers)}")
    for s in inv.servers:
        tags = f" [{', '.join(s.tags)}]" if s.tags else ""
        print(f"  - {s.name}{tags}: {s.user}@{s.host}:{s.port}  auth={s.public_dict()['auth']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mcp_server", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--http", action="store_true", help="serve over streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1", help="bind host for --http (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="bind port for --http (default 8000)")
    parser.add_argument("--check", action="store_true", help="validate the inventory and exit")
    parser.add_argument("--list", action="store_true", help="print the configured servers and exit")
    args = parser.parse_args(argv)

    if args.check or args.list:
        return _print_inventory()

    # Import here so --check/--list work even if the MCP SDK is absent.
    from .server import mcp
    if args.http:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        # Logs go to stderr; never write to stdout under stdio transport.
        print(f"serving fleet MCP over http://{args.host}:{args.port}{mcp.settings.streamable_http_path}",
              file=sys.stderr)
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
