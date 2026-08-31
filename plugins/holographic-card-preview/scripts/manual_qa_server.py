#!/usr/bin/env python3
"""Launch the production preview renderer for manual Browser QA."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import threading
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def load_server():
    spec = importlib.util.spec_from_file_location("holo_manual_qa_server", ROOT / "mcp" / "server.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def presentation(material: str) -> dict:
    return {
        "version": 2,
        "frame": {"style": "narrow", "width": 0.65, "color": "#75808f", "colorMode": "image"},
        "radius": {"outer": 5.8},
        "surface": {"color": "#070a0f", "accent": "#a7d9e8", "material": material},
        "foil": {"enabled": True, "target": "background", "colors": ["#ff5470", "#ffcc66", "#50e3c2", "#5cb8ff", "#8f7cff", "#ef7dff"], "intensity": 0.78},
        "texture": {"kind": "micro-grain", "target": "background", "intensity": 0.32 if material == "star-holo" else 0.48},
        "sparkle": {"enabled": material in {"clear-coat", "pearl", "cosmic-flake"}, "target": "background", "intensity": 0.3},
        "glare": {"enabled": True, "target": "surface", "intensity": 0.52 if material == "star-holo" else 0.62},
        "depth": {"parallaxX": 1.45, "parallaxY": 1.25, "lift": 19, "shadowOpacity": 0.18, "shadowBlur": 16, "rimIntensity": 0.12},
        "motion": {"maxX": 14, "maxY": 14, "scale": 1.024, "smoothing": 0.18},
        "constraints": {"keepInsideFrame": True},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--background", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--back")
    parser.add_argument("--material", choices=("clear-coat", "pearl", "brushed-metal", "spectral-lines", "etched-holo", "cosmic-flake", "star-holo"))
    parser.add_argument("--url-file", type=Path)
    args = parser.parse_args()
    server = load_server()

    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        sources = [("background", args.background), ("subject", args.subject)]
        if args.back:
            sources.append(("back", args.back))
        for kind, source_path in sources:
            with Image.open(source_path) as source:
                mode = "RGBA" if kind == "subject" else "RGB"
                source.convert(mode).resize((420, 588), Image.Resampling.LANCZOS).save(work / f"{kind}.png")

        background_info, background_data, size = server.encode_background(work / "background.png")
        subject_info, subject_data = server.encode_subject(work / "subject.png", size)
        back_info = back_data = None
        if args.back:
            back_info, back_data, back_size = server.encode_background(work / "back.png")
            if back_size != size:
                raise ValueError("back must use the same canvas as the background")

        base = server.ensure_http_server()
        urls = {}
        materials = [args.material] if args.material else sorted(server.MATERIALS)
        for material in materials:
            resolved, warnings = server.normalize_presentation(presentation(material))
            payload = {
                "schemaVersion": 5,
                "launchPolicy": "codex-browser-right",
                "artAlt": f"Production holographic card — {material}",
                "backAlt": "Adaptive frame back face" if back_info else None,
                "presentation": resolved,
                "warnings": warnings,
                "background": background_info,
                "subject": subject_info,
                "back": back_info,
            }
            preview_id = server.store_preview(background_data, subject_data, back_data, payload)
            urls[material] = f"{base}/preview/{preview_id}"
        serialized = json.dumps(urls)
        if args.url_file:
            args.url_file.write_text(serialized, encoding="utf-8")
        print(serialized, flush=True)
        threading.Event().wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
