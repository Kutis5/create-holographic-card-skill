#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, re, subprocess, sys, tempfile, unittest
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("holo_preview_server", ROOT / "mcp" / "server.py"); assert SPEC and SPEC.loader
SERVER = importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name] = SERVER; SPEC.loader.exec_module(SERVER)

def assert_binary_free(test, value):
    if isinstance(value, dict):
        test.assertNotIn("image_url", value)
        for item in value.values(): assert_binary_free(test, item)
    elif isinstance(value, list):
        for item in value: assert_binary_free(test, item)
    elif isinstance(value, str):
        test.assertFalse(value.startswith("data:image"))
        test.assertLessEqual(len(value), 8192)

def presentation(material="clear-coat"):
    return {"version": 2, "frame": {"style": "hairline", "width": .45, "color": "#75808f"}, "radius": {"outer": 4.8}, "surface": {"color": "#070a0f", "accent": "#a7d9e8", "material": material}, "foil": {"enabled": True, "target": "background", "colors": ["#a7d9e8", "#8e80c2"], "intensity": .16}, "texture": {"kind": "micro-grain", "target": "background", "intensity": .1}, "sparkle": {"enabled": False, "target": "background", "intensity": 0}, "glare": {"enabled": True, "target": "surface", "intensity": .15}, "depth": {"parallaxX": 1.2, "parallaxY": 1, "lift": 16, "shadowOpacity": .18, "shadowBlur": 16, "rimIntensity": .12}, "motion": {"maxX": 8, "maxY": 6, "scale": 1.008, "smoothing": .18}, "constraints": {"keepInsideFrame": True}}

class PreviewServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name); SERVER.PREVIEW_STORE.clear(); SERVER.PREVIEW_STORE_BYTES = 0
    def tearDown(self): self.temp.cleanup()
    def background(self, name="background.png", size=(700, 980)):
        path = self.root / name; Image.new("RGB", size, (15, 22, 31)).save(path); return path
    def subject(self, name="subject.png", size=(700, 980), full=False, alpha=True):
        path = self.root / name
        if not alpha: Image.new("RGB", size, (210, 210, 220)).save(path); return path
        image = Image.new("RGBA", size, (0, 0, 0, 0)); draw = ImageDraw.Draw(image)
        draw.ellipse((0, 0, size[0]-1, size[1]-1) if full else (180, 170, 540, 900), fill=(220, 225, 235, 255)); image.save(path); return path
    def arguments(self, **extra):
        return {"background_path": str(self.background()), "subject_path": str(self.subject()), "art_alt": "Monochrome portrait", "presentation": presentation(), **extra}
    def test_v5_protocol_has_one_tool(self):
        initialized = SERVER.handle_rpc({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}})
        self.assertEqual(initialized["result"]["serverInfo"]["version"], "0.9.0")
        tools = SERVER.handle_rpc({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["preview_holographic_card"])
        self.assertIn("full-bleed 5:7", tools[0]["description"]); self.assertIn("right-side Browser panel", tools[0]["description"])
        self.assertNotIn("content", tools[0]["inputSchema"]["properties"]); self.assertNotIn("candidates", tools[0]["inputSchema"]["properties"])
        self.assertNotIn("open_in_browser", tools[0]["inputSchema"]["properties"])
        self.assertEqual(tools[0]["inputSchema"]["properties"]["presentation"]["properties"]["version"]["const"], 2)
        self.assertEqual(tools[0]["inputSchema"]["properties"]["presentation"]["properties"]["frame"]["properties"]["colorMode"]["enum"], ["fixed", "image"])
    def test_preview_assets_and_payload(self):
        result = SERVER.call_tool("preview_holographic_card", self.arguments())["structuredContent"]
        self.assertEqual(result["schemaVersion"], 5); self.assertEqual(result["subject"]["hasAlpha"], True); self.assertEqual(result["resolvedPresentation"]["radius"]["inner"], 4.35)
        assert_binary_free(self, result)
        config = json.loads(urlopen(result["previewUrl"].replace("/preview/", "/api/preview/")).read())
        self.assertEqual(config["schemaVersion"], 5); self.assertIn("backgroundUrl", config); self.assertIn("subjectUrl", config)
        subject = Image.open(BytesIO(urlopen(result["previewUrl"].split("/preview/")[0] + config["subjectUrl"]).read()))
        self.assertIn("A", subject.getbands())
        base = result["previewUrl"].split("/preview/")[0]
        for name in SERVER.HOLO_TEXTURE_NAMES:
            response = urlopen(f"{base}/assets/holo-textures/{name}")
            self.assertEqual(response.headers.get_content_type(), "image/webp")
            self.assertEqual(response.read(), SERVER.HOLO_TEXTURE_BYTES[name])
            self.assertIn("img-src 'self'", response.headers["Content-Security-Policy"])
        palette_response = urlopen(f"{base}/assets/frame-palette.js")
        self.assertEqual(palette_response.headers.get_content_type(), "text/javascript")
        self.assertEqual(palette_response.read(), SERVER.FRAME_PALETTE_BYTES)
        self.assertIn("default-src 'self'", palette_response.headers["Content-Security-Policy"])
        optical_response = urlopen(f"{base}/assets/optical-state.js")
        self.assertEqual(optical_response.read(), SERVER.OPTICAL_STATE_BYTES)
    def test_flagship_defaults_and_explicit_values(self):
        defaulted = presentation(); defaulted["frame"] = {}; defaulted["radius"] = {}; defaulted["motion"] = {}
        resolved, warnings = SERVER.normalize_presentation(defaulted)
        self.assertEqual(resolved["frame"], {"style": "narrow", "width": .65, "color": "#75808f", "colorMode": "fixed"})
        self.assertEqual(resolved["radius"], {"outer": 5.8, "inner": 5.15})
        self.assertEqual(resolved["motion"], {"maxX": 14, "maxY": 14, "scale": 1.024, "smoothing": .18})
        self.assertEqual(warnings, [])
        explicit = presentation(); explicit["motion"] = {"maxX": 4, "maxY": 3, "scale": 1.004, "smoothing": .24}
        resolved, _ = SERVER.normalize_presentation(explicit)
        self.assertEqual(resolved["frame"]["width"], .45); self.assertEqual(resolved["radius"]["outer"], 4.8)
        self.assertEqual(resolved["motion"], explicit["motion"]); self.assertEqual(resolved["depth"], explicit["depth"])
        adaptive = presentation(); adaptive["frame"]["colorMode"] = "image"
        resolved, warnings = SERVER.normalize_presentation(adaptive)
        self.assertEqual(resolved["frame"]["colorMode"], "image"); self.assertEqual(warnings, [])
        bad = presentation(); bad["frame"]["colorMode"] = "dominant"
        with self.assertRaisesRegex(ValueError, "Unknown colorMode"): SERVER.normalize_presentation(bad)
        six = presentation(); six["foil"]["colors"] = ["#110000", "#221100", "#002200", "#002222", "#000033", "#330033"]
        resolved, _ = SERVER.normalize_presentation(six)
        self.assertEqual(resolved["foil"]["colors"], six["foil"]["colors"])
    def test_rejects_invalid_layers_and_legacy_arguments(self):
        with self.assertRaisesRegex(ValueError, "Alpha channel"): SERVER.call_tool("preview_holographic_card", self.arguments(subject_path=str(self.subject("flat.png", alpha=False))))
        with self.assertRaisesRegex(ValueError, "full canvas"): SERVER.call_tool("preview_holographic_card", self.arguments(subject_path=str(self.subject("full.png", full=True))))
        with self.assertRaisesRegex(ValueError, "identical canvas"): SERVER.call_tool("preview_holographic_card", self.arguments(subject_path=str(self.subject("wrong.png", (500, 700)))))
        with self.assertRaisesRegex(ValueError, "Unknown v5 arguments"): SERVER.call_tool("preview_holographic_card", self.arguments(candidates=[]))
        with self.assertRaisesRegex(ValueError, "Unknown tool"): SERVER.call_tool("select_holographic_card_candidate", {})
    def test_rejects_material_conflicts_and_depth_bounds(self):
        bad = presentation("cosmic-flake"); bad["texture"]["kind"] = "sparse-flake"
        with self.assertRaisesRegex(ValueError, "already includes particles"): SERVER.call_tool("preview_holographic_card", self.arguments(presentation=bad))
        bad = presentation(); bad["depth"]["lift"] = 29
        with self.assertRaisesRegex(ValueError, "depth.lift"): SERVER.call_tool("preview_holographic_card", self.arguments(presentation=bad))
        bad = presentation(); bad["surface"]["material"] = "rainbow"
        with self.assertRaisesRegex(ValueError, "Unknown material"): SERVER.call_tool("preview_holographic_card", self.arguments(presentation=bad))
        bad = presentation("pearl"); bad["texture"]["kind"] = "scanline"
        with self.assertRaisesRegex(ValueError, "not compatible"): SERVER.call_tool("preview_holographic_card", self.arguments(presentation=bad))
        bad = presentation("etched-holo"); bad["sparkle"]["enabled"] = True
        with self.assertRaisesRegex(ValueError, "sparkle is only valid"): SERVER.call_tool("preview_holographic_card", self.arguments(presentation=bad))
        bad = presentation("star-holo"); bad["sparkle"]["enabled"] = True; bad["sparkle"]["intensity"] = .3
        with self.assertRaisesRegex(ValueError, "cannot enable generic sparkle"): SERVER.call_tool("preview_holographic_card", self.arguments(presentation=bad))
        bad = presentation("star-holo"); bad["texture"]["kind"] = "sparse-flake"
        with self.assertRaisesRegex(ValueError, "not compatible"): SERVER.call_tool("preview_holographic_card", self.arguments(presentation=bad))
        bad = presentation(); bad["css"] = "filter: blur(8px)"
        with self.assertRaisesRegex(ValueError, "Unknown presentation fields"): SERVER.call_tool("preview_holographic_card", self.arguments(presentation=bad))
        bad = presentation(); bad["foil"]["colors"] = ["https://example.com/foil.png"]
        with self.assertRaisesRegex(ValueError, "Invalid color"): SERVER.call_tool("preview_holographic_card", self.arguments(presentation=bad))

    def test_surface_patterns_are_restricted_with_warnings(self):
        requested = presentation("spectral-lines")
        requested["foil"]["target"] = "surface"; requested["texture"]["target"] = "surface"
        result = SERVER.call_tool("preview_holographic_card", self.arguments(presentation=requested))["structuredContent"]
        self.assertEqual(result["resolvedPresentation"]["foil"]["target"], "background")
        self.assertEqual(result["resolvedPresentation"]["texture"]["target"], "background")
        self.assertEqual(len(result["warnings"]), 2)
        clear = presentation("clear-coat"); clear["foil"]["target"] = "surface"
        resolved, warnings = SERVER.normalize_presentation(clear)
        self.assertEqual(resolved["foil"]["target"], "surface"); self.assertEqual(warnings, [])
    def test_dom_layer_order_and_no_card_copy(self):
        html = (ROOT / "assets" / "preview.html").read_text(encoding="utf-8")
        order = [html.index(token) for token in ('id="material-canvas"', 'id="background"', 'id="subject-shadow"', 'id="subject"')]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("subject-rim", html)
        preview = (ROOT / "assets" / "preview.js").read_text(encoding="utf-8")
        self.assertNotIn("subjectRim", preview)
        self.assertNotIn("--rim-opacity", preview)
        css = (ROOT / "assets" / "card-renderer.css").read_text(encoding="utf-8")
        self.assertNotIn(".subjectRim", css)
        self.assertNotIn("repeating-linear-gradient", css)
        self.assertIn(".materialCanvas{z-index:1}", css)
        self.assertIn(".subjectShadow{z-index:2", css)
        self.assertIn(".subject{z-index:3", css)
        self.assertIn('type="module"', html)
        self.assertIn('role="alert"', html)
        self.assertIn('id="card" class="card" tabindex="0" hidden', html)
        self.assertIn('id="toolbar" class="toolbar" hidden', html)
        for token in ("candidate", "description", "tag", "serial", "edition", "guides"): self.assertNotIn(token, html.lower())
    def test_preview_script_uses_the_token_from_the_current_url(self):
        preview = (ROOT / "assets" / "preview.js").read_text(encoding="utf-8")
        self.assertIn('const previewMatch = /^\\/preview\\/([A-Za-z0-9_-]{32,96})$/.exec(location.pathname);', preview)
        self.assertIn('const id = previewMatch?.[1];', preview)
        self.assertIn('fetch(`/api/preview/${id}`, { cache: "no-store" })', preview)
        self.assertNotIn('const id = "sakura";', preview)
    def test_subject_layer_stays_composited_and_decoded_before_render(self):
        preview = (ROOT / "assets" / "preview.js").read_text(encoding="utf-8")
        css = (ROOT / "assets" / "card-renderer.css").read_text(encoding="utf-8")
        self.assertIn('await Promise.all([background.decode(), subject.decode(), subjectShadow.decode()]);', preview)
        self.assertIn('calc(var(--subject-z) + .01px)', css)
        for selector, z_index in (("subjectShadow", 2), ("subject", 3)):
            rule = re.search(rf"\.{selector}\{{z-index:{z_index};[^}}]*\}}", css)
            self.assertIsNotNone(rule)
            self.assertIn("backface-visibility:hidden", rule.group())
            self.assertIn("-webkit-backface-visibility:hidden", rule.group())
            self.assertIn("transform-style:preserve-3d", rule.group())

    def test_pointer_input_is_coalesced_into_one_shared_frame_clock(self):
        preview = (ROOT / "assets" / "preview.js").read_text(encoding="utf-8")
        engine = (ROOT / "assets" / "holo-engine.js").read_text(encoding="utf-8")
        self.assertIn('import { createPointerMotionController } from "/assets/pointer-motion.js";', preview)
        self.assertIn("event.getCoalescedEvents?.()", preview)
        self.assertIn("motion?.moveClient(sample.clientX, sample.clientY);", preview)
        self.assertIn("renderer.renderPointerFrame(nx, ny, now);", preview)
        self.assertNotIn("write(point.x, point.y);", preview)
        self.assertIn("function renderPointerFrame(x, y, now = performance.now())", engine)
        self.assertIn('mode = "external";', engine)
        self.assertIn("targetInterval - 0.25", engine)
    def test_javascript_parses(self):
        for name in ("preview.js", "holo-engine.js", "frame-palette.js", "optical-state.js", "pointer-motion.js"):
            result = subprocess.run(["node", "--check", str(ROOT / "assets" / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_recipe_registry_and_renderer_are_deterministic(self):
        js = (ROOT / "assets" / "holo-engine.js").read_text(encoding="utf-8")
        css = (ROOT / "assets" / "card-renderer.css").read_text(encoding="utf-8")
        for family in SERVER.MATERIALS: self.assertIn(family, js)
        self.assertIn("NEUTRAL_REVEAL = IDLE_REVEAL", js)
        self.assertIn("flagshipOptics", js)
        self.assertIn("MAX_DEVICE_PIXEL_RATIO = 2", js)
        canonical_path = ROOT.parents[1] / "create-holographic-card" / "assets" / "react-template" / "holo-engine.js"
        if canonical_path.is_file():
            self.assertEqual((ROOT / "assets" / "holo-engine.js").read_bytes(), canonical_path.read_bytes())
        else:
            self.assertIn("buildFragmentShader", js)
        canonical_palette = ROOT.parents[1] / "create-holographic-card" / "assets" / "react-template" / "frame-palette.js"
        self.assertEqual((ROOT / "assets" / "frame-palette.js").read_bytes(), canonical_palette.read_bytes())
        canonical_optical = ROOT.parents[1] / "create-holographic-card" / "assets" / "react-template" / "optical-state.js"
        self.assertEqual((ROOT / "assets" / "optical-state.js").read_bytes(), canonical_optical.read_bytes())
        canonical_pointer_motion = ROOT.parents[1] / "create-holographic-card" / "assets" / "react-template" / "pointer-motion.js"
        self.assertEqual((ROOT / "assets" / "pointer-motion.js").read_bytes(), canonical_pointer_motion.read_bytes())
        canonical_textures = ROOT.parents[1] / "create-holographic-card" / "assets" / "react-template" / "holo-textures"
        for name in (*SERVER.HOLO_TEXTURE_NAMES, "manifest.json"):
            self.assertEqual((ROOT / "assets" / "holo-textures" / name).read_bytes(), (canonical_textures / name).read_bytes())
        preview_js = (ROOT / "assets" / "preview.js").read_text(encoding="utf-8")
        self.assertIn("await renderer.ready()", preview_js)
        self.assertIn("__holoPreviewDiagnostics", preview_js)
        self.assertNotIn('url("http://', css); self.assertNotIn('url("https://', css)

    def test_skill_uses_one_minimal_browser_navigation(self):
        skill = (ROOT / "skills" / "preview-holographic-card" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("one minimal Browser navigation", skill)
        self.assertIn("deliverable", skill)
        self.assertIn("restrained silver foil", skill)
        self.assertIn("foil `0.28`, texture `0.32`, glare `0.36`", skill)
        self.assertIn("flagship rainbow palette", skill)
        self.assertNotIn("Unless explicitly overridden, use foil `0.78`", skill)
        self.assertNotIn("open_in_browser", skill)

if __name__ == "__main__": unittest.main(verbosity=2)
