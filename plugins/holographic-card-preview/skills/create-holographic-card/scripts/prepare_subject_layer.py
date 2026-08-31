#!/usr/bin/env python3
"""Prepare a transparent subject layer from an adaptive chroma-key edit."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFilter = None  # type: ignore[assignment]


KEY_FAMILIES = {
    "green": (0, 255, 0),
    "magenta": (255, 0, 255),
}
KEY_ALIASES = {
    "auto": "auto",
    "green": "green",
    "magenta": "magenta",
    "#00ff00": "green",
    "#ff00ff": "magenta",
}
MIN_BORDER_FAMILY_COVERAGE = 0.65
MIN_CORNER_FAMILY_COVERAGE = 0.50
MAX_CLUSTER_SPREAD = 34.0
MIN_ALIGNMENT_SCORE = 0.45
MIN_ALPHA_COVERAGE = 0.01
MAX_ALPHA_COVERAGE = 0.94
MODEL_FILES = {
    "human": ("u2net_human_seg", "u2net_human_seg.onnx"),
    "generic": ("u2netp", "u2netp.onnx"),
}


class PreparationError(ValueError):
    """Raised when a subject layer cannot be prepared safely."""


class KeyPreflightError(PreparationError):
    """Raised when no stable, separable chroma background exists."""


class AlignmentError(PreparationError):
    """Raised when the keyed subject no longer aligns with the accepted art."""


def require_dependencies() -> None:
    if Image is None:
        raise RuntimeError("Pillow is required to prepare the subject layer.")
    if np is None:
        raise RuntimeError("NumPy is required to prepare the subject layer.")


def load_image(path: Path, label: str):
    require_dependencies()
    if not path.is_file():
        raise PreparationError(f"{label} does not exist: {path}")
    try:
        with Image.open(path) as source:
            source.load()
            image = source.copy()
    except Exception as error:
        raise PreparationError(f"{label} is not a readable image: {error}") from error
    return image


def validate_canvas(art, keyed) -> None:
    if art.size != keyed.size:
        raise PreparationError("art and keyed images must have identical canvas dimensions.")
    if abs(art.width / art.height - 5 / 7) > 0.012:
        raise PreparationError("art and keyed images must use a 5:7 canvas.")


def _rgb_to_lab(rgb):
    values = np.asarray(rgb, dtype=np.float32) / 255.0
    linear = np.where(
        values <= 0.04045,
        values / 12.92,
        ((values + 0.055) / 1.055) ** 2.4,
    )
    xyz = linear @ np.asarray(
        (
            (0.4124564, 0.3575761, 0.1804375),
            (0.2126729, 0.7151522, 0.0721750),
            (0.0193339, 0.1191920, 0.9503041),
        ),
        dtype=np.float32,
    ).T
    xyz /= np.asarray((0.95047, 1.0, 1.08883), dtype=np.float32)
    delta = 6 / 29
    transformed = np.where(
        xyz > delta**3,
        np.cbrt(xyz),
        xyz / (3 * delta**2) + 4 / 29,
    )
    lightness = 116 * transformed[..., 1] - 16
    a_axis = 500 * (transformed[..., 0] - transformed[..., 1])
    b_axis = 200 * (transformed[..., 1] - transformed[..., 2])
    return np.stack((lightness, a_axis, b_axis), axis=-1)


def _family_strength(rgb, family: str):
    values = np.asarray(rgb, dtype=np.int16)
    red, green, blue = values[..., 0], values[..., 1], values[..., 2]
    if family == "green":
        return green - np.maximum(red, blue)
    return np.minimum(red, blue) - green


def _border_masks(width: int, height: int):
    band = max(1, math.ceil(min(width, height) * 0.02))
    border = np.zeros((height, width), dtype=bool)
    border[:band, :] = True
    border[-band:, :] = True
    border[:, :band] = True
    border[:, -band:] = True
    corners = (
        np.s_[:band, :band],
        np.s_[:band, width - band :],
        np.s_[height - band :, :band],
        np.s_[height - band :, width - band :],
    )
    return band, border, corners


def _family_metrics(rgb, border, corners, family: str):
    family_pixels = _family_strength(rgb, family) >= 48
    border_coverage = float(np.mean(family_pixels[border]))
    corner_coverages = [float(np.mean(family_pixels[corner])) for corner in corners]
    return family_pixels, border_coverage, corner_coverages


def _connected_to_border(candidate):
    # Pillow can expose a read-only buffer for Image.fromarray(); floodfill needs
    # a writable copy or it silently leaves that buffer unchanged.
    binary = Image.fromarray(np.where(candidate, 255, 0).astype(np.uint8), "L").copy()
    pixels = binary.load()
    width, height = binary.size
    seeds = (
        [(x, 0) for x in range(width)]
        + [(x, height - 1) for x in range(width)]
        + [(0, y) for y in range(1, height - 1)]
        + [(width - 1, y) for y in range(1, height - 1)]
    )
    for seed in seeds:
        if pixels[seed] == 255:
            ImageDraw.floodfill(binary, seed, 128, thresh=0)
    return np.asarray(binary) == 128


def adaptive_chroma_mask(keyed, requested_key: str):
    rgb = np.asarray(keyed.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    band, border, corners = _border_masks(width, height)

    candidates: dict[str, tuple[Any, float, list[float]]] = {}
    for family in KEY_FAMILIES:
        candidates[family] = _family_metrics(rgb, border, corners, family)

    if requested_key == "auto":
        family = max(candidates, key=lambda value: candidates[value][1])
    else:
        family = requested_key
    family_pixels, border_coverage, corner_coverages = candidates[family]
    weakest_corner = min(corner_coverages)
    if border_coverage < MIN_BORDER_FAMILY_COVERAGE:
        raise KeyPreflightError(
            "keyed background has no dominant chroma family on the border: "
            f"{border_coverage:.3f} < {MIN_BORDER_FAMILY_COVERAGE:.2f}."
        )
    if weakest_corner < MIN_CORNER_FAMILY_COVERAGE:
        raise KeyPreflightError(
            "keyed background chroma is not connected through every corner: "
            f"{weakest_corner:.3f} < {MIN_CORNER_FAMILY_COVERAGE:.2f}."
        )

    border_family = border & family_pixels
    samples = rgb[border_family]
    estimated_rgb = np.median(samples, axis=0)
    lab = _rgb_to_lab(rgb)
    estimated_lab = _rgb_to_lab(estimated_rgb.reshape(1, 1, 3))[0, 0]
    delta = lab - estimated_lab
    distance = np.sqrt(
        delta[..., 1] ** 2 + delta[..., 2] ** 2 + 0.0625 * delta[..., 0] ** 2
    )
    border_distances = distance[border_family]
    cluster_spread = float(np.percentile(border_distances, 95))
    if cluster_spread > MAX_CLUSTER_SPREAD:
        raise KeyPreflightError(
            "keyed background chroma cluster is too dispersed: "
            f"{cluster_spread:.2f} > {MAX_CLUSTER_SPREAD:.2f}."
        )

    strong_threshold = float(np.clip(np.percentile(border_distances, 99) + 2.0, 6.0, 30.0))
    soft_threshold = float(np.clip(strong_threshold + max(8.0, cluster_spread), 14.0, 48.0))
    relaxed_family = _family_strength(rgb, family) >= 20
    connected = _connected_to_border((distance <= soft_threshold) & relaxed_family)
    connected_coverage = float(np.mean(connected[border]))
    if connected_coverage < MIN_BORDER_FAMILY_COVERAGE:
        raise KeyPreflightError(
            "keyed background does not form a connected border region: "
            f"{connected_coverage:.3f} < {MIN_BORDER_FAMILY_COVERAGE:.2f}."
        )

    span = max(soft_threshold - strong_threshold, 1.0)
    normalized = np.clip((distance - strong_threshold) / span, 0.0, 1.0)
    softened = normalized * normalized * (3.0 - 2.0 * normalized)
    alpha = np.full((height, width), 255.0, dtype=np.float32)
    alpha[connected] = softened[connected] * 255.0
    alpha_image = Image.fromarray(np.rint(alpha).astype(np.uint8), "L")
    blurred = np.asarray(alpha_image.filter(ImageFilter.GaussianBlur(0.65)), dtype=np.uint8)
    uncertain = connected & (distance > strong_threshold) & (distance < soft_threshold)
    alpha[uncertain] = blurred[uncertain]
    alpha_image = Image.fromarray(np.rint(alpha).astype(np.uint8), "L")

    preflight = {
        "requestedKey": requested_key,
        "selectedFamily": family,
        "estimatedKey": [int(round(value)) for value in estimated_rgb],
        "borderCoverage": round(border_coverage, 4),
        "cornerCoverages": [round(value, 4) for value in corner_coverages],
        "connectedBorderCoverage": round(connected_coverage, 4),
        "clusterSpread": round(cluster_spread, 4),
        "strongThreshold": round(strong_threshold, 4),
        "softThreshold": round(soft_threshold, 4),
        "borderBand": band,
    }
    return alpha_image, preflight, family


def model_cache() -> Path:
    configured = os.environ.get("U2NET_HOME")
    if configured:
        return Path(configured).expanduser()
    data_home = os.environ.get("XDG_DATA_HOME", "~")
    return Path(data_home).expanduser() / ".u2net"


def normalize_local_mask(mask):
    grayscale = mask.convert("L")
    transparent_at = 12
    opaque_at = 220

    def remap(value: int) -> int:
        if value <= transparent_at:
            return 0
        if value >= opaque_at:
            return 255
        ratio = (value - transparent_at) / (opaque_at - transparent_at)
        smooth = ratio * ratio * (3.0 - 2.0 * ratio)
        return max(0, min(255, int(round(smooth * 255))))

    return grayscale.point([remap(value) for value in range(256)])


def local_mask(art, subject_kind: str):
    model_name, filename = MODEL_FILES[subject_kind]
    cached_model = model_cache() / filename
    if not cached_model.is_file():
        raise PreparationError(
            f"local fallback model is not cached and will not be downloaded automatically: {cached_model}"
        )
    try:
        from rembg import new_session, remove
    except ImportError as error:
        raise PreparationError("rembg is required for the local subject fallback.") from error
    try:
        session = new_session(model_name)
        mask = remove(art.convert("RGB"), session=session, only_mask=True, post_process_mask=False)
    except Exception as error:
        raise PreparationError(f"local subject fallback failed with {model_name}: {error}") from error
    if isinstance(mask, bytes):
        with Image.open(BytesIO(mask)) as source:
            source.load()
            mask = source.copy()
    if not hasattr(mask, "convert"):
        raise PreparationError("local subject fallback returned an unsupported mask.")
    return normalize_local_mask(mask)


def chroma_guided_mask(adaptive_alpha, prior):
    adaptive = np.asarray(adaptive_alpha.convert("L"), dtype=np.float32)
    local = np.asarray(prior.convert("L"), dtype=np.float32)
    if adaptive.shape != local.shape:
        raise PreparationError("local guidance mask must use the same canvas dimensions.")
    uncertain = (adaptive > 4) & (adaptive < 251)
    if not np.any(uncertain):
        boundary = Image.fromarray((adaptive >= 128).astype(np.uint8) * 255, "L")
        outer = np.asarray(boundary.filter(ImageFilter.MaxFilter(5)), dtype=np.uint8) > 0
        inner = np.asarray(boundary.filter(ImageFilter.MinFilter(5)), dtype=np.uint8) > 0
        uncertain = outer ^ inner
    refined = adaptive.copy()
    refined[uncertain] = adaptive[uncertain] * 0.65 + local[uncertain] * 0.35
    return Image.fromarray(np.rint(refined).astype(np.uint8), "L")


def validate_alpha(alpha, expected_size: tuple[int, int] | None = None) -> dict[str, Any]:
    alpha = alpha.convert("L")
    if expected_size is not None and alpha.size != expected_size:
        raise PreparationError("subject Alpha must use the same canvas dimensions as the art.")
    low, high = alpha.getextrema()
    if low >= 8 or high <= 247:
        raise PreparationError("subject Alpha must contain meaningful transparent and opaque pixels.")
    thresholded = alpha.point(lambda value: 255 if value > 8 else 0)
    bbox = thresholded.getbbox()
    if bbox is None or bbox == (0, 0, alpha.width, alpha.height):
        raise PreparationError("subject Alpha bounding box must be smaller than the canvas.")
    histogram = thresholded.histogram()
    coverage = histogram[255] / (alpha.width * alpha.height)
    if coverage < MIN_ALPHA_COVERAGE or coverage > MAX_ALPHA_COVERAGE:
        raise PreparationError(
            f"subject Alpha coverage must be between 1% and 94%; received {coverage:.4f}."
        )
    coverage_value = round(coverage, 4)
    bounds_value = list(bbox)
    return {
        "alphaCoverage": coverage_value,
        "alphaBounds": bounds_value,
        "validation": {
            "canvas": [alpha.width, alpha.height],
            "ratio": round(alpha.width / alpha.height, 6),
            "hasTransparent": low < 8,
            "hasOpaque": high > 247,
            "alphaCoverage": coverage_value,
            "alphaBounds": bounds_value,
            "nonFullCanvasBounds": bbox != (0, 0, alpha.width, alpha.height),
        },
    }


def _gradient_magnitude(image):
    gray = np.asarray(image.convert("L"), dtype=np.float32) / 255.0
    dx = np.zeros_like(gray)
    dy = np.zeros_like(gray)
    dx[:, 1:-1] = np.abs(gray[:, 2:] - gray[:, :-2]) * 0.5
    dy[1:-1, :] = np.abs(gray[2:, :] - gray[:-2, :]) * 0.5
    return np.hypot(dx, dy)


def validate_alignment(art, keyed, alpha) -> dict[str, Any]:
    core = np.asarray(alpha.convert("L"), dtype=np.uint8) >= 224
    if int(np.count_nonzero(core)) < 64:
        raise AlignmentError("keyed subject has too few opaque pixels for alignment validation.")
    art_gradient = _gradient_magnitude(art)
    keyed_gradient = _gradient_magnitude(keyed)
    art_values = art_gradient[core]
    keyed_values = keyed_gradient[core]
    art_cutoff = float(np.percentile(art_values, 72))
    keyed_cutoff = float(np.percentile(keyed_values, 72))
    art_edges = core & (art_gradient >= max(art_cutoff, 0.02))
    keyed_edges = core & (keyed_gradient >= max(keyed_cutoff, 0.02))
    denominator = int(np.count_nonzero(art_edges)) + int(np.count_nonzero(keyed_edges))
    score = 1.0 if denominator == 0 else 2 * int(np.count_nonzero(art_edges & keyed_edges)) / denominator
    if score < MIN_ALIGNMENT_SCORE:
        raise AlignmentError(
            "keyed subject does not align with the accepted art: "
            f"{score:.3f} < {MIN_ALIGNMENT_SCORE:.2f}."
        )
    return {"alignmentScore": round(score, 4), "alignmentPassed": True}


def compose_original_rgb(art, alpha):
    rgba = art.convert("RGBA")
    alpha = alpha.convert("L")
    rgba.putalpha(alpha)
    visible = alpha.point(lambda value: 255 if value > 0 else 0)
    transparent = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    return Image.composite(rgba, transparent, visible)


def atomic_save_png(image, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.stem}.", suffix=".png", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        image.save(temporary, "PNG", compress_level=6)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def prepare_subject(
    art_path: Path,
    keyed_path: Path,
    key_color: str,
    subject_kind: str,
    output: Path,
) -> dict[str, Any]:
    normalized_key = key_color.lower()
    if normalized_key not in KEY_ALIASES:
        raise PreparationError(
            "--key-color must be auto, green, magenta, #00ff00, or #ff00ff."
        )
    requested_key = KEY_ALIASES[normalized_key]
    if subject_kind not in MODEL_FILES:
        raise PreparationError("--subject-kind must be human or generic.")
    if output.exists():
        raise PreparationError(f"output already exists and will not be overwritten: {output}")
    if output.suffix.lower() != ".png":
        raise PreparationError("--out must end in .png.")

    art = load_image(art_path, "art")
    keyed = load_image(keyed_path, "keyed image")
    validate_canvas(art, keyed)

    fallback_reason: str | None = None
    preflight: dict[str, Any] | None = None
    alignment: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = []
    selected_family: str | None = None
    try:
        alpha, preflight, selected_family = adaptive_chroma_mask(keyed, requested_key)
    except KeyPreflightError as error:
        fallback_reason = str(error)
        attempts.append(
            {"method": "adaptive-chroma", "status": "failed", "reason": fallback_reason}
        )
        attempts.append(
            {
                "method": "chroma-guided-local",
                "status": "skipped",
                "reason": "no usable chroma region",
            }
        )
        alpha = local_mask(art, subject_kind)
        metrics = validate_alpha(alpha, art.size)
        method = "local-fallback"
        attempts.append({"method": "local-fallback", "status": "passed"})
    else:
        try:
            metrics = validate_alpha(alpha, art.size)
            alignment = validate_alignment(art, keyed, alpha)
        except AlignmentError:
            raise
        except PreparationError as error:
            fallback_reason = str(error)
            attempts.append(
                {"method": "adaptive-chroma", "status": "failed", "reason": fallback_reason}
            )
            prior = local_mask(art, subject_kind)
            alpha = chroma_guided_mask(alpha, prior)
            metrics = validate_alpha(alpha, art.size)
            alignment = validate_alignment(art, keyed, alpha)
            method = "chroma-guided-local"
            attempts.append({"method": "chroma-guided-local", "status": "passed"})
            attempts.append({"method": "local-fallback", "status": "skipped"})
        else:
            method = "adaptive-chroma"
            attempts.append({"method": "adaptive-chroma", "status": "passed"})
            attempts.append({"method": "chroma-guided-local", "status": "skipped"})
            attempts.append({"method": "local-fallback", "status": "skipped"})

    subject = compose_original_rgb(art, alpha)
    atomic_save_png(subject, output)
    key_value = (
        "#%02x%02x%02x" % KEY_FAMILIES[selected_family]
        if selected_family is not None
        else None
    )
    return {
        "method": method,
        "keyMode": normalized_key,
        "keyColor": key_value,
        "fallbackReason": fallback_reason,
        "attempts": attempts,
        **metrics,
        "preflight": preflight,
        "alignment": alignment,
        "output": str(output.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--art", required=True)
    parser.add_argument("--keyed", required=True)
    parser.add_argument(
        "--key-color",
        default="auto",
        choices=sorted(KEY_ALIASES),
        help="Adaptive key family; defaults to auto and accepts legacy hex values.",
    )
    parser.add_argument("--subject-kind", required=True, choices=sorted(MODEL_FILES))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        report = prepare_subject(
            Path(args.art).resolve(),
            Path(args.keyed).resolve(),
            args.key_color,
            args.subject_kind,
            Path(args.out).resolve(),
        )
    except (PreparationError, RuntimeError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
