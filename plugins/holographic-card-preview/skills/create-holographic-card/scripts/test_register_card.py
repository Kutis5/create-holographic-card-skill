#!/usr/bin/env python3
"""Regression tests for isolated multi-card registration."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("register_card", ROOT / "scripts" / "register_card.py")
assert SPEC and SPEC.loader
REGISTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REGISTER)


def make_project(root: Path) -> Path:
    project = root / "project"
    project.mkdir()
    (project / "package.json").write_text('{"dependencies":{"react":"19","typescript":"6","vite":"8"}}', encoding="utf-8")
    return project


class RegisterCardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = make_project(self.root)
        incoming = self.project / "incoming"; incoming.mkdir()
        self.background = incoming / "background.png"
        Image.new("RGB", (700, 980), (12, 18, 24)).save(self.background)
        self.subject = incoming / "subject.png"
        subject = Image.new("RGBA", (700, 980), (0, 0, 0, 0)); ImageDraw.Draw(subject).ellipse((180, 160, 520, 880), fill=(220, 225, 235, 255)); subject.save(self.subject)
        self.presentation = incoming / "presentation.json"
        self.presentation.write_text(json.dumps({
            "version": 2,
            "frame": {"style": "narrow", "width": .65, "color": "#75808f"},
            "radius": {"outer": 5.8},
            "surface": {"color": "#070a0f", "accent": "#a7d9e8", "material": "clear-coat"},
            "foil": {"enabled": False, "target": "background", "colors": ["#a7d9e8"], "intensity": 0},
            "texture": {"kind": "micro-grain", "target": "background", "intensity": .12},
            "sparkle": {"enabled": False, "target": "background", "intensity": 0},
            "glare": {"enabled": True, "target": "surface", "intensity": .16},
            "depth": {"parallaxX": 1.45, "parallaxY": 1.25, "lift": 19, "shadowOpacity": .18, "shadowBlur": 16, "rimIntensity": .12},
            "motion": {"maxX": 9, "maxY": 7, "scale": 1.01, "smoothing": .18},
            "constraints": {"keepInsideFrame": True},
        }), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def register(self, slug="afterimage", **kwargs):
        return REGISTER.register(self.project, self.project / "src/components/holographic-card", slug, kwargs.get("card_id"), self.background, self.subject, "Afterimage", json.loads(self.presentation.read_text(encoding="utf-8")), None, None)

    def test_repeated_slug_creates_isolated_numbered_cards(self) -> None:
        first = self.register(); first_dir = self.project / "src/components/holographic-card/cards" / first
        first_hash = (first_dir / "background.webp").read_bytes()
        second = self.register(); second_dir = self.project / "src/components/holographic-card/cards" / second
        self.assertEqual((first, second), ("afterimage-01", "afterimage-02"))
        self.assertTrue((first_dir / "subject.webp").is_file()); self.assertTrue((second_dir / "subject.webp").is_file())
        self.assertEqual(first_hash, (first_dir / "background.webp").read_bytes())
        catalog = json.loads((first_dir.parent / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual([card["id"] for card in catalog["cards"]], ["afterimage-01", "afterimage-02"])
        registry = (first_dir.parent / "registry.ts").read_text(encoding="utf-8")
        self.assertIn('"afterimage-01"', registry); self.assertIn('"afterimage-02"', registry)
        self.assertIn('./afterimage-01/background.webp', catalog["cards"][0]["background"])
        self.assertNotEqual(catalog["cards"][0]["background"], catalog["cards"][1]["background"])

    def test_existing_id_and_unsafe_output_are_rejected_without_changes(self) -> None:
        self.register()
        catalog = self.project / "src/components/holographic-card/cards/catalog.json"
        before = catalog.read_bytes()
        with self.assertRaisesRegex(ValueError, "will not be overwritten"):
            self.register(card_id="afterimage-01")
        self.assertEqual(before, catalog.read_bytes())
        with self.assertRaisesRegex(ValueError, "inside the project"):
            REGISTER.register(self.project, (self.project / "../escape").resolve(), "other", None, self.background, self.subject, "Other", {}, None, None)

    def test_failed_asset_validation_leaves_existing_catalog_untouched(self) -> None:
        self.register()
        catalog = self.project / "src/components/holographic-card/cards/catalog.json"
        registry = catalog.parent / "registry.ts"
        before_catalog, before_registry = catalog.read_bytes(), registry.read_bytes()
        invalid = self.project / "incoming/invalid.png"
        Image.new("RGB", (100, 100), (255, 255, 255)).save(invalid)
        with self.assertRaisesRegex(ValueError, "5:7 canvas"):
            REGISTER.register(self.project, self.project / "src/components/holographic-card", "afterimage", None, invalid, self.subject, "Broken", json.loads(self.presentation.read_text(encoding="utf-8")), None, None)
        self.assertEqual(before_catalog, catalog.read_bytes()); self.assertEqual(before_registry, registry.read_bytes())
        self.assertTrue((catalog.parent / "afterimage-01").is_dir())

    def test_registry_is_deterministic(self) -> None:
        self.register("zeta"); self.register("alpha")
        registry = (self.project / "src/components/holographic-card/cards/registry.ts").read_text(encoding="utf-8")
        self.assertLess(registry.index('"alpha-01"'), registry.index('"zeta-01"'))
        self.assertIn("import type { CardRegistry }", registry)


if __name__ == "__main__":
    unittest.main(verbosity=2)
