"""Offline tests for the fleet management MCP server.

No network and no MCP SDK needed: the core logic (inventory, manager) is exercised
with a fake SSH backend that records commands and returns canned results.

Run: python -m pytest tests/test_mcp_server.py -q   (or)   python tests/test_mcp_server.py
"""
import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.backends import ExecResult, build_service_command
from mcp_server.inventory import Server, load_inventory
from mcp_server.manager import FleetError, ServerManager, _parse_status


# ---- helpers ----------------------------------------------------------------
def _write_config(payload: dict) -> str:
    d = tempfile.mkdtemp()
    path = os.path.join(d, "servers.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return path


def _basic_config() -> dict:
    return {
        "defaults": {"user": "root", "port": 22, "key_file": "~/.ssh/id_ed25519"},
        "servers": [
            {"name": "web-1", "host": "10.0.0.11", "tags": ["web", "prod"]},
            {"name": "web-2", "host": "10.0.0.12", "tags": ["web", "prod"]},
            {"name": "db-1", "host": "10.0.0.31", "tags": ["db", "prod"], "user": "ubuntu"},
        ],
    }


class FakeBackend:
    """Records every command and returns a scripted or default result."""
    name = "fake"

    def __init__(self, scripted=None):
        self.calls = []                 # list of (server_name, command, timeout)
        self.scripted = scripted or {}  # command-substring -> ExecResult factory

    async def execute(self, server: Server, command: str, timeout: int) -> ExecResult:
        self.calls.append((server.name, command, timeout))
        for needle, factory in self.scripted.items():
            if needle in command:
                return factory(server)
        return ExecResult(server=server.name, ok=True, exit_status=0,
                          stdout=f"ran on {server.name}", duration_s=0.01)


def _mgr(config=None, backend=None, **inv_over):
    path = _write_config(config or _basic_config())
    inv = load_inventory(path)
    for k, v in inv_over.items():
        setattr(inv, k, v)
    return ServerManager(inv, backend=backend or FakeBackend())


def _run(coro):
    return asyncio.run(coro)


# ---- inventory --------------------------------------------------------------
def test_inventory_defaults_and_merge():
    inv = load_inventory(_write_config(_basic_config()))
    assert len(inv.servers) == 3
    web1 = inv.by_name("web-1")
    assert web1.user == "root" and web1.port == 22           # from defaults
    assert web1.key_file.endswith("id_ed25519")              # expanded/inherited
    assert inv.by_name("db-1").user == "ubuntu"              # per-server override


def test_inventory_password_from_env(monkeypatch=None):
    os.environ["SERVERS_MCP_PASSWORD_WEB_1"] = "s3cret"
    try:
        inv = load_inventory(_write_config(_basic_config()))
        assert inv.by_name("web-1").password == "s3cret"
        # secret is never exposed in the public view
        assert "password" not in inv.by_name("web-1").public_dict()
        assert inv.by_name("web-1").public_dict()["auth"] == "password"
    finally:
        del os.environ["SERVERS_MCP_PASSWORD_WEB_1"]


def test_inventory_rejects_unknown_key():
    cfg = _basic_config()
    cfg["servers"][0]["hostt"] = "typo"
    try:
        load_inventory(_write_config(cfg))
        assert False, "expected ValueError for unknown key"
    except ValueError as e:
        assert "unknown key" in str(e)


def test_inventory_rejects_duplicate_and_missing_host():
    dup = _basic_config()
    dup["servers"].append({"name": "web-1", "host": "10.0.0.99"})
    try:
        load_inventory(_write_config(dup))
        assert False
    except ValueError as e:
        assert "duplicate" in str(e)
    missing = {"servers": [{"name": "x"}]}
    try:
        load_inventory(_write_config(missing))
        assert False
    except ValueError as e:
        assert "host" in str(e)


def test_missing_file_message():
    try:
        load_inventory("/nonexistent/servers.json")
        assert False
    except FileNotFoundError as e:
        assert "no inventory file found" in str(e)


# ---- selector resolution ----------------------------------------------------
def test_resolve_targets():
    inv = load_inventory(_write_config(_basic_config()))
    assert [s.name for s in inv.resolve_targets("all")] == ["web-1", "web-2", "db-1"]
    assert [s.name for s in inv.resolve_targets("web")] == ["web-1", "web-2"]
    assert [s.name for s in inv.resolve_targets("db-1")] == ["db-1"]
    # comma list, dedup preserved
    assert [s.name for s in inv.resolve_targets("web,db-1,web-1")] == ["web-1", "web-2", "db-1"]
    try:
        inv.resolve_targets("nope")
        assert False
    except KeyError as e:
        assert "no server matched" in str(e)


# ---- manager: read ops ------------------------------------------------------
def test_list_servers_hides_secrets():
    mgr = _mgr()
    rows = mgr.list_servers()
    assert len(rows) == 3
    assert all("password" not in r for r in rows)
    assert [r["name"] for r in mgr.list_servers(tag="web")] == ["web-1", "web-2"]


def test_status_parsing_and_call():
    def status_factory(server):
        body = ("# host\n" + server.name + "\n# uptime\nup 1 day\n"
                "# load\n0.1 0.2 0.3\n# mem\nMem: 8G\n# disk\n/ 40% \n# top\nproc a\n")
        return ExecResult(server=server.name, ok=True, exit_status=0, stdout=body)
    mgr = _mgr(backend=FakeBackend({"# host": status_factory}))
    res = _run(mgr.get_status("web-1"))
    assert res["ok"] and res["sections"]["uptime"] == "up 1 day"
    assert res["sections"]["host"] == "web-1"


def test_parse_status_unit():
    body = "# host\nh1\n# load\n0.5\n"
    sec = _parse_status(body)
    assert sec == {"host": "h1", "load": "0.5"}


def test_tail_logs_builds_commands():
    mgr = _mgr()
    _run(mgr.tail_logs("web-1", path="/var/log/nginx/error.log", lines=50))
    assert mgr.backend.calls[-1][1] == "tail -n 50 /var/log/nginx/error.log"
    _run(mgr.tail_logs("web-1", unit="nginx", lines=10))
    assert "journalctl -u nginx -n 10 --no-pager" in mgr.backend.calls[-1][1]
    try:
        _run(mgr.tail_logs("web-1"))
        assert False
    except FleetError as e:
        assert "path" in str(e) and "unit" in str(e)


# ---- manager: write ops -----------------------------------------------------
def test_run_command_ok():
    mgr = _mgr()
    res = _run(mgr.run_command("web-1", "uptime"))
    assert res["ok"] and res["server"] == "web-1"
    assert mgr.backend.calls == [("web-1", "uptime", 60)]


def test_run_command_unknown_server():
    mgr = _mgr()
    try:
        _run(mgr.run_command("ghost", "ls"))
        assert False
    except FleetError as e:
        assert "unknown server 'ghost'" in str(e)


def test_run_on_group_fanout():
    mgr = _mgr()
    res = _run(mgr.run_on_group("prod", "hostname"))
    assert res["count"] == 3 and res["succeeded"] == 3 and res["failed"] == 0
    assert {c[0] for c in mgr.backend.calls} == {"web-1", "web-2", "db-1"}


def test_run_on_group_counts_failures():
    def fail_db(server):
        if server.name == "db-1":
            return ExecResult(server=server.name, ok=False, exit_status=1, stderr="boom")
        return ExecResult(server=server.name, ok=True, exit_status=0, stdout="ok")
    mgr = _mgr(backend=FakeBackend({"hostname": fail_db}))
    res = _run(mgr.run_on_group("all", "hostname"))
    assert res["succeeded"] == 2 and res["failed"] == 1


def test_readonly_blocks_mutations():
    mgr = _mgr(read_only=True)
    for coro in (mgr.run_command("web-1", "reboot"),
                 mgr.run_on_group("all", "reboot"),
                 mgr.service_action("web-1", "nginx", "restart")):
        try:
            _run(coro)
            assert False, "expected read-only refusal"
        except FleetError as e:
            assert "read-only" in str(e)
    # read-only service actions are still allowed
    res = _run(mgr.service_action("web-1", "nginx", "status"))
    assert res["action"] == "status"


def test_deny_patterns_block():
    cfg = _basic_config()
    cfg["defaults"]["deny_patterns"] = [r"rm\s+-rf\s+/"]
    mgr = _mgr(config=cfg)
    try:
        _run(mgr.run_command("web-1", "rm -rf /"))
        assert False
    except FleetError as e:
        assert "deny pattern" in str(e)
    # a normal command still runs
    assert _run(mgr.run_command("web-1", "ls"))["ok"]


def test_service_action_validation_and_build():
    mgr = _mgr()
    try:
        _run(mgr.service_action("web-1", "nginx", "frobnicate"))
        assert False
    except FleetError as e:
        assert "unsupported service action" in str(e)
    _run(mgr.service_action("web-1", "nginx", "restart"))
    assert mgr.backend.calls[-1][1] == "systemctl restart nginx"


def test_build_service_command_sudo_and_quoting():
    assert build_service_command("restart", "nginx", False) == "systemctl restart nginx"
    assert build_service_command("restart", "nginx", True) == "sudo -n systemctl restart nginx"
    # a service name with a space is shell-quoted
    assert "'weird name'" in build_service_command("status", "weird name", False)


def test_empty_command_rejected():
    mgr = _mgr()
    for coro in (mgr.run_command("web-1", "   "), mgr.run_on_group("all", "")):
        try:
            _run(coro)
            assert False
        except FleetError as e:
            assert "empty" in str(e)


def test_wizard_helpers():
    from mcp_server.wizard import _sanitize_env_name, _shell_quote
    assert _sanitize_env_name("web-1") == "WEB_1"
    assert _sanitize_env_name("staging.db 2") == "STAGING_DB_2"
    # single-quoting must survive an embedded quote so `source` round-trips it
    assert _shell_quote("simple") == "'simple'"
    assert _shell_quote("p@ss'w0rd") == "'p@ss'\"'\"'w0rd'"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
