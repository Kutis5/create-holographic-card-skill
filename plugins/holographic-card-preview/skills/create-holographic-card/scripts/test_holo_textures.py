#!/usr/bin/env python3
"""Validate the original holographic texture asset pack."""

from __future__ import annotations

import hashlib
import json
import math
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "react-template" / "holo-textures"
MATERIALS = ("clear-coat", "pearl", "brushed-metal", "spectral-lines", "etched-holo", "cosmic-flake", "star-holo")
SHARED = ("blue-noise", "micro-grain")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixels_sha256(image: Image.Image) -> str:
    return hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()


class HoloTextureAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))

    def test_manifest_and_required_assets(self) -> None:
        self.assertEqual(self.manifest["schemaVersion"], 1)
        self.assertEqual(self.manifest["version"], "1.1.0")
        self.assertEqual(set(self.manifest["assets"]), set(MATERIALS))
        self.assertEqual(set(self.manifest["shared"]), set(SHARED))
        self.assertEqual(self.manifest["channelContract"], {"R": "microHeight", "G": "roughness", "B": "flakeDefectDensity", "A": "anisotropyDirection0To2Pi"})
        self.assertFalse(self.manifest["sourceGeneration"]["thirdPartyCodeOrAssets"])
        self.assertEqual(self.manifest["sourceGeneration"]["externalUrls"], [])

    def test_runtime_images_are_lossless_rgba_and_hash_matched(self) -> None:
        for group, names in (("assets", MATERIALS), ("shared", SHARED)):
            for name in names:
                record = self.manifest[group][name]
                path = ASSETS / record["runtime"]
                self.assertTrue(path.is_file(), path)
                self.assertEqual(record["encoding"], "lossless-webp")
                self.assertEqual(sha256(path), record["sha256"])
                with Image.open(path) as raw:
                    self.assertEqual(raw.size, (512, 512))
                    image = raw.convert("RGBA")
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(pixels_sha256(image), record["pixelSha256"])

    def test_material_channels_have_variance_and_seam_safety(self) -> None:
        for name in MATERIALS:
            record = self.manifest["assets"][name]
            for channel in "RGBA":
                stats = record["channelStats"][channel]
                self.assertGreater(stats["max"], stats["min"], f"{name}.{channel} is flat")
                self.assertGreater(stats["stddev"], 4.0, f"{name}.{channel} variance is too low")
                self.assertLessEqual(record["edgeMae"][channel], 0.035, f"{name}.{channel} seam exceeds limit")

    def test_cosmic_flake_density_is_sparse(self) -> None:
        coverage = self.manifest["assets"]["cosmic-flake"]["densityCoverage"]
        self.assertGreaterEqual(coverage, 0.01)
        self.assertLessEqual(coverage, 0.08)

    def test_star_holo_counts_and_density(self) -> None:
        record = self.manifest["assets"]["star-holo"]
        self.assertGreaterEqual(record["mainStarCount"], 12)
        self.assertLessEqual(record["mainStarCount"], 18)
        self.assertGreaterEqual(record["microStarCount"], 30)
        self.assertLessEqual(record["microStarCount"], 50)
        self.assertGreaterEqual(record["densityCoverage"], 0.025)
        self.assertLessEqual(record["densityCoverage"], 0.12)

    def test_star_holo_build_is_pixel_deterministic(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_holo_textures", ROOT / "scripts" / "build_holo_textures.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(module)
        source = ASSETS / self.manifest["assets"]["star-holo"]["source"]
        first, first_meta = module.build_star_holo(source)
        second, second_meta = module.build_star_holo(source)
        self.assertEqual(first_meta, second_meta)
        self.assertEqual(pixels_sha256(first), pixels_sha256(second))

    def test_sources_prompts_and_contact_sheet_exist(self) -> None:
        for name in MATERIALS:
            record = self.manifest["assets"][name]
            source = ASSETS / record["source"]
            self.assertTrue(source.is_file(), source)
            self.assertEqual(sha256(source), record["sourceSha256"])
            self.assertTrue(record["prompt"].strip())
        sheet = ASSETS / self.manifest["contactSheet"]["path"]
        self.assertTrue(sheet.is_file())
        self.assertEqual(sha256(sheet), self.manifest["contactSheet"]["sha256"])
        with Image.open(sheet) as image:
            self.assertGreater(image.width, 700)
            self.assertGreater(image.height, 800)

    def test_manifest_contains_no_external_or_reference_material(self) -> None:
        payload = json.dumps(self.manifest, ensure_ascii=False).lower()
        for forbidden in ("data:image", "http://", "https://", "pokemon", "simey", "github.com"):
            self.assertNotIn(forbidden, payload)
        self.assertLess(len(payload), 100_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
