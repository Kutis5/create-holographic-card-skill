#!/usr/bin/env python3
"""Install the bundled holographic-card React template into a supported project."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


TEMPLATE_FILES = (
    "HolographicCard.tsx",
    "HolographicCard.module.css",
    "HolographicCard.module.css.d.ts",
    "card-registry.ts",
    "presentation.ts",
    "optical-recipes.ts",
    "holo-engine.js",
    "holo-engine.d.ts",
    "frame-palette.js",
    "frame-palette.d.ts",
    "optical-state.js",
    "optical-state.d.ts",
    "materials.ts",
    "index.ts",
)
RUNTIME_TEXTURE_FILES = (
    "clear-coat.webp",
    "pearl.webp",
    "brushed-metal.webp",
    "spectral-lines.webp",
    "etched-holo.webp",
    "cosmic-flake.webp",
    "star-holo.webp",
    "blue-noise.webp",
    "micro-grain.webp",
    "manifest.json",
)


def read_package(project: Path) -> dict:
    package_file = project / "package.json"
    if not package_file.is_file():
        raise ValueError(f"No package.json found in {project}")
    try:
        return json.loads(package_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid package.json: {error}") from error


def dependency_names(package: dict) -> set[str]:
    names: set[str] = set()
    for field in ("dependencies", "devDependencies", "peerDependencies"):
        values = package.get(field, {})
        if isinstance(values, dict):
            names.update(values)
    return names


def ensure_supported_project(package: dict) -> None:
    names = dependency_names(package)
    if "react" not in names:
        raise ValueError("The target must declare React in package.json.")
    if "next" not in names and "vite" not in names:
        raise ValueError("The target must declare either Next.js or Vite in package.json.")
    if "typescript" not in names:
        raise ValueError("The target must declare TypeScript in package.json.")


def safe_output_path(project: Path, output: str) -> Path:
    raw = Path(output)
    if raw.is_absolute():
        raise ValueError("--out must be a relative path inside the target project.")
    destination = (project / raw).resolve()
    if destination != project and project not in destination.parents:
        raise ValueError("--out must stay inside the target project.")
    return destination


def install(project: Path, destination: Path, force: bool) -> None:
    template = Path(__file__).resolve().parents[1] / "assets" / "react-template"
    sources = [(Path(name), template / name) for name in TEMPLATE_FILES]
    sources.extend((Path("holo-textures") / name, template / "holo-textures" / name) for name in RUNTIME_TEXTURE_FILES)
    missing = [str(relative) for relative, source in sources if not source.is_file()]
    if missing:
        raise ValueError(f"Bundled template is incomplete: {', '.join(missing)}")

    existing = [str(relative) for relative, _ in sources if (destination / relative).exists()]
    if existing and not force:
        raise ValueError(
            "Refusing to overwrite existing files: "
            + ", ".join(existing)
            + ". Re-run with --force only when replacement is intended."
        )

    destination.mkdir(parents=True, exist_ok=True)
    for relative, source in sources:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Path to a Vite React or Next.js project")
    parser.add_argument(
        "--out",
        default="src/components/holographic-card",
        help="Relative component directory (default: src/components/holographic-card)",
    )
    parser.add_argument("--force", action="store_true", help="Allow replacement of template files")
    args = parser.parse_args()

    try:
        project = Path(args.project).resolve()
        if not project.is_dir():
            raise ValueError(f"Project directory does not exist: {project}")
        package = read_package(project)
        ensure_supported_project(package)
        destination = safe_output_path(project, args.out)
        install(project, destination, args.force)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(f"Installed holographic-card template to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
