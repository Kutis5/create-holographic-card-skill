#!/usr/bin/env python3
"""Contract tests for the optimized skill workflow and final summary."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


class WorkflowContractTests(unittest.TestCase):
    def test_skill_uses_path_only_intermediates_and_parallel_layer_edits(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("inspect_card_face.py", skill)
        self.assertIn("output_hint", skill)
        self.assertIn("generatedImage", skill)
        self.assertIn("in parallel", skill)
        self.assertIn("one minimal Browser navigation", skill)
        self.assertIn("Generate the card face exactly once", skill)
        self.assertIn("hard maximum of three image generations", skill)
        self.assertIn("preserve the source field of view", skill)
        self.assertIn("--key-color auto", skill)
        self.assertNotIn("open_in_browser", skill)
        self.assertNotIn("elapsedMs", skill)

    def test_ratio_only_route_forbids_outpainting_and_subject_completion(self) -> None:
        card_spec = (ROOT / "references" / "card-face-spec.md").read_text(encoding="utf-8")
        prompt_ir = (ROOT / "references" / "image-prompt-ir.md").read_text(encoding="utf-8")
        self.assertIn("ratio-only EDIT", card_spec)
        self.assertIn("every existing crop boundary", card_spec)
        self.assertIn("forbid zooming out, outpainting, completing the body", card_spec)
        self.assertIn("do not regenerate the card face", prompt_ir)

    def test_layer_contract_uses_adaptive_keying_and_original_rgb(self) -> None:
        contract = (ROOT / "references" / "layered-card-assets.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Do not require diffusion output to equal an exact RGB triplet", contract)
        self.assertIn("connected to the canvas edge", contract)
        self.assertIn("every visible RGB pixel comes from the accepted art", contract)
        self.assertIn("shifted, scaled, or restaged keyed subject is a hard failure", contract)

    def test_material_guidance_adapts_foil_to_the_artwork(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        material_api = (ROOT / "references" / "material-api.md").read_text(encoding="utf-8")
        self.assertIn("restrained silver mode", skill)
        self.assertIn("foil `0.28`, texture `0.32`, glare `0.36`", skill)
        self.assertIn("flagship rainbow mode", skill)
        self.assertNotIn("Unless the user explicitly overrides them, use foil `0.78`", skill)
        self.assertIn("HSL 饱和度不超过 20%", material_api)
        self.assertIn("#b7bcc3", material_api)
        self.assertIn("静止态不得改变主体固有颜色", material_api)

    def test_summary_schema_is_strict_and_contains_no_binary_fields(self) -> None:
        schema = json.loads(
            (ROOT / "references" / "workflow-summary.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 1)
        self.assertFalse(schema["additionalProperties"])
        counts = schema["properties"]["imageGenerationCount"]["properties"]
        self.assertEqual(counts["cardFace"]["maximum"], 1)
        self.assertEqual(counts["background"]["maximum"], 1)
        self.assertEqual(counts["keyed"]["maximum"], 1)
        self.assertEqual(
            schema["properties"]["segmentationMethod"]["enum"],
            ["adaptive-chroma", "chroma-guided-local", "local-fallback"],
        )
        self.assertEqual(
            set(schema["required"]),
            {
                "schemaVersion",
                "imageGenerationCount",
                "segmentationMethod",
                "fallbackReason",
                "outputs",
                "validation",
                "previewWarnings",
            },
        )
        encoded = json.dumps(schema)
        for forbidden in ("data:image", "image_url", "elapsedMs", "open_in_browser"):
            self.assertNotIn(forbidden, encoded)

    def test_current_girl_card_regression_assets_remain_valid(self) -> None:
        sample = ROOT.parent / "holographic-card"
        art_path = sample / "art.png"
        subject_path = sample / "subject.png"
        if not art_path.is_file() or not subject_path.is_file():
            self.skipTest("workspace regression card is not installed with the skill")

        with Image.open(art_path) as art:
            self.assertEqual(art.size, (1060, 1484))
            self.assertAlmostEqual(art.width / art.height, 5 / 7, places=6)
        with Image.open(subject_path) as subject:
            alpha = subject.convert("RGBA").getchannel("A")
            thresholded = alpha.point(lambda value: 255 if value > 8 else 0)
            coverage = thresholded.histogram()[255] / (alpha.width * alpha.height)
            self.assertGreaterEqual(coverage, 0.01)
            self.assertLessEqual(coverage, 0.94)
            self.assertAlmostEqual(coverage, 0.768, places=3)
            self.assertNotEqual(thresholded.getbbox(), (0, 0, alpha.width, alpha.height))


if __name__ == "__main__":
    unittest.main(verbosity=2)
