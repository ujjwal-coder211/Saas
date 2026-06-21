"""MCP runtime — bridge registered MCP tool definitions to Aksh agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from saas.storage.projects import read_file


def load_project_mcp_config(user_id: str, project_id: str) -> list[dict[str, Any]]:
    for path in (".aksh/mcp.json", "mcp.json", ".cursor/mcp.json"):
        try:
            raw = read_file(user_id, project_id, path)
            data = json.loads(raw)
            servers = data.get("mcpServers") or data.get("servers") or {}
            out = []
            for name, cfg in servers.items():
                if isinstance(cfg, dict):
                    out.append({"id": name, "config": cfg})
            return out
        except Exception:
            continue
    return []


def list_mcp_tools(user_id: str, project_id: str) -> list[dict[str, Any]]:
    """List tools from project MCP config + built-in Aksh tools."""
    servers = load_project_mcp_config(user_id, project_id)
    tools: list[dict[str, Any]] = []
    for srv in servers:
        sid = srv["id"]
        tools.append(
            {
                "server": sid,
                "name": f"{sid}__ping",
                "description": f"Health check for MCP server {sid} (config loaded)",
            }
        )
    tools.extend(
        [
            {"server": "aksh", "name": "read_file", "description": "Read project file"},
            {"server": "aksh", "name": "write_file", "description": "Write project file"},
            {"server": "aksh", "name": "run_terminal", "description": "Run sandboxed shell command"},
        ]
    )
    return tools


def invoke_mcp_tool(
    user_id: str,
    project_id: str,
    tool_name: str,
    args: dict[str, Any],
    *,
    project_root: Path | None,
    run_tool_fn: Any,
) -> dict[str, Any]:
    """
    MCP tool dispatch. Built-in Aksh tools run immediately.
    External MCP servers: config must exist; returns guidance until full stdio bridge is configured.
    """
    if tool_name in ("read_file", "write_file", "grep", "list_files", "run_terminal", "security_scan"):
        return run_tool_fn(tool_name, args, project_root=project_root, allow_write=True)

    servers = load_project_mcp_config(user_id, project_id)
    for srv in servers:
        if tool_name.startswith(srv["id"] + "__"):
            return {
                "ok": True,
                "server": srv["id"],
                "message": (
                    f"MCP server '{srv['id']}' is registered. "
                    "Full stdio MCP execution requires AKSH_MCP_ENABLE=true on server. "
                    "Use built-in Aksh tools for file/terminal operations today."
                ),
                "config_keys": list(srv.get("config", {}).keys()),
            }
    return {"ok": False, "error": f"Unknown MCP tool: {tool_name}"}
