#!/usr/bin/env python3
"""Regression tests for the Cardex hcard exporter."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("export_hcard", ROOT / "scripts" / "export_hcard.py")
assert SPEC and SPEC.loader
EXPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)


class ExportHcardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.background = self.root / "background.png"
        Image.new("RGB", (500, 700), (16, 18, 30)).save(self.background)
        self.subject = self.root / "subject.png"
        subject = Image.new("RGBA", (500, 700), (0, 0, 0, 0))
        ImageDraw.Draw(subject).ellipse((160, 100, 340, 610), fill=(220, 195, 255, 255))
        subject.save(self.subject)
        self.presentation = self.root / "presentation.json"
        self.presentation.write_text(json.dumps({"version": 2}), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_exports_lossless_layers_and_thumbnail(self) -> None:
        result = EXPORTER.export_hcard(
            card_id="sample-001", title="样卡", series="测试", serial_number="001",
            author="Cardex", rarity="限定", background_path=self.background,
            subject_path=self.subject, presentation_path=self.presentation,
            output=self.root / "sample.hcard", copy={"isFavorite": True, "tags": ["测试"]},
        )
        with zipfile.ZipFile(result) as package:
            self.assertEqual(set(package.namelist()), {
                "manifest.json", "presentation.json", "assets/background.webp",
                "assets/subject.webp", "assets/thumbnail.webp",
            })
            manifest = json.loads(package.read("manifest.json"))
            self.assertEqual(manifest["copy"]["tags"], ["测试"])
            for asset in manifest["assets"].values():
                payload = package.read(asset["path"])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), asset["sha256"])
                with Image.open(__import__("io").BytesIO(payload)) as decoded:
                    self.assertEqual(decoded.size, (asset["width"], asset["height"]))
            with Image.open(__import__("io").BytesIO(package.read("assets/subject.webp"))) as subject:
                self.assertLess(subject.getchannel("A").getextrema()[0], 255)

    def test_refuses_nonmatching_subject_canvas(self) -> None:
        wrong = self.root / "wrong.png"
        Image.new("RGBA", (250, 350), (0, 0, 0, 0)).save(wrong)
        with self.assertRaisesRegex(ValueError, "same canvas"):
            EXPORTER.export_hcard(
                card_id="sample-001", title="样卡", series="测试", serial_number="001",
                author="Cardex", rarity="限定", background_path=self.background,
                subject_path=wrong, presentation_path=self.presentation,
                output=self.root / "sample.hcard",
            )


if __name__ == "__main__":
    unittest.main()
