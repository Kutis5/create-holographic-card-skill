#!/usr/bin/env python3
"""Regression tests for install_component.py and the React template contract."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = SKILL_ROOT / "scripts" / "install_component.py"
SPEC = importlib.util.spec_from_file_location("install_component", INSTALLER_PATH)
assert SPEC and SPEC.loader
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


def make_project(root: Path, dependencies: dict[str, str]) -> Path:
    root.mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": dependencies}), encoding="utf-8")
    return root


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_vite_and_next_projects_install(self) -> None:
        for name, framework in (("vite", "vite"), ("next", "next")):
            project = make_project(self.root / name, {"react": "19", "typescript": "6", framework: "latest"})
            INSTALLER.install(project, project / "src/components/holographic-card", force=False)
            for filename in INSTALLER.TEMPLATE_FILES:
                self.assertTrue((project / "src/components/holographic-card" / filename).is_file())
            for filename in INSTALLER.RUNTIME_TEXTURE_FILES:
                self.assertTrue((project / "src/components/holographic-card/holo-textures" / filename).is_file())
            self.assertFalse((project / "src/components/holographic-card/holo-textures/sources").exists())
            self.assertFalse((project / "src/components/holographic-card/holo-textures/contact-sheet.png").exists())

    def test_custom_path_and_force(self) -> None:
        project = make_project(self.root / "project", {"react": "19", "typescript": "6", "vite": "8"})
        destination = INSTALLER.safe_output_path(project, "ui/holo")
        INSTALLER.install(project, destination, force=False)
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            INSTALLER.install(project, destination, force=False)
        INSTALLER.install(project, destination, force=True)

    def test_rejects_invalid_projects_and_escape_paths(self) -> None:
        cases = (
            ({"typescript": "6", "vite": "8"}, "React"),
            ({"react": "19", "vite": "8"}, "TypeScript"),
            ({"react": "19", "typescript": "6"}, "Next.js or Vite"),
        )
        for index, (dependencies, message) in enumerate(cases):
            project = make_project(self.root / f"invalid-{index}", dependencies)
            with self.assertRaisesRegex(ValueError, message):
                INSTALLER.ensure_supported_project(INSTALLER.read_package(project))
        project = make_project(self.root / "safe", {"react": "19", "typescript": "6", "vite": "8"})
        with self.assertRaisesRegex(ValueError, "inside the target project"):
            INSTALLER.safe_output_path(project, "../escape")

    def test_template_contract(self) -> None:
        source = (SKILL_ROOT / "assets/react-template/HolographicCard.tsx").read_text(encoding="utf-8")
        css = (SKILL_ROOT / "assets/react-template/HolographicCard.module.css").read_text(encoding="utf-8")
        contract = (SKILL_ROOT / "assets/react-template/presentation.ts").read_text(encoding="utf-8")
        recipes = (SKILL_ROOT / "assets/react-template/optical-recipes.ts").read_text(encoding="utf-8")
        self.assertIn("card: CardRecord", source)
        self.assertIn("data-card-id={card.id}", source)
        self.assertNotIn("backgroundSrc: string;", source)
        self.assertNotIn("subjectSrc: string;", source)
        self.assertNotIn("presentation: CardPresentation;", source)
        self.assertIn("card-registry", source)
        self.assertIn("frame-palette.js", source)
        self.assertIn("optical-state.js", source)
        self.assertIn("pointer-motion.js", source)
        self.assertIn("frontPaletteKey", source)
        self.assertIn("backPaletteKey", source)
        self.assertIn("cancelled", source)
        self.assertIn("style={paletteVars(frontPalette)}", source)
        self.assertIn("style={paletteVars(backPalette)}", source)
        self.assertIn('colorMode?: FrameColorMode', contract)
        self.assertIn('colorMode: "fixed"', contract)
        registry = (SKILL_ROOT / "assets/react-template/card-registry.ts").read_text(encoding="utf-8")
        self.assertIn("export interface CardRecord", registry)
        self.assertIn("export type CardRegistry", registry)
        self.assertIn("export function getCard", registry)
        self.assertNotIn("CardContent", source)
        self.assertNotIn("content", source)
        self.assertNotIn("header", source.lower())
        self.assertNotIn("footer", source.lower())
        self.assertIn("--flip-y", source)
        self.assertIn("version: 2", contract)
        self.assertNotIn("layout", contract)
        self.assertNotIn("type:", contract)
        self.assertIn("parallaxX", contract)
        self.assertIn('frame: { style: "narrow", width: 0.65', contract)
        self.assertIn('radius: { outer: 5.8, inner: 5.15 }', contract)
        self.assertIn('parallaxX: 1.45, parallaxY: 1.25, lift: 19', contract)
        self.assertIn('maxX: 14, maxY: 14, scale: 1.024, smoothing: 0.18', contract)
        self.assertIn('intensity: 0.78', contract)
        self.assertIn('intensity: 0.48', contract)
        self.assertIn('intensity: 0.62', contract)
        self.assertIn("touch-action:none", css)
        engine = (SKILL_ROOT / "assets/react-template/holo-engine.js").read_text(encoding="utf-8")
        declarations = (SKILL_ROOT / "assets/react-template/holo-engine.d.ts").read_text(encoding="utf-8")
        self.assertIn("createHolographicRenderer", engine)
        self.assertIn("createHolographicRenderer", declarations)
        self.assertIn("ready(): Promise<void>", declarations)
        self.assertIn("<canvas", source)
        self.assertIn("renderer.ready()", source)
        self.assertIn("aria-busy", source)
        self.assertIn("styles.pending", source)
        self.assertIn("ResizeObserver", source)
        self.assertIn("renderPointerFrame", source)
        self.assertIn("role=\"alert\"", source)
        for family in ("clear-coat", "pearl", "brushed-metal", "spectral-lines", "etched-holo", "cosmic-flake", "star-holo"):
            self.assertIn(f'"{family}"', engine)
        self.assertNotIn("data-optical-layer", source)
        self.assertIn("resolveEffectTargets", recipes)
        self.assertIn(".materialCanvas", css)
        self.assertIn(".pending{visibility:hidden}", css)
        self.assertNotIn(".spectral-lines-a", css)
        self.assertNotIn(".flake-large", css)
        self.assertNotIn("radial-gradient(circle at 50% 50%", css)
        self.assertLess(css.index(".background{z-index:0"), css.index(".materialCanvas{z-index:1"))
        self.assertLess(css.index(".materialCanvas{z-index:1"), css.index(".subjectShadow{z-index:2"))
        self.assertLess(css.index(".subjectShadow{z-index:2"), css.index(".subject{z-index:3"))
        self.assertNotIn("subjectRim", source)
        self.assertNotIn(".subjectRim", css)
        self.assertNotIn("repeating-linear-gradient", css)
        self.assertNotIn(".surfaceCoat", css)
        self.assertNotIn(".surfaceGlare", css)

    def test_optical_recipes_are_bounded_and_differential(self) -> None:
        source = (SKILL_ROOT / "assets/react-template/holo-engine.js").read_text(encoding="utf-8")
        self.assertEqual(source.count("materialEffect_"), 14)
        self.assertIn("NEUTRAL_REVEAL = IDLE_REVEAL", source)
        self.assertIn("flagshipOptics", source)
        self.assertIn("MAX_DEVICE_PIXEL_RATIO = 2", source)
        self.assertIn("webglcontextlost", source)
        component = (SKILL_ROOT / "assets/react-template/HolographicCard.tsx").read_text(encoding="utf-8")
        self.assertIn("renderPointerFrame", component)
        self.assertIn("setReducedMotion", component)
        self.assertIn("releasePointer", component)
        self.assertIn("setPaused", component)


if __name__ == "__main__":
    unittest.main(verbosity=2)
