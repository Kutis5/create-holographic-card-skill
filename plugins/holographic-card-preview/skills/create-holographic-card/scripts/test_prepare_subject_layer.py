#!/usr/bin/env python3
"""Regression tests for adaptive chroma subject preparation."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "prepare_subject_layer", ROOT / "scripts" / "prepare_subject_layer.py"
)
assert SPEC and SPEC.loader
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


class PrepareSubjectLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.art = self.root / "art.png"
        art = Image.new("RGB", (500, 700), (24, 36, 58))
        ImageDraw.Draw(art).ellipse((125, 90, 385, 645), fill=(226, 171, 112))
        art.save(self.art)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def keyed(
        self,
        color: tuple[int, int, int],
        name: str = "keyed.png",
        offset_x: int = 0,
    ) -> Path:
        path = self.root / name
        image = Image.new("RGB", (500, 700), color)
        ImageDraw.Draw(image).ellipse(
            (125 + offset_x, 90, 385 + offset_x, 645), fill=(226, 171, 112)
        )
        image.save(path)
        return path

    def fallback_mask(self) -> Image.Image:
        mask = Image.new("L", (500, 700), 0)
        ImageDraw.Draw(mask).ellipse((125, 90, 385, 645), fill=255)
        return mask

    def test_green_magenta_and_legacy_keys_preserve_original_rgb(self) -> None:
        cases = (
            ("green", (0, 255, 0), "green"),
            ("#00ff00", (0, 255, 0), "green"),
            ("magenta", (255, 0, 255), "magenta"),
            ("#ff00ff", (255, 0, 255), "magenta"),
        )
        for key, color, family in cases:
            with self.subTest(key=key):
                output = self.root / f"subject-{key.removeprefix('#')}.png"
                with patch.object(PREPARE, "local_mask") as local:
                    report = PREPARE.prepare_subject(
                        self.art,
                        self.keyed(color, f"keyed-{key.removeprefix('#')}.png"),
                        key,
                        "generic",
                        output,
                    )
                local.assert_not_called()
                self.assertEqual(report["method"], "adaptive-chroma")
                self.assertIsNone(report["fallbackReason"])
                self.assertEqual(report["preflight"]["selectedFamily"], family)
                self.assertEqual(report["preflight"]["borderCoverage"], 1.0)
                self.assertTrue(report["alignment"]["alignmentPassed"])
                self.assertEqual(
                    report["attempts"],
                    [
                        {"method": "adaptive-chroma", "status": "passed"},
                        {"method": "chroma-guided-local", "status": "skipped"},
                        {"method": "local-fallback", "status": "skipped"},
                    ],
                )
                subject = Image.open(output).convert("RGBA")
                art = Image.open(self.art).convert("RGB")
                self.assertEqual(subject.getpixel((250, 350))[:3], art.getpixel((250, 350)))
                self.assertEqual(subject.getpixel((10, 10)), (0, 0, 0, 0))

    def test_auto_accepts_imperfect_brightness_varying_green(self) -> None:
        keyed = Image.new("RGB", (500, 700))
        pixels = keyed.load()
        for y in range(700):
            for x in range(500):
                delta = round(18 * (x / 499 - 0.5))
                pixels[x, y] = (20, 235 + delta, 22)
        ImageDraw.Draw(keyed).ellipse((125, 90, 385, 645), fill=(226, 171, 112))
        path = self.root / "imperfect-green.png"
        keyed.save(path)
        output = self.root / "imperfect-green-subject.png"
        with patch.object(PREPARE, "local_mask") as local:
            report = PREPARE.prepare_subject(self.art, path, "auto", "human", output)
        local.assert_not_called()
        self.assertEqual(report["method"], "adaptive-chroma")
        self.assertEqual(report["keyColor"], "#00ff00")
        self.assertEqual(report["preflight"]["selectedFamily"], "green")
        self.assertGreaterEqual(report["preflight"]["cornerCoverages"][0], 0.99)
        self.assertTrue(report["alignment"]["alignmentPassed"])

    def test_auto_selects_magenta_when_it_is_the_background_family(self) -> None:
        output = self.root / "auto-magenta.png"
        report = PREPARE.prepare_subject(
            self.art, self.keyed((238, 18, 229), "auto-magenta-keyed.png"), "auto", "generic", output
        )
        self.assertEqual(report["method"], "adaptive-chroma")
        self.assertEqual(report["keyColor"], "#ff00ff")
        self.assertEqual(report["preflight"]["estimatedKey"], [238, 18, 229])

    def test_unusable_key_uses_one_full_local_fallback(self) -> None:
        cases: list[tuple[str, Image.Image]] = []
        gray = Image.new("RGB", (500, 700), (96, 96, 96))
        cases.append(("gray", gray))
        checker = Image.new("RGB", (500, 700), (0, 255, 0))
        draw = ImageDraw.Draw(checker)
        for y in range(0, 700, 24):
            for x in range(0, 500, 24):
                if (x // 24 + y // 24) % 2:
                    draw.rectangle((x, y, x + 23, y + 23), fill=(0, 92, 0))
        cases.append(("dispersed-green", checker))
        cases.append(("wrong-family", Image.new("RGB", (500, 700), (255, 0, 255))))

        for name, image in cases:
            with self.subTest(name=name):
                path = self.root / f"{name}.png"
                image.save(path)
                output = self.root / f"{name}-subject.png"
                with patch.object(PREPARE, "local_mask", return_value=self.fallback_mask()) as local:
                    report = PREPARE.prepare_subject(
                        self.art, path, "green", "human", output
                    )
                local.assert_called_once()
                self.assertEqual(local.call_args.args[1], "human")
                self.assertEqual(report["method"], "local-fallback")
                self.assertIsNotNone(report["fallbackReason"])
                self.assertEqual(report["attempts"][0]["method"], "adaptive-chroma")
                self.assertEqual(report["attempts"][0]["status"], "failed")
                self.assertEqual(report["attempts"][1]["method"], "chroma-guided-local")
                self.assertEqual(report["attempts"][1]["status"], "skipped")
                self.assertEqual(report["attempts"][2], {"method": "local-fallback", "status": "passed"})

    def test_shifted_keyed_subject_is_a_hard_alignment_failure(self) -> None:
        output = self.root / "shifted.png"
        with patch.object(PREPARE, "local_mask") as local:
            with self.assertRaisesRegex(PREPARE.AlignmentError, "does not align"):
                PREPARE.prepare_subject(
                    self.art,
                    self.keyed((0, 255, 0), "shifted-keyed.png", offset_x=20),
                    "auto",
                    "human",
                    output,
                )
        local.assert_not_called()
        self.assertFalse(output.exists())

    def test_subject_kind_selects_the_expected_cached_model(self) -> None:
        calls: list[str] = []

        def fake_local(_art, kind: str):
            calls.append(PREPARE.MODEL_FILES[kind][0])
            return self.fallback_mask()

        wrong_key = self.root / "wrong-model.png"
        Image.new("RGB", (500, 700), (32, 32, 32)).save(wrong_key)
        with patch.object(PREPARE, "local_mask", side_effect=fake_local):
            PREPARE.prepare_subject(
                self.art, wrong_key, "auto", "human", self.root / "human.png"
            )
            PREPARE.prepare_subject(
                self.art, wrong_key, "auto", "generic", self.root / "generic.png"
            )
        self.assertEqual(calls, ["u2net_human_seg", "u2netp"])

    def test_canvas_errors_are_hard_failures_without_fallback(self) -> None:
        wrong_size = self.root / "wrong-size.png"
        Image.new("RGB", (400, 560), (0, 255, 0)).save(wrong_size)
        square_art = self.root / "square-art.png"
        square_key = self.root / "square-key.png"
        Image.new("RGB", (500, 500), (0, 0, 0)).save(square_art)
        Image.new("RGB", (500, 500), (0, 255, 0)).save(square_key)
        with patch.object(PREPARE, "local_mask") as local:
            with self.assertRaisesRegex(PREPARE.PreparationError, "identical canvas"):
                PREPARE.prepare_subject(
                    self.art, wrong_size, "auto", "generic", self.root / "mismatch.png"
                )
            with self.assertRaisesRegex(PREPARE.PreparationError, "5:7 canvas"):
                PREPARE.prepare_subject(
                    square_art, square_key, "auto", "generic", self.root / "square.png"
                )
        local.assert_not_called()

    def test_existing_output_and_local_failure_do_not_mutate_files(self) -> None:
        keyed = self.keyed((0, 255, 0), "existing-key.png")
        output = self.root / "existing.png"
        output.write_bytes(b"keep")
        before = output.read_bytes()
        with self.assertRaisesRegex(PREPARE.PreparationError, "will not be overwritten"):
            PREPARE.prepare_subject(self.art, keyed, "auto", "generic", output)
        self.assertEqual(output.read_bytes(), before)

        wrong = self.root / "failed-key.png"
        Image.new("RGB", (500, 700), (40, 40, 40)).save(wrong)
        failed_output = self.root / "failed.png"
        with patch.object(
            PREPARE, "local_mask", side_effect=PREPARE.PreparationError("local failed")
        ) as local:
            with self.assertRaisesRegex(PREPARE.PreparationError, "local failed"):
                PREPARE.prepare_subject(
                    self.art, wrong, "auto", "generic", failed_output
                )
        local.assert_called_once()
        self.assertFalse(failed_output.exists())

    def test_current_imperfect_green_passes_chroma_but_fails_alignment(self) -> None:
        sample = ROOT.parent / "holographic-cherry-blossom-card"
        art = sample / "card-face-final.png"
        keyed = sample / "subject-keyed.png"
        if not art.is_file() or not keyed.is_file():
            self.skipTest("current cherry blossom regression assets are not available")
        keyed_image = PREPARE.load_image(keyed, "keyed image")
        alpha, preflight, family = PREPARE.adaptive_chroma_mask(keyed_image, "auto")
        self.assertEqual(family, "green")
        self.assertEqual(preflight["estimatedKey"], [20, 235, 22])
        self.assertEqual(preflight["cornerCoverages"], [1.0, 1.0, 1.0, 1.0])
        self.assertGreater(PREPARE.validate_alpha(alpha)["alphaCoverage"], 0.10)

        output = self.root / "current-subject.png"
        with patch.object(PREPARE, "local_mask") as local:
            with self.assertRaisesRegex(PREPARE.AlignmentError, "does not align"):
                PREPARE.prepare_subject(art, keyed, "auto", "human", output)
        local.assert_not_called()
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
