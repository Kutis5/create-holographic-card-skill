#!/usr/bin/env python3
"""Run deterministic preflight checks before accepting or generating card-face art."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]


MIN_WIDTH = 840
MIN_HEIGHT = 1176
RATIO_TOLERANCE = 0.012
VISUAL_CHECKS = [
    "subjectFullyInsideCanvas",
    "safeBottomMargin",
    "noTextOrUi",
    "noBakedBorderOrOpticalEffects",
    "subjectReadableAtCardSize",
]


class PreflightError(ValueError):
    """Raised when card-face metadata cannot be inspected safely."""


def require_pillow() -> None:
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow is required to inspect card-face art.")


def inspect_card_face(path: Path) -> dict[str, Any]:
    require_pillow()
    if not path.is_file():
        raise PreflightError(f"art does not exist: {path}")
    try:
        with Image.open(path) as source:
            source.load()
            image = ImageOps.exif_transpose(source).copy()
    except Exception as error:
        raise PreflightError(f"art is not a readable image: {error}") from error

    width, height = image.size
    ratio = width / height if height else 0.0
    failures: list[str] = []
    ratio_ok = abs(ratio - 5 / 7) <= RATIO_TOLERANCE
    resolution_ok = width >= MIN_WIDTH and height >= MIN_HEIGHT

    fully_opaque = True
    if "A" in image.getbands():
        alpha_low, _alpha_high = image.getchannel("A").getextrema()
        fully_opaque = alpha_low == 255

    if not ratio_ok:
        failures.append("art must use a 5:7 canvas")
    if not resolution_ok:
        failures.append(f"art is below the {MIN_WIDTH}x{MIN_HEIGHT} minimum")
    if not fully_opaque:
        failures.append("art must be fully opaque")

    return {
        "schemaVersion": 1,
        "path": str(path.resolve()),
        "passed": not failures,
        "failures": failures,
        "validation": {
            "canvas": [width, height],
            "ratio": round(ratio, 6),
            "ratioIs5By7": ratio_ok,
            "fullyOpaque": fully_opaque,
            "meetsMinimumResolution": resolution_ok,
        },
        "visualChecksRequired": list(VISUAL_CHECKS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--art", required=True)
    args = parser.parse_args()
    try:
        report = inspect_card_face(Path(args.art).resolve())
    except (PreflightError, RuntimeError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
