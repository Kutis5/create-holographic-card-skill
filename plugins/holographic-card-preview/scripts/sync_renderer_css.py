#!/usr/bin/env python3
"""Build preview renderer assets from the canonical React card sources."""
from __future__ import annotations
import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT.parents[1] / "create-holographic-card" / "assets" / "react-template"
ASSETS = ROOT / "assets"
FILES = {
    "HolographicCard.module.css": "card-renderer.css",
    "holo-engine.js": "holo-engine.js",
    "frame-palette.js": "frame-palette.js",
    "optical-state.js": "optical-state.js",
    "pointer-motion.js": "pointer-motion.js",
}
TEXTURE_FILES = (
    "clear-coat.webp", "pearl.webp", "brushed-metal.webp", "spectral-lines.webp",
    "etched-holo.webp", "cosmic-flake.webp", "star-holo.webp", "blue-noise.webp", "micro-grain.webp",
    "manifest.json",
)

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    for source_name, destination_name in FILES.items():
        source, destination = TEMPLATE / source_name, ASSETS / destination_name
        if not source.is_file():
            raise SystemExit(f"Canonical renderer asset is missing: {source}")
        destination.write_bytes(source.read_bytes())
        if destination.read_bytes() != source.read_bytes():
            raise SystemExit(f"Renderer asset hash mismatch after sync: {destination}")
        print(f"Synced {source} -> {destination} ({sha256(destination)})")
    texture_source = TEMPLATE / "holo-textures"
    texture_destination = ASSETS / "holo-textures"
    texture_destination.mkdir(parents=True, exist_ok=True)
    for name in TEXTURE_FILES:
        source, destination = texture_source / name, texture_destination / name
        if not source.is_file():
            raise SystemExit(f"Canonical renderer asset is missing: {source}")
        shutil.copy2(source, destination)
        if sha256(destination) != sha256(source):
            raise SystemExit(f"Renderer asset hash mismatch after sync: {destination}")
        print(f"Synced {source} -> {destination} ({sha256(destination)})")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
