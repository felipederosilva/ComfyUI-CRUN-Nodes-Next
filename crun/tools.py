"""AI Tools metadata drawn from the same local catalog as the Comfy nodes.

This workspace index is read-only. A documented node is not proof of account
entitlement, upstream availability, or a successfully tested paid operation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .catalog import list_catalog


def list_tools(snapshot: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """List every documented tool, without querying CRUN or reading credentials.

    Tool controls are available through model-specific Comfy nodes in prepare
    mode by default. No operation can be submitted by these metadata cards.
    Rights-sensitive operations retain an explicit authorized-use reminder.
    """
    catalog = list_catalog() if snapshot is None else snapshot
    tools = []
    for entry in catalog.get("entries", []):
        if entry.get("kind") != "tool":
            continue
        identifier = str(entry.get("id") or "")
        model = str(entry.get("model") or "")
        title = str(entry.get("title") or model or identifier)
        provider = str(entry.get("provider") or "CRUN")
        schema = deepcopy(entry.get("inputs") or entry.get("input_schema") or {})
        description = str(schema.get("description") or "Inspect this tool's documented inputs in its model-specific Comfy node.")
        rights_sensitive = "face-swap" in model or "watermark" in model
        tools.append({
            "id": identifier,
            "model": model,
            "name": title,
            "provider": provider,
            "category": str(entry.get("group") or "AI Tools"),
            "description": description,
            "documentation_url": str(entry.get("documentation_url") or ""),
            "status": "node_available",
            "availability": str(entry.get("availability") or "documented_not_account_verified"),
            "node_menu": f"CRUN Next/AI Tools/{provider}",
            "node_display_name": "CRUN • " + title,
            "default_mode": "prepare",
            "workspace_execution_enabled": False,
            "input_schema": schema,
            "rights_sensitive": rights_sensitive,
            "usage_note": "Use only media, likenesses and modifications you are authorized to use." if rights_sensitive else "Paid execution requires explicit enablement in the corresponding Comfy node.",
        })
    return tools
