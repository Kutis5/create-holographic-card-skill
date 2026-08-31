#!/usr/bin/env python3
"""Export one accepted layered card as a deterministic Cardex ``.hcard``.

This converter deliberately owns only the exchange package. It does not
modify a Presentation IR, the source art, or the holographic renderer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image


CARD_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
RATIO_EPSILON = 0.012


def require_card_id(value: str) -> str:
    if not CARD_ID.fullmatch(value):
        raise ValueError("--id must use only letters, numbers, _ and -, and be at most 64 characters.")
    return value


def resolve(source: str | None, card_dir: Path, default: str, label: str) -> Path:
    candidate = Path(source) if source else card_dir / default
    candidate = candidate.expanduser().resolve()
    if not candidate.is_file():
        raise ValueError(f"{label} does not exist: {candidate}")
    return candidate


def read_presentation(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"presentation is not valid JSON: {error}") from error
    if not isinstance(value, dict) or value.get("version") != 2:
        raise ValueError("presentation.version must be 2.")
    return value


def open_image(path: Path, label: str) -> Image.Image:
    try:
        image = Image.open(path)
        image.load()
    except Exception as error:
        raise ValueError(f"{label} is not a readable image: {error}") from error
    if abs(image.width / image.height - 5 / 7) > RATIO_EPSILON:
        raise ValueError(f"{label} must use a 5:7 canvas.")
    return image


def subject_image(path: Path, size: tuple[int, int]) -> Image.Image:
    subject = open_image(path, "subject").convert("RGBA")
    if subject.size != size:
        raise ValueError("subject must have exactly the same canvas dimensions as background.")
    alpha = subject.getchannel("A")
    low, high = alpha.getextrema()
    if low > 0 or high == 0:
        raise ValueError("subject must contain both transparent and visible pixels.")
    return subject


def webp_bytes(image: Image.Image, *, alpha: bool) -> bytes:
    from io import BytesIO

    output = BytesIO()
    image.convert("RGBA" if alpha else "RGB").save(output, "WEBP", lossless=True, method=6)
    return output.getvalue()


def asset_metadata(name: str, payload: bytes, size: tuple[int, int]) -> dict[str, Any]:
    return {
        "path": name,
        "mime": "image/webp",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "width": size[0],
        "height": size[1],
    }


def export_hcard(
    *, card_id: str, title: str, series: str, serial_number: str, author: str,
    rarity: str, background_path: Path, subject_path: Path, presentation_path: Path,
    output: Path, back_path: Path | None = None, copy: dict[str, Any] | None = None,
) -> Path:
    background = open_image(background_path, "background").convert("RGB")
    subject = subject_image(subject_path, background.size)
    presentation = read_presentation(presentation_path)
    thumbnail = Image.alpha_composite(background.convert("RGBA"), subject).convert("RGB")
    thumbnail.thumbnail((320, 448), Image.Resampling.LANCZOS)
    if thumbnail.size != (320, 448):
        thumbnail = thumbnail.resize((320, 448), Image.Resampling.LANCZOS)

    files: dict[str, bytes] = {
        "presentation.json": json.dumps(presentation, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        "assets/background.webp": webp_bytes(background, alpha=False),
        "assets/subject.webp": webp_bytes(subject, alpha=True),
        "assets/thumbnail.webp": webp_bytes(thumbnail, alpha=False),
    }
    if back_path is not None:
        back = open_image(back_path, "back").convert("RGB")
        if back.size != background.size:
            raise ValueError("back must have exactly the same canvas dimensions as background.")
        files["assets/back.webp"] = webp_bytes(back, alpha=False)

    manifest: dict[str, Any] = {
        "formatVersion": 1,
        "definition": {
            "id": require_card_id(card_id), "title": title.strip(), "series": series.strip(),
            "serialNumber": serial_number.strip(), "author": author.strip(), "rarity": rarity.strip(),
        },
        "presentation": {"path": "presentation.json", "version": 2},
        "assets": {
            "background": asset_metadata("assets/background.webp", files["assets/background.webp"], background.size),
            "subject": asset_metadata("assets/subject.webp", files["assets/subject.webp"], background.size),
            "thumbnail": asset_metadata("assets/thumbnail.webp", files["assets/thumbnail.webp"], thumbnail.size),
        },
    }
    if "assets/back.webp" in files:
        manifest["assets"]["back"] = asset_metadata("assets/back.webp", files["assets/back.webp"], background.size)
    if copy:
        manifest["copy"] = copy
    if any(not value for value in manifest["definition"].values()):
        raise ValueError("definition metadata cannot be empty.")

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.stem}-", suffix=".hcard", dir=output.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
            for name, payload in files.items():
                archive.writestr(name, payload)
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a layered holographic card for Cardex.")
    parser.add_argument("--card-dir", default=".", help="Folder containing background.png, subject.png and presentation.json.")
    parser.add_argument("--id", required=True, help="Stable Cardex definition identifier.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--series", default="未归类")
    parser.add_argument("--serial-number", default="—")
    parser.add_argument("--author", default="未知作者")
    parser.add_argument("--rarity", default="未标注")
    parser.add_argument("--background")
    parser.add_argument("--subject")
    parser.add_argument("--presentation")
    parser.add_argument("--back")
    parser.add_argument("--output", required=True)
    parser.add_argument("--acquired-at")
    parser.add_argument("--source", default="")
    parser.add_argument("--condition", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--favorite", action="store_true")
    parser.add_argument("--tag", action="append", default=[])
    args = parser.parse_args()
    try:
        card_dir = Path(args.card_dir).expanduser().resolve()
        copy = {"source": args.source, "condition": args.condition, "notes": args.notes, "isFavorite": args.favorite, "tags": args.tag}
        if args.acquired_at:
            copy["acquiredAt"] = args.acquired_at
        exported = export_hcard(
            card_id=args.id, title=args.title, series=args.series, serial_number=args.serial_number,
            author=args.author, rarity=args.rarity,
            background_path=resolve(args.background, card_dir, "background.png", "background"),
            subject_path=resolve(args.subject, card_dir, "subject.png", "subject"),
            presentation_path=resolve(args.presentation, card_dir, "presentation.json", "presentation"),
            back_path=Path(args.back).expanduser().resolve() if args.back else None,
            output=Path(args.output), copy=copy,
        )
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(exported)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
