#!/usr/bin/env python3
"""Register one isolated holographic card asset set in a React project."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]


ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-\d{2}$")
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
DEFAULT_OUT = "src/components/holographic-card"
PRESENTATION_KEYS = {"version", "frame", "radius", "surface", "foil", "texture", "sparkle", "glare", "depth", "motion", "constraints"}


def inside(root: Path, candidate: Path, label: str) -> Path:
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"{label} must stay inside the project.")
    return resolved


def slugify(value: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("--slug must contain at least one letter or number.")
    return slug[:48].rstrip("-")


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Cannot read {label}: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    if value.get("version") != 2:
        raise ValueError("presentation.version must be 2.")
    missing = PRESENTATION_KEYS - set(value)
    if missing:
        raise ValueError(f"presentation is missing required fields: {', '.join(sorted(missing))}.")
    return value


def read_catalog(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid card catalog: {error}") from error
    cards = value.get("cards") if isinstance(value, dict) else None
    if not isinstance(cards, list) or any(not isinstance(card, dict) for card in cards):
        raise ValueError("Card catalog must contain a cards array.")
    ids = [card.get("id") for card in cards]
    if any(not isinstance(card_id, str) or not ID_PATTERN.fullmatch(card_id) for card_id in ids):
        raise ValueError("Card catalog contains an invalid card id.")
    if len(ids) != len(set(ids)):
        raise ValueError("Card catalog contains duplicate card ids.")
    return cards


def choose_id(slug: str, cards: list[dict[str, Any]], explicit_id: str | None) -> str:
    existing = {str(card["id"]) for card in cards}
    if explicit_id:
        if not ID_PATTERN.fullmatch(explicit_id):
            raise ValueError("--card-id must use the slug-01 format.")
        if explicit_id in existing:
            raise ValueError(f"Card id already exists and will not be overwritten: {explicit_id}")
        return explicit_id
    prefix = f"{slug}-"
    numbers = [int(card_id[len(prefix):]) for card_id in existing if card_id.startswith(prefix) and card_id[len(prefix):].isdigit()]
    number = max(numbers, default=0) + 1
    if number > 99:
        raise ValueError(f"No available two-digit card id remains for slug: {slug}")
    return f"{slug}-{number:02d}"


def require_source(path_value: str, project: Path, label: str) -> Path:
    raw = Path(path_value).expanduser()
    path = inside(project, raw if raw.is_absolute() else project / raw, label)
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    return path


def normalize_image(source: Path, destination: Path, label: str, alpha: bool, expected_size: tuple[int, int] | None = None) -> tuple[int, int]:
    if Image is None:
        raise RuntimeError("Pillow is required to register card assets.")
    try:
        image = Image.open(source)
        image.load()
    except Exception as error:
        raise ValueError(f"{label} is not a readable image: {error}") from error
    if abs(image.width / image.height - 5 / 7) > 0.012:
        raise ValueError(f"{label} must use a 5:7 canvas.")
    if expected_size is not None and image.size != expected_size:
        raise ValueError("background and subject assets must have identical canvas dimensions.")
    if alpha:
        if "A" not in image.getbands():
            raise ValueError("subject must contain an Alpha channel.")
        rgba = image.convert("RGBA")
        low, high = rgba.getchannel("A").getextrema()
        bbox = rgba.getchannel("A").point(lambda value: 255 if value > 8 else 0).getbbox()
        if low >= 8 or high <= 247 or bbox is None or bbox == (0, 0, rgba.width, rgba.height):
            raise ValueError("subject must contain meaningful transparent and opaque pixels with a non-full alpha bounding box.")
        rgba.save(destination, "WEBP", lossless=True, method=6)
    else:
        image.convert("RGB").save(destination, "WEBP", quality=90, method=6)
    return image.size


def render_registry(cards: list[dict[str, Any]]) -> str:
    lines = ["import type { CardRegistry } from \"../card-registry\";", ""]
    ordered = sorted(cards, key=lambda card: str(card["id"]))
    for card in ordered:
        ident = re.sub(r"[^A-Za-z0-9_]", "_", str(card["id"]))
        lines.append(f'import background_{ident} from "./{card["id"]}/background.webp";')
        lines.append(f'import subject_{ident} from "./{card["id"]}/subject.webp";')
        if card.get("back"):
            lines.append(f'import back_{ident} from "./{card["id"]}/back.webp";')
    lines.append("")
    lines.append("export const cardRegistry: CardRegistry = {")
    for card in ordered:
        card_id = str(card["id"])
        ident = re.sub(r"[^A-Za-z0-9_]", "_", card_id)
        record = {
            "id": card_id,
            "backgroundSrc": f"background_{ident}",
            "subjectSrc": f"subject_{ident}",
            "artAlt": card["artAlt"],
            "presentation": card["presentation"],
        }
        if card.get("back"):
            record["backSrc"] = f"back_{ident}"
            if card.get("backAlt"):
                record["backAlt"] = card["backAlt"]
        lines.append(f"  {json.dumps(card_id)}: {{")
        lines.append(f"    id: {json.dumps(record['id'], ensure_ascii=False)},")
        lines.append(f"    backgroundSrc: {record['backgroundSrc']},")
        lines.append(f"    subjectSrc: {record['subjectSrc']},")
        lines.append(f"    artAlt: {json.dumps(record['artAlt'], ensure_ascii=False)},")
        lines.append("    presentation: " + json.dumps(record["presentation"], ensure_ascii=False, indent=2).replace("\n", "\n    ") + ",")
        if card.get("back"):
            lines.append(f"    backSrc: {record['backSrc']},")
            if card.get("backAlt"):
                lines.append(f"    backAlt: {json.dumps(record['backAlt'], ensure_ascii=False)},")
        lines.append("  },")
    lines.extend(["};", "", "export default cardRegistry;", ""])
    return "\n".join(lines)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def restore_file(path: Path, previous: bytes | None) -> None:
    if previous is None:
        if path.exists():
            path.unlink()
        return
    path.write_bytes(previous)


def register(project: Path, destination: Path, slug: str, card_id: str | None, background: Path, subject: Path, art_alt: str, presentation: dict[str, Any], back: Path | None, back_alt: str | None) -> str:
    destination = inside(project, destination, "destination")
    cards_root = destination / "cards"
    catalog_path = cards_root / "catalog.json"
    registry_path = cards_root / "registry.ts"
    cards = read_catalog(catalog_path)
    chosen_id = choose_id(slug, cards, card_id)
    final_dir = cards_root / chosen_id
    if final_dir.exists():
        raise ValueError(f"Card directory already exists and will not be overwritten: {final_dir}")

    cards_root.mkdir(parents=True, exist_ok=True)
    previous_catalog = catalog_path.read_bytes() if catalog_path.is_file() else None
    previous_registry = registry_path.read_bytes() if registry_path.is_file() else None
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{chosen_id}.", dir=cards_root))
    moved = False
    try:
        size = normalize_image(background, temporary_dir / "background.webp", "background", alpha=False)
        normalize_image(subject, temporary_dir / "subject.webp", "subject", alpha=True, expected_size=size)
        if back:
            normalize_image(back, temporary_dir / "back.webp", "back", alpha=False, expected_size=size)
        new_card = {
            "id": chosen_id,
            "background": f"./{chosen_id}/background.webp",
            "subject": f"./{chosen_id}/subject.webp",
            "artAlt": art_alt,
            "presentation": presentation,
        }
        if back:
            new_card["back"] = f"./{chosen_id}/back.webp"
            if back_alt:
                new_card["backAlt"] = back_alt
        updated = sorted(cards + [new_card], key=lambda card: str(card["id"]))
        os.replace(temporary_dir, final_dir)
        moved = True
        atomic_write(catalog_path, json.dumps({"cards": updated}, ensure_ascii=False, indent=2) + "\n")
        atomic_write(registry_path, render_registry(updated))
    except Exception:
        if moved and final_dir.exists():
            shutil.rmtree(final_dir)
        elif temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        restore_file(catalog_path, previous_catalog)
        restore_file(registry_path, previous_registry)
        raise
    return chosen_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--slug", required=True, help="Short human-readable card slug")
    parser.add_argument("--card-id", help="Optional explicit slug-01 id; existing ids are rejected")
    parser.add_argument("--background", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--art-alt", required=True)
    parser.add_argument("--presentation", required=True, help="Path to a Card Presentation IR v2 JSON file")
    parser.add_argument("--back")
    parser.add_argument("--back-alt")
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()
    try:
        project = Path(args.project).resolve()
        if not project.is_dir():
            raise ValueError(f"Project directory does not exist: {project}")
        destination = inside(project, project / args.out, "--out")
        slug = slugify(args.slug)
        background = require_source(args.background, project, "--background")
        subject = require_source(args.subject, project, "--subject")
        back = require_source(args.back, project, "--back") if args.back else None
        presentation_path = require_source(args.presentation, project, "--presentation")
        if args.back_alt and not back:
            raise ValueError("--back-alt requires --back.")
        art_alt = args.art_alt.strip()
        if not art_alt:
            raise ValueError("--art-alt must not be empty.")
        chosen_id = register(project, destination, slug, args.card_id, background, subject, art_alt, read_json(presentation_path, "presentation"), back, args.back_alt.strip() if args.back_alt else None)
    except (RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Registered holographic card {chosen_id} in {destination / 'cards' / chosen_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
