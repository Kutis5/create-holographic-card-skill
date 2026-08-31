#!/usr/bin/env python3
"""Loopback MCP preview service for layered Card Presentation IR v2."""
from __future__ import annotations

import io, json, math, re, secrets, sys, threading, time
from collections import OrderedDict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = ImageOps = None  # type: ignore[assignment]

SERVER_NAME, SERVER_VERSION = "holographic-card-preview", "0.10.0"
ROOT, ASSETS = Path(__file__).resolve().parents[1], Path(__file__).resolve().parents[1] / "assets"
PRESENTATION_SCHEMA_PATH = ROOT / "schemas" / "card-presentation-v2.schema.json"
MAX_SOURCE_BYTES, MAX_PIXELS, MAX_ASSET_BYTES = 25 * 1024 * 1024, 40_000_000, 2 * 1024 * 1024
ASSET_TTL_SECONDS, MAX_PREVIEWS, MAX_PREVIEW_STORE_BYTES = 15 * 60, 12, 32 * 1024 * 1024
HEX, TOKEN = re.compile(r"^#[0-9a-fA-F]{6}$"), re.compile(r"^[A-Za-z0-9_-]{32,96}$")
MATERIALS = {"clear-coat", "pearl", "brushed-metal", "spectral-lines", "etched-holo", "cosmic-flake", "star-holo"}
TEXTURES = {"none", "micro-grain", "scanline", "geometric", "contour", "sparse-flake"}
TARGETS, FRAMES = {"background", "surface", "frame"}, {"none", "hairline", "narrow", "double"}
FRAME_COLOR_MODES = {"fixed", "image"}
TEXTURE_COMPATIBILITY = {
    "clear-coat": {"none", "micro-grain", "scanline", "sparse-flake"},
    "pearl": {"none", "micro-grain", "contour", "sparse-flake"},
    "brushed-metal": {"none", "micro-grain", "scanline"},
    "spectral-lines": {"none", "micro-grain", "scanline"},
    "etched-holo": {"none", "micro-grain", "geometric", "contour"},
    "cosmic-flake": {"none", "micro-grain"},
    "star-holo": {"none", "micro-grain"},
}

def read_asset(name: str) -> bytes:
    path = ASSETS / name
    try: return path.read_bytes()
    except OSError as error: raise RuntimeError(f"Preview asset is missing at MCP startup: {path}") from error

HTML_BYTES, CSS_BYTES, JS_BYTES, ENGINE_BYTES, RENDERER_CSS_BYTES, FRAME_PALETTE_BYTES, OPTICAL_STATE_BYTES = (read_asset(name) for name in ("preview.html", "preview.css", "preview.js", "holo-engine.js", "card-renderer.css", "frame-palette.js", "optical-state.js"))
HOLO_TEXTURE_NAMES = (
    "clear-coat.webp", "pearl.webp", "brushed-metal.webp", "spectral-lines.webp",
    "etched-holo.webp", "cosmic-flake.webp", "star-holo.webp", "blue-noise.webp", "micro-grain.webp",
)
HOLO_TEXTURE_BYTES = {name: read_asset(f"holo-textures/{name}") for name in HOLO_TEXTURE_NAMES}
try: PRESENTATION_SCHEMA = json.loads(PRESENTATION_SCHEMA_PATH.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as error: raise RuntimeError(f"Presentation schema is missing or invalid: {PRESENTATION_SCHEMA_PATH}") from error
PREVIEW_STORE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
PREVIEW_STORE_BYTES = 0
HTTP_SERVER: ThreadingHTTPServer | None = None
HTTP_THREAD: threading.Thread | None = None
HTTP_LOCK = threading.Lock()

def plain(value: Any) -> bool: return isinstance(value, dict)
def text(value: Any, maximum: int = 160) -> str | None:
    if value is None: return None
    return str(value).strip()[:maximum] or None
def number(value: Any, minimum: float, maximum: float, fallback: float) -> float:
    try: value = float(value)
    except (TypeError, ValueError): return fallback
    return max(minimum, min(maximum, value)) if math.isfinite(value) else fallback
def required_number(raw: dict[str, Any], key: str, minimum: float, maximum: float) -> float:
    if key not in raw: raise ValueError(f"depth.{key} is required.")
    try: value = float(raw[key])
    except (TypeError, ValueError): raise ValueError(f"depth.{key} must be numeric.") from None
    if not math.isfinite(value) or value < minimum or value > maximum: raise ValueError(f"depth.{key} must be between {minimum} and {maximum}.")
    return value
def color(value: Any, fallback: str) -> str:
    if value is None: return fallback
    candidate = text(value, 7)
    if not candidate or not HEX.fullmatch(candidate): raise ValueError(f"Invalid color value: {value}.")
    return candidate
def choice(raw: dict[str, Any], key: str, allowed: set[str], fallback: str) -> str:
    candidate = text(raw.get(key), 32) or fallback
    if candidate not in allowed: raise ValueError(f"Unknown {key}: {candidate}.")
    return candidate
def ensure_keys(raw: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(raw) - allowed
    if unknown: raise ValueError(f"Unknown {label} fields: {', '.join(sorted(unknown))}.")
def error_result(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "structuredContent": {"ok": False, "error": message}, "isError": True}

def source_image(path_value: Any, label: str) -> tuple[Path, Any]:
    if Image is None: raise RuntimeError("Pillow is required to validate preview images.")
    path = Path(str(path_value or "")).expanduser().resolve()
    if not path.is_file(): raise ValueError(f"{label} does not exist: {path}")
    if path.stat().st_size > MAX_SOURCE_BYTES: raise ValueError(f"{label} exceeds the 25 MB source limit.")
    try:
        image = ImageOps.exif_transpose(Image.open(path)); image.load()
    except Exception as error: raise ValueError(f"{label} is not a readable image: {error}") from error
    if image.width * image.height > MAX_PIXELS: raise ValueError(f"{label} exceeds the decoded pixel limit.")
    if abs(image.width / image.height - 5 / 7) > 0.012: raise ValueError(f"{label} must use a 5:7 canvas.")
    return path, image

def encode_background(path_value: Any, label: str = "background_path") -> tuple[dict[str, Any], bytes, tuple[int, int]]:
    path, image = source_image(path_value, label)
    image = image.convert("RGB")
    output = io.BytesIO(); image.save(output, "WEBP", quality=90, method=6)
    data = output.getvalue()
    if len(data) > MAX_ASSET_BYTES: raise ValueError(f"{label} cannot be normalized below the preview asset limit.")
    info = {"name": path.name, "width": image.width, "height": image.height, "format": "webp", "bytes": len(data), "hasAlpha": False}
    return info, data, image.size

def encode_subject(path_value: Any, expected_size: tuple[int, int]) -> tuple[dict[str, Any], bytes]:
    path, image = source_image(path_value, "subject_path")
    if image.size != expected_size: raise ValueError("background_path and subject_path must have identical canvas dimensions.")
    if "A" not in image.getbands(): raise ValueError("subject_path must contain an Alpha channel.")
    image = image.convert("RGBA"); alpha = image.getchannel("A"); low, high = alpha.getextrema()
    if low >= 8 or high <= 247: raise ValueError("subject_path must contain both transparent and opaque pixels.")
    bbox = alpha.point(lambda value: 255 if value > 8 else 0).getbbox()
    if bbox is None or bbox == (0, 0, image.width, image.height): raise ValueError("subject alpha bounding box must not equal the full canvas.")
    sample = alpha.resize((100, 140)); pixels = sample.get_flattened_data() if hasattr(sample, "get_flattened_data") else sample.getdata()
    coverage = sum(1 for value in pixels if value > 8) / 14000
    if coverage < 0.01 or coverage > 0.94: raise ValueError("subject alpha coverage must be between 1% and 94%.")
    output = io.BytesIO(); image.save(output, "WEBP", lossless=True, method=6)
    data = output.getvalue()
    if len(data) > MAX_ASSET_BYTES: raise ValueError("subject_path cannot be normalized below the preview asset limit.")
    return {"name": path.name, "width": image.width, "height": image.height, "format": "webp", "bytes": len(data), "hasAlpha": True, "alphaBounds": list(bbox), "alphaCoverage": round(coverage, 4)}, data

def normalize_presentation(raw: Any) -> tuple[dict[str, Any], list[str]]:
    if not plain(raw): raise ValueError("presentation must be a Card Presentation IR v2 object.")
    if raw.get("version") not in (None, 2): raise ValueError("presentation.version must be 2.")
    ensure_keys(raw, {"version", "frame", "radius", "surface", "foil", "texture", "sparkle", "glare", "depth", "motion", "constraints"}, "presentation")
    frame_raw = raw.get("frame") if plain(raw.get("frame")) else {}
    ensure_keys(frame_raw, {"style", "width", "color", "colorMode"}, "frame")
    frame_width = number(frame_raw.get("width"), 0, .9, .65)
    radius_raw = raw.get("radius") if plain(raw.get("radius")) else {}
    ensure_keys(radius_raw, {"outer", "inner"}, "radius")
    outer = number(radius_raw.get("outer"), 2, 8, 5.8)
    inner = max(0, round(outer - frame_width, 3))
    surface_raw = raw.get("surface") if plain(raw.get("surface")) else {}
    ensure_keys(surface_raw, {"color", "accent", "material"}, "surface")
    material = choice(surface_raw, "material", MATERIALS, "clear-coat")
    foil_raw = raw.get("foil") if plain(raw.get("foil")) else {}
    texture_raw = raw.get("texture") if plain(raw.get("texture")) else {}
    sparkle_raw = raw.get("sparkle") if plain(raw.get("sparkle")) else {}
    glare_raw = raw.get("glare") if plain(raw.get("glare")) else {}
    ensure_keys(foil_raw, {"enabled", "target", "colors", "intensity"}, "foil")
    ensure_keys(texture_raw, {"kind", "target", "intensity"}, "texture")
    ensure_keys(sparkle_raw, {"enabled", "target", "intensity"}, "sparkle")
    ensure_keys(glare_raw, {"enabled", "target", "intensity"}, "glare")
    foil_target = choice(foil_raw, "target", TARGETS, "background")
    texture_kind = choice(texture_raw, "kind", TEXTURES, "none")
    texture_target = choice(texture_raw, "target", TARGETS, "background")
    sparkle_target = choice(sparkle_raw, "target", TARGETS, "background")
    glare_target = choice(glare_raw, "target", TARGETS, "surface")
    foil_enabled, sparkle_enabled = bool(foil_raw.get("enabled", True)), bool(sparkle_raw.get("enabled", False))
    foil_intensity = number(foil_raw.get("intensity"), 0, 1, .78) if foil_enabled else 0
    texture_intensity = number(texture_raw.get("intensity"), 0, 1, .48)
    sparkle_intensity = number(sparkle_raw.get("intensity"), 0, 1, .3) if sparkle_enabled else 0
    glare_intensity = number(glare_raw.get("intensity"), 0, 1, .62) if bool(glare_raw.get("enabled", True)) else 0
    if texture_kind not in TEXTURE_COMPATIBILITY[material]:
        if material == "cosmic-flake" and texture_kind == "sparse-flake": raise ValueError("cosmic-flake already includes particles and cannot use sparse-flake.")
        raise ValueError(f"texture {texture_kind} is not compatible with {material}.")
    if material == "star-holo" and sparkle_enabled: raise ValueError("star-holo has directional star highlights and cannot enable generic sparkle.")
    if sparkle_enabled and material not in {"clear-coat", "pearl", "cosmic-flake"}: raise ValueError("sparkle is only valid with clear-coat, pearl, or cosmic-flake.")
    warnings: list[str] = []
    if foil_target == "surface" and material != "clear-coat":
        foil_target = "background"; warnings.append("Patterned foil requested on surface was restricted to background.")
    if texture_target == "surface" and texture_kind != "none":
        texture_target = "background"; warnings.append("Patterned texture requested on surface was restricted to background.")
    if sparkle_target == "surface" and sparkle_enabled:
        sparkle_target = "background"; warnings.append("Sparkle requested on surface was restricted to background.")
    depth_raw = raw.get("depth") if plain(raw.get("depth")) else {}
    ensure_keys(depth_raw, {"parallaxX", "parallaxY", "lift", "shadowOpacity", "shadowBlur", "rimIntensity"}, "depth")
    depth = {
        "parallaxX": required_number(depth_raw, "parallaxX", 0, 2.5), "parallaxY": required_number(depth_raw, "parallaxY", 0, 2.5),
        "lift": required_number(depth_raw, "lift", 0, 28), "shadowOpacity": required_number(depth_raw, "shadowOpacity", 0, .3),
        "shadowBlur": required_number(depth_raw, "shadowBlur", 0, 28), "rimIntensity": required_number(depth_raw, "rimIntensity", 0, .25),
    }
    motion_raw = raw.get("motion") if plain(raw.get("motion")) else {}
    constraints_raw = raw.get("constraints") if plain(raw.get("constraints")) else {}
    ensure_keys(motion_raw, {"maxX", "maxY", "scale", "smoothing"}, "motion")
    ensure_keys(constraints_raw, {"keepInsideFrame"}, "constraints")
    if constraints_raw.get("keepInsideFrame") is not True: raise ValueError("constraints.keepInsideFrame must be true.")
    colors = [color(item, "#a7d9e8") for item in foil_raw.get("colors", [])[:6]] if isinstance(foil_raw.get("colors"), list) else []
    presentation = {
        "version": 2,
        "frame": {"style": choice(frame_raw, "style", FRAMES, "narrow"), "width": frame_width, "color": color(frame_raw.get("color"), "#75808f"), "colorMode": choice(frame_raw, "colorMode", FRAME_COLOR_MODES, "fixed")},
        "radius": {"outer": outer, "inner": inner},
        "surface": {"color": color(surface_raw.get("color"), "#070a0f"), "accent": color(surface_raw.get("accent"), "#a7d9e8"), "material": material},
        "foil": {"enabled": foil_enabled, "target": foil_target, "colors": colors or [color(surface_raw.get("accent"), "#a7d9e8")], "intensity": foil_intensity},
        "texture": {"kind": texture_kind, "target": texture_target, "intensity": texture_intensity},
        "sparkle": {"enabled": sparkle_enabled, "target": sparkle_target, "intensity": sparkle_intensity},
        "glare": {"enabled": glare_intensity > 0, "target": glare_target, "intensity": glare_intensity},
        "depth": depth,
        "motion": {"maxX": number(motion_raw.get("maxX"), 0, 14, 14), "maxY": number(motion_raw.get("maxY"), 0, 14, 14), "scale": number(motion_raw.get("scale"), 1, 1.05, 1.024), "smoothing": number(motion_raw.get("smoothing"), .08, .4, .18)},
        "constraints": {"keepInsideFrame": True},
    }
    return presentation, warnings

def cleanup_store(now: float | None = None) -> None:
    global PREVIEW_STORE_BYTES
    now = now or time.monotonic()
    for key in list(PREVIEW_STORE):
        if now - PREVIEW_STORE[key]["created"] > ASSET_TTL_SECONDS:
            entry = PREVIEW_STORE.pop(key); PREVIEW_STORE_BYTES -= entry["bytes"]
    while len(PREVIEW_STORE) > MAX_PREVIEWS or PREVIEW_STORE_BYTES > MAX_PREVIEW_STORE_BYTES:
        _, entry = PREVIEW_STORE.popitem(last=False); PREVIEW_STORE_BYTES -= entry["bytes"]

def store_preview(background: bytes, subject: bytes, back: bytes | None, payload: dict[str, Any]) -> str:
    global PREVIEW_STORE_BYTES
    cleanup_store(); preview_id = secrets.token_urlsafe(32); size = len(background) + len(subject) + len(back or b"")
    PREVIEW_STORE[preview_id] = {"created": time.monotonic(), "background": background, "subject": subject, "back": back, "payload": payload, "bytes": size}
    PREVIEW_STORE_BYTES += size; cleanup_store(); return preview_id

def preview_entry(preview_id: str) -> dict[str, Any] | None:
    cleanup_store(); entry = PREVIEW_STORE.get(preview_id)
    if entry: PREVIEW_STORE.move_to_end(preview_id)
    return entry

def make_handler() -> type[BaseHTTPRequestHandler]:
    class PreviewHandler(BaseHTTPRequestHandler):
        server_version = "HolographicPreview/5"
        def log_message(self, _format: str, *_args: Any) -> None: return
        def allowed_host(self) -> bool: return self.headers.get("Host", "") == f"127.0.0.1:{self.server.server_port}"
        def send_payload(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("Referrer-Policy", "no-referrer"); self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"); self.end_headers()
            if self.command != "HEAD": self.wfile.write(body)
        def do_GET(self) -> None: self.dispatch()
        def do_HEAD(self) -> None: self.dispatch()
        def do_POST(self) -> None: self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
        def dispatch(self) -> None:
            if not self.allowed_host(): self.send_error(HTTPStatus.BAD_REQUEST); return
            path = urlparse(self.path).path
            static = {"/assets/preview.css": (CSS_BYTES, "text/css; charset=utf-8"), "/assets/preview.js": (JS_BYTES, "text/javascript; charset=utf-8"), "/assets/holo-engine.js": (ENGINE_BYTES, "text/javascript; charset=utf-8"), "/assets/frame-palette.js": (FRAME_PALETTE_BYTES, "text/javascript; charset=utf-8"), "/assets/optical-state.js": (OPTICAL_STATE_BYTES, "text/javascript; charset=utf-8"), "/assets/card-renderer.css": (RENDERER_CSS_BYTES, "text/css; charset=utf-8")}
            if path in static: data, mime = static[path]; self.send_payload(HTTPStatus.OK, data, mime); return
            texture_match = re.fullmatch(r"/assets/holo-textures/([a-z-]+\.webp)", path)
            if texture_match and texture_match.group(1) in HOLO_TEXTURE_BYTES:
                self.send_payload(HTTPStatus.OK, HOLO_TEXTURE_BYTES[texture_match.group(1)], "image/webp"); return
            match = re.fullmatch(r"/(preview|api/preview|asset)/([A-Za-z0-9_-]{32,96})(?:/(background|subject|back)\.webp)?", path)
            if not match: self.send_error(HTTPStatus.NOT_FOUND); return
            kind, preview_id, side = match.groups(); entry = preview_entry(preview_id)
            if entry is None: self.send_error(HTTPStatus.GONE, "Preview expired or does not exist"); return
            if kind == "preview": self.send_payload(HTTPStatus.OK, HTML_BYTES, "text/html; charset=utf-8"); return
            if kind == "api/preview":
                payload = {**entry["payload"], "backgroundUrl": f"/asset/{preview_id}/background.webp", "subjectUrl": f"/asset/{preview_id}/subject.webp", "backUrl": f"/asset/{preview_id}/back.webp" if entry["back"] else None}
                self.send_payload(HTTPStatus.OK, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(), "application/json; charset=utf-8"); return
            data = entry.get(side)
            if not isinstance(data, bytes): self.send_error(HTTPStatus.NOT_FOUND); return
            self.send_payload(HTTPStatus.OK, data, "image/webp")
    return PreviewHandler

def ensure_http_server() -> str:
    global HTTP_SERVER, HTTP_THREAD
    with HTTP_LOCK:
        if HTTP_SERVER is None:
            HTTP_SERVER = ThreadingHTTPServer(("127.0.0.1", 0), make_handler()); HTTP_THREAD = threading.Thread(target=HTTP_SERVER.serve_forever, name="holographic-preview", daemon=True); HTTP_THREAD.start()
        return f"http://127.0.0.1:{HTTP_SERVER.server_port}"

def tool_definitions() -> list[dict[str, Any]]:
    schema = {"type": "object", "additionalProperties": False, "required": ["background_path", "subject_path", "art_alt", "presentation"], "properties": {"background_path": {"type": "string"}, "subject_path": {"type": "string"}, "art_alt": {"type": "string"}, "presentation": PRESENTATION_SCHEMA, "back_path": {"type": "string"}, "back_alt": {"type": "string"}}}
    return [{"name": "preview_holographic_card", "title": "Preview layered holographic card", "description": "Validate a full-bleed 5:7 background plate and transparent subject layer, then prepare one Card Presentation IR v2 preview for the right-side Browser panel.", "inputSchema": schema, "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}}]

def preview_card(arguments: dict[str, Any]) -> dict[str, Any]:
    allowed = {"background_path", "subject_path", "art_alt", "presentation", "back_path", "back_alt"}
    unknown = set(arguments) - allowed
    if unknown: raise ValueError(f"Unknown v5 arguments: {', '.join(sorted(unknown))}.")
    art_alt = text(arguments.get("art_alt"), 240)
    if not art_alt: raise ValueError("art_alt is required.")
    background_info, background_data, size = encode_background(arguments.get("background_path"))
    subject_info, subject_data = encode_subject(arguments.get("subject_path"), size)
    back_info = back_data = None
    if arguments.get("back_path"): back_info, back_data, _ = encode_background(arguments.get("back_path"), "back_path")
    presentation, warnings = normalize_presentation(arguments.get("presentation"))
    payload = {"schemaVersion": 5, "launchPolicy": "codex-browser-right", "artAlt": art_alt, "backAlt": text(arguments.get("back_alt"), 240), "presentation": presentation, "warnings": warnings, "background": background_info, "subject": subject_info, "back": back_info}
    preview_id = store_preview(background_data, subject_data, back_data, payload); base = ensure_http_server()
    result = {"schemaVersion": 5, "previewUrl": f"{base}/preview/{preview_id}", "warnings": warnings, "resolvedPresentation": presentation, "background": background_info, "subject": subject_info}
    return {"content": [{"type": "text", "text": "Layered 5:7 holographic card preview prepared for the right-side Browser."}], "structuredContent": result, "isError": False}

def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "preview_holographic_card": return preview_card(arguments)
    raise ValueError(f"Unknown tool: {name}")
def rpc_response(message_id: Any, result: Any) -> dict[str, Any]: return {"jsonrpc": "2.0", "id": message_id, "result": result}
def rpc_error(message_id: Any, code: int, message: str) -> dict[str, Any]: return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}
def handle_rpc(message: dict[str, Any]) -> dict[str, Any] | None:
    if not plain(message) or not isinstance(message.get("method"), str): return rpc_error(message.get("id") if plain(message) else None, -32600, "Invalid Request")
    method, message_id = message["method"], message.get("id"); params = message.get("params") if plain(message.get("params")) else {}
    try:
        if method.startswith("notifications/") or method == "$/cancelRequest": return None
        if method == "initialize": return rpc_response(message_id, {"protocolVersion": params.get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": SERVER_NAME, "title": "Holographic Card Preview", "version": SERVER_VERSION}})
        if method == "ping": return rpc_response(message_id, {})
        if method == "tools/list": return rpc_response(message_id, {"tools": tool_definitions()})
        if method == "resources/list": return rpc_response(message_id, {"resources": []})
        if method == "resources/templates/list": return rpc_response(message_id, {"resourceTemplates": []})
        if method == "tools/call":
            try: return rpc_response(message_id, call_tool(params.get("name"), params.get("arguments") if plain(params.get("arguments")) else {}))
            except (RuntimeError, ValueError) as error: return rpc_response(message_id, error_result(str(error)))
        return rpc_error(message_id, -32601, f"Method not found: {method}")
    except Exception as error: return rpc_error(message_id, -32000, str(error))
def run_stdio() -> None:
    for line in sys.stdin:
        if not line.strip(): continue
        try:
            response = handle_rpc(json.loads(line))
            if response is not None: sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"); sys.stdout.flush()
        except json.JSONDecodeError as error: sys.stdout.write(json.dumps(rpc_error(None, -32700, f"Parse error: {error}")) + "\n"); sys.stdout.flush()
if __name__ == "__main__": run_stdio()
