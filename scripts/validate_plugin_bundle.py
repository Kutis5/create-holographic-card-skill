#!/usr/bin/env python3
"""Validate the self-contained Codex marketplace bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "holographic-card-preview"
EMBEDDED_SKILL = PLUGIN / "skills" / "create-holographic-card"
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    require(marketplace["name"] == "holographic-card-studio", "Unexpected marketplace name")
    entry = marketplace["plugins"][0]
    require(entry["name"] == "holographic-card-preview", "Unexpected plugin ID")
    require(entry["source"] == {"source": "local", "path": "./plugins/holographic-card-preview"}, "Unexpected plugin source")

    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    require(manifest["name"] == "holographic-card-preview", "Plugin ID changed")
    require(manifest["interface"]["displayName"] == "Holographic Card Studio", "Plugin display name is wrong")
    require(manifest["mcpServers"] == "./.mcp.json", "Plugin MCP configuration is missing")
    mcp = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
    require("holographicCardPreview" in mcp["mcpServers"], "Preview MCP server is missing")

    for name in ("SKILL.md", "agents", "assets", "references", "scripts"):
        require((EMBEDDED_SKILL / name).exists(), f"Embedded creation skill is missing {name}")
    require((PLUGIN / "skills" / "preview-holographic-card" / "SKILL.md").is_file(), "Preview skill is missing")
    require((PLUGIN / "mcp" / "server.py").is_file(), "MCP server is missing")

    for parent in ("agents", "assets", "references", "scripts"):
        for source in (ROOT / parent).rglob("*"):
            if not source.is_file() or "__pycache__" in source.parts or source.name == "validate_plugin_bundle.py":
                continue
            target = EMBEDDED_SKILL / source.relative_to(ROOT)
            require(target.is_file(), f"Embedded skill is missing {source.relative_to(ROOT)}")
            require(sha256(source) == sha256(target), f"Embedded skill drift: {source.relative_to(ROOT)}")
    require(sha256(ROOT / "SKILL.md") == sha256(EMBEDDED_SKILL / "SKILL.md"), "Embedded SKILL.md drift")

    renderer = EMBEDDED_SKILL / "assets" / "react-template"
    assets = PLUGIN / "assets"
    for source_name, target_name in {
        "HolographicCard.module.css": "card-renderer.css",
        "holo-engine.js": "holo-engine.js",
        "frame-palette.js": "frame-palette.js",
        "optical-state.js": "optical-state.js",
    }.items():
        require(sha256(renderer / source_name) == sha256(assets / target_name), f"Renderer drift: {source_name}")
    for source in (renderer / "holo-textures").glob("*"):
        if source.is_file():
            target = assets / "holo-textures" / source.name
            require(target.is_file() and sha256(source) == sha256(target), f"Texture drift: {source.name}")

    print("plugin bundle validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
