#!/usr/bin/env python3
"""Tests for deterministic card-face preflight inspection."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "inspect_card_face", ROOT / "scripts" / "inspect_card_face.py"
)
assert SPEC and SPEC.loader
INSPECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECT)


def assert_no_binary(test: unittest.TestCase, value) -> None:
    encoded = json.dumps(value)
    test.assertNotIn("data:image", encoded)
    test.assertNotIn("image_url", encoded)
    for item in value.values() if isinstance(value, dict) else value if isinstance(value, list) else []:
        if isinstance(item, (dict, list)):
            assert_no_binary(test, item)
        elif isinstance(item, str):
            test.assertLessEqual(len(item), 8192)


class CardFacePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def image(self, name: str, size=(1060, 1484), mode="RGB", color=None) -> Path:
        path = self.root / name
        fill = color if color is not None else ((32, 48, 72, 255) if mode == "RGBA" else (32, 48, 72))
        Image.new(mode, size, fill).save(path)
        return path

    def test_opaque_5_by_7_art_passes_deterministic_preflight(self) -> None:
        report = INSPECT.inspect_card_face(self.image("accepted.png"))
        self.assertTrue(report["passed"])
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["validation"]["canvas"], [1060, 1484])
        self.assertAlmostEqual(report["validation"]["ratio"], 5 / 7, places=6)
        self.assertTrue(report["validation"]["fullyOpaque"])
        self.assertTrue(report["validation"]["meetsMinimumResolution"])
        self.assertIn("subjectFullyInsideCanvas", report["visualChecksRequired"])
        self.assertIn("noTextOrUi", report["visualChecksRequired"])
        self.assertIn("safeBottomMargin", report["visualChecksRequired"])
        assert_no_binary(self, report)

    def test_opaque_rgba_is_allowed_but_transparency_is_rejected(self) -> None:
        opaque = INSPECT.inspect_card_face(self.image("opaque.png", mode="RGBA"))
        self.assertTrue(opaque["passed"])

        path = self.image("transparent.png", mode="RGBA")
        image = Image.open(path).convert("RGBA")
        image.putpixel((0, 0), (0, 0, 0, 0))
        image.save(path)
        report = INSPECT.inspect_card_face(path)
        self.assertFalse(report["passed"])
        self.assertIn("art must be fully opaque", report["failures"])

    def test_wrong_ratio_and_low_resolution_are_reported_together(self) -> None:
        report = INSPECT.inspect_card_face(self.image("small-square.png", (500, 500)))
        self.assertFalse(report["passed"])
        self.assertIn("art must use a 5:7 canvas", report["failures"])
        self.assertIn("art is below the 840x1176 minimum", report["failures"])

    def test_unreadable_input_is_a_hard_failure(self) -> None:
        missing = self.root / "missing.png"
        with self.assertRaisesRegex(INSPECT.PreflightError, "does not exist"):
            INSPECT.inspect_card_face(missing)
        broken = self.root / "broken.png"
        broken.write_bytes(b"not an image")
        with self.assertRaisesRegex(INSPECT.PreflightError, "not a readable image"):
            INSPECT.inspect_card_face(broken)


if __name__ == "__main__":
    unittest.main(verbosity=2)
