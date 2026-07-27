"""fleet server-management MCP server.

Exposes a fleet of SSH-reachable servers to Claude (or any MCP client) as a set
of management tools: list / health-check / status / run-command / run-across-a-
group / service-control / tail-logs.

The package is split so the core logic never imports the MCP SDK, which keeps it
unit-testable without a running client:

  * ``inventory``  – load & validate the server list (no network, no SDK)
  * ``backends``   – pluggable SSH execution (paramiko or the system ``ssh``)
  * ``manager``    – high-level operations returning plain dicts
  * ``server``     – the thin FastMCP tool layer (imports ``mcp``)
"""

from .inventory import Inventory, Server, load_inventory

__all__ = ["Inventory", "Server", "load_inventory"]
__version__ = "0.1.0"
