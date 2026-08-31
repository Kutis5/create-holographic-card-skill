#!/usr/bin/env python3
"""Build original, tileable RGBA holographic material atlases from source plates."""

from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


SIZE = 512
MATERIALS = (
    "clear-coat",
    "pearl",
    "brushed-metal",
    "spectral-lines",
    "etched-holo",
    "cosmic-flake",
    "star-holo",
)
CHANNELS = {
    "R": "microHeight",
    "G": "roughness",
    "B": "flakeDefectDensity",
    "A": "anisotropyDirection0To2Pi",
}
CONFIG: dict[str, dict[str, float]] = {
    "clear-coat": {"low": 0.08, "fine": 0.92, "rough_min": 18, "rough_max": 76, "density": 0.018, "angle": 0.08},
    "pearl": {"low": 0.72, "fine": 0.28, "rough_min": 72, "rough_max": 168, "density": 0.16, "angle": 0.31},
    "brushed-metal": {"low": 0.18, "fine": 0.82, "rough_min": 48, "rough_max": 138, "density": 0.055, "angle": 0.04},
    "spectral-lines": {"low": 0.10, "fine": 0.90, "rough_min": 34, "rough_max": 118, "density": 0.075, "angle": 0.17},
    "etched-holo": {"low": 0.24, "fine": 0.76, "rough_min": 54, "rough_max": 148, "density": 0.095, "angle": 0.27},
    "cosmic-flake": {"low": 0.36, "fine": 0.64, "rough_min": 42, "rough_max": 186, "density": 0.045, "angle": 0.43},
    "star-holo": {"low": 0.22, "fine": 0.78, "rough_min": 62, "rough_max": 174, "density": 0.07, "angle": 0.19},
}

STAR_MAIN_COUNT = 15
STAR_MICRO_COUNT = 40
STAR_SEED = 0x57A4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pixel_sha256(image: Image.Image) -> str:
    return hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()


def normalize_l(image: Image.Image, cutoff: float = 1.0) -> Image.Image:
    return ImageOps.autocontrast(image.convert("L"), cutoff=cutoff)


def scale_range(image: Image.Image, low: int, high: int) -> Image.Image:
    normalized = normalize_l(image)
    span = max(1, high - low)
    return normalized.point(lambda value: low + round(value / 255 * span))


def make_seamless(image: Image.Image, band: int = 48) -> Image.Image:
    """Move source-edge discontinuities inward and repair only that central cross.

    The half-period wrapped copy is naturally continuous at the output boundary,
    while the original is naturally continuous at the centre. A compact cosine
    mask selects each image only in its continuous region, preserving most of the
    source plate without introducing a visible half-period duplicate.
    """
    source = image.copy()
    width, height = source.size
    wrapped = ImageChops.offset(source, width // 2, height // 2)
    centre_x = (width - 1) * 0.5
    centre_y = (height - 1) * 0.5
    radius = max(4, min(band, width // 4, height // 4))

    def cosine_weight(distance: float) -> float:
        if distance >= radius:
            return 0.0
        return 0.5 + 0.5 * math.cos(math.pi * distance / radius)

    mask_values = bytearray(width * height)
    for y in range(height):
        weight_y = cosine_weight(abs(y - centre_y))
        for x in range(width):
            weight_x = cosine_weight(abs(x - centre_x))
            cross_weight = 1.0 - (1.0 - weight_x) * (1.0 - weight_y)
            mask_values[y * width + x] = round(cross_weight * 255)
    seam_mask = Image.frombytes("L", (width, height), bytes(mask_values))
    result = Image.composite(source, wrapped, seam_mask)

    # Close the discrete endpoint with the mean of its two interior neighbours.
    # Both border samples become identical while continuing the local slope from
    # either side; this avoids a duplicated bright/dark endpoint in minified tiles.
    pixels = result.load()
    for y in range(height):
        endpoint = round((pixels[1, y] + pixels[width - 2, y]) * 0.5)
        pixels[0, y] = endpoint
        pixels[width - 1, y] = endpoint
    for x in range(width):
        endpoint = round((pixels[x, 1] + pixels[x, height - 2]) * 0.5)
        pixels[x, 0] = endpoint
        pixels[x, height - 1] = endpoint
    return result


def percentile_mask(image: Image.Image, fraction: float) -> Image.Image:
    source = normalize_l(image)
    histogram = source.histogram()
    wanted = max(1, round(source.width * source.height * fraction))
    accumulated = 0
    threshold = 255
    for value in range(255, -1, -1):
        accumulated += histogram[value]
        if accumulated >= wanted:
            threshold = value
            break
    softness = 20
    return source.point(lambda value: 0 if value < threshold - softness else min(255, round((value - threshold + softness) / softness * 255)))


def direction_channel(image: Image.Image, base_turn: float) -> Image.Image:
    source = image.convert("L")
    width, height = source.size
    values = list(source.get_flattened_data())
    output = bytearray(width * height)
    for y in range(height):
        row = y * width
        up = ((y - 1) % height) * width
        down = ((y + 1) % height) * width
        for x in range(width):
            gx = values[row + ((x + 1) % width)] - values[row + ((x - 1) % width)]
            gy = values[down + x] - values[up + x]
            magnitude = abs(gx) + abs(gy)
            if magnitude < 5:
                turn = (base_turn + (values[row + x] - 128) / 2048) % 1.0
            else:
                turn = ((math.atan2(gy, gx) + math.pi) / (2 * math.pi) + base_turn) % 1.0
            output[row + x] = round(turn * 255)
    return Image.frombytes("L", (width, height), bytes(output))


def source_plate(path: Path) -> Image.Image:
    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
    return ImageOps.fit(image, (SIZE, SIZE), method=Image.Resampling.LANCZOS)


def connected_components(mask: Image.Image) -> list[dict[str, Any]]:
    """Return 8-connected components, joining pixels across tile boundaries."""
    source = mask.convert("L")
    pixels = list(source.get_flattened_data())
    seen = bytearray(SIZE * SIZE)
    components: list[dict[str, Any]] = []
    for start, value in enumerate(pixels):
        if value == 0 or seen[start]:
            continue
        stack = [start]
        seen[start] = 1
        indices: list[int] = []
        while stack:
            index = stack.pop()
            indices.append(index)
            x, y = index % SIZE, index // SIZE
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    neighbour = ((y + dy) % SIZE) * SIZE + ((x + dx) % SIZE)
                    if pixels[neighbour] and not seen[neighbour]:
                        seen[neighbour] = 1
                        stack.append(neighbour)
        xs = [index % SIZE for index in indices]
        ys = [index // SIZE for index in indices]
        components.append({
            "indices": indices,
            "area": len(indices),
            "width": max(xs) - min(xs) + 1,
            "height": max(ys) - min(ys) + 1,
            "centre": (sum(xs) / len(xs), sum(ys) / len(ys)),
        })
    return components


def toroidal_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = min(abs(a[0] - b[0]), SIZE - abs(a[0] - b[0]))
    dy = min(abs(a[1] - b[1]), SIZE - abs(a[1] - b[1]))
    return math.hypot(dx, dy)


def select_spaced(components: list[dict[str, Any]], count: int, minimum_distance: float) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for component in components:
        if all(toroidal_distance(component["centre"], item["centre"]) >= minimum_distance for item in selected):
            selected.append(component)
            if len(selected) == count:
                return selected
    return selected


def build_star_holo(source_path: Path) -> tuple[Image.Image, dict[str, int]]:
    """Extract stable star bodies from the generated relief plate and encode semantic RGBA."""
    luminance = make_seamless(normalize_l(source_plate(source_path), 0.5))
    local = luminance.filter(ImageFilter.GaussianBlur(5.5))
    relief = normalize_l(ImageChops.difference(luminance, local), 0.5)
    # A high threshold isolates embossed strokes. Small dilation reconnects the
    # points of each motif without turning quiet paper grain into star bodies.
    binary = relief.point(lambda value: 255 if value >= 184 else 0).filter(ImageFilter.MaxFilter(3))
    components = connected_components(binary)
    main_candidates = sorted(
        (item for item in components if item["area"] >= 42 and max(item["width"], item["height"]) >= 10),
        key=lambda item: (-item["area"], item["centre"]),
    )
    main = select_spaced(main_candidates, STAR_MAIN_COUNT, 22)
    if len(main) != STAR_MAIN_COUNT:
        raise SystemExit(f"star-holo source yielded {len(main)} main stars; expected {STAR_MAIN_COUNT}.")

    micro_candidates = sorted(
        (item for item in components if 5 <= item["area"] < 42 and 2 <= max(item["width"], item["height"]) <= 14),
        key=lambda item: (-item["area"], item["centre"]),
    )
    occupied = main.copy()
    micro: list[dict[str, Any]] = []
    for item in micro_candidates:
        if all(toroidal_distance(item["centre"], other["centre"]) >= (13 if other in main else 7) for other in occupied):
            micro.append(item)
            occupied.append(item)
            if len(micro) == STAR_MICRO_COUNT:
                break
    if len(micro) != STAR_MICRO_COUNT:
        raise SystemExit(f"star-holo source yielded {len(micro)} micro stars; expected {STAR_MICRO_COUNT}.")

    star_mask = Image.new("L", (SIZE, SIZE), 0)
    mask_pixels = star_mask.load()
    component_map: list[tuple[dict[str, Any], int]] = []
    for component in main:
        component_map.append((component, 255))
    for component in micro:
        component_map.append((component, 218))
    for component, value in component_map:
        for index in component["indices"]:
            mask_pixels[index % SIZE, index // SIZE] = value
    star_mask = make_seamless(star_mask.filter(ImageFilter.MaxFilter(3)), 24)
    soft_mask = star_mask.filter(ImageFilter.GaussianBlur(1.15))

    source_detail = scale_range(relief, 76, 224)
    height = make_seamless(Image.composite(source_detail, Image.new("L", (SIZE, SIZE), 88), soft_mask), 24)
    roughness = make_seamless(Image.composite(Image.new("L", (SIZE, SIZE), 62), Image.new("L", (SIZE, SIZE), 148), soft_mask), 24)
    density = make_seamless(star_mask, 24)

    rng = random.Random(STAR_SEED)
    direction = Image.new("L", (SIZE, SIZE), round(CONFIG["star-holo"]["angle"] * 255))
    direction_pixels = direction.load()
    for component, _ in component_map:
        angle = rng.randrange(256)
        for index in component["indices"]:
            direction_pixels[index % SIZE, index // SIZE] = angle
    direction = make_seamless(direction.filter(ImageFilter.MaxFilter(3)), 24)
    atlas = Image.merge("RGBA", (height, roughness, density, direction))
    metadata = {"mainStarCount": len(main), "microStarCount": len(micro)}
    coverage = density_coverage(atlas)
    if not 0.025 <= coverage <= 0.12:
        raise SystemExit(f"star-holo density coverage {coverage:.6f} is outside 0.025..0.12.")
    return atlas, metadata


def build_material(name: str, source_path: Path) -> Image.Image:
    if name == "star-holo":
        return build_star_holo(source_path)[0]
    config = CONFIG[name]
    rgb = source_plate(source_path)
    luminance = make_seamless(normalize_l(rgb, 0.5))
    low = normalize_l(luminance.filter(ImageFilter.GaussianBlur(10)))
    medium = normalize_l(ImageChops.difference(luminance, luminance.filter(ImageFilter.GaussianBlur(3))), 0.5)
    fine = normalize_l(ImageChops.difference(luminance, luminance.filter(ImageFilter.GaussianBlur(1.05))), 0.5)
    edges = normalize_l(luminance.filter(ImageFilter.FIND_EDGES), 0.5)

    height = Image.blend(low, Image.blend(medium, fine, 0.62), config["fine"])
    if name == "pearl":
        height = Image.blend(low, medium, 0.32)
    elif name == "brushed-metal":
        height = Image.blend(fine, edges, 0.24)
    elif name in {"spectral-lines", "etched-holo"}:
        height = Image.blend(medium, edges, 0.46)
    elif name == "cosmic-flake":
        height = Image.blend(low, Image.blend(fine, edges, 0.52), 0.72)
    height = make_seamless(normalize_l(height))

    rough_source = Image.blend(ImageOps.invert(medium), edges, 0.38)
    roughness = make_seamless(scale_range(rough_source, round(config["rough_min"]), round(config["rough_max"])))

    density_source = Image.blend(edges, Image.blend(medium, fine, 0.45), 0.54)
    if name == "pearl":
        density_source = Image.blend(low, edges, 0.22)
    elif name == "cosmic-flake":
        density_source = Image.blend(luminance, edges, 0.58)
    density = make_seamless(percentile_mask(density_source, config["density"]))

    direction_source = luminance.filter(ImageFilter.GaussianBlur(2.4 if name == "pearl" else 0.7))
    direction = make_seamless(direction_channel(direction_source, config["angle"]))
    return Image.merge("RGBA", (height, roughness, density, direction))


def seeded_noise(seed: int) -> Image.Image:
    rng = random.Random(seed)
    return Image.frombytes("L", (SIZE, SIZE), bytes(rng.randrange(256) for _ in range(SIZE * SIZE)))


def build_blue_noise() -> Image.Image:
    white = seeded_noise(0xB10E)
    low = white.filter(ImageFilter.GaussianBlur(2.25))
    high = ImageChops.subtract(white, low, scale=1.0, offset=128)
    blue = make_seamless(normalize_l(high, 0.75), 32)
    opaque = Image.new("L", (SIZE, SIZE), 255)
    return Image.merge("RGBA", (blue, blue, blue, opaque))


def build_micro_grain() -> Image.Image:
    fine = seeded_noise(0x6A41)
    broad = seeded_noise(0xC0A7).filter(ImageFilter.GaussianBlur(1.8))
    grain = Image.blend(fine, broad, 0.28)
    high = ImageChops.difference(grain, grain.filter(ImageFilter.GaussianBlur(0.85)))
    grain = make_seamless(scale_range(high, 28, 226), 36)
    opaque = Image.new("L", (SIZE, SIZE), 255)
    return Image.merge("RGBA", (grain, grain, grain, opaque))


def channel_stats(image: Image.Image) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for label, channel in zip("RGBA", image.convert("RGBA").split()):
        histogram = channel.histogram()
        total = channel.width * channel.height
        mean = sum(index * count for index, count in enumerate(histogram)) / total
        variance = sum(((index - mean) ** 2) * count for index, count in enumerate(histogram)) / total
        stats[label] = {
            "min": next(index for index, count in enumerate(histogram) if count),
            "max": next(index for index in range(255, -1, -1) if histogram[index]),
            "mean": round(mean, 4),
            "stddev": round(math.sqrt(variance), 4),
        }
    return stats


def edge_mae(image: Image.Image) -> dict[str, float]:
    result: dict[str, float] = {}
    for label, channel in zip("RGBA", image.convert("RGBA").split()):
        pixels = channel.load()
        vertical = sum(abs(pixels[0, y] - pixels[channel.width - 1, y]) for y in range(channel.height)) / (channel.height * 255)
        horizontal = sum(abs(pixels[x, 0] - pixels[x, channel.height - 1]) for x in range(channel.width)) / (channel.width * 255)
        result[label] = round(max(vertical, horizontal), 6)
    return result


def density_coverage(image: Image.Image) -> float:
    blue = image.convert("RGBA").getchannel("B")
    return round(sum(1 for value in blue.get_flattened_data() if value > 160) / (blue.width * blue.height), 6)


def direction_preview(direction: Image.Image) -> Image.Image:
    pixels = []
    for value in direction.get_flattened_data():
        red, green, blue = colorsys.hsv_to_rgb(value / 255, 0.82, 0.92)
        pixels.append((round(red * 255), round(green * 255), round(blue * 255)))
    result = Image.new("RGB", direction.size)
    result.putdata(pixels)
    return result


def material_preview(atlas: Image.Image) -> Image.Image:
    height, roughness, density, direction = atlas.convert("RGBA").split()
    hue = direction_preview(direction)
    brightness = Image.blend(height, ImageOps.invert(roughness), 0.42)
    tinted = ImageChops.multiply(hue, brightness.convert("RGB"))
    sparkle = ImageOps.colorize(density, black=(0, 0, 0), white=(255, 244, 205))
    return Image.blend(tinted, ImageChops.screen(tinted, sparkle), 0.56)


def contact_sheet(material_images: dict[str, Image.Image], shared: dict[str, Image.Image], output: Path) -> None:
    thumb = 128
    label_width = 152
    header = 60
    row_height = thumb + 28
    columns = ("Preview", "R Height", "G Roughness", "B Density", "A Direction")
    width = label_width + len(columns) * (thumb + 12)
    height = header + (len(MATERIALS) + 1) * row_height
    sheet = Image.new("RGB", (width, height), (24, 27, 31))
    draw = ImageDraw.Draw(sheet)
    draw.text((10, 10), "Original Holographic Material Atlases", fill=(238, 240, 244))
    for index, title in enumerate(columns):
        draw.text((label_width + index * (thumb + 12), 36), title, fill=(180, 188, 198))
    for row, name in enumerate(MATERIALS):
        y = header + row * row_height
        atlas = material_images[name].convert("RGBA")
        channels = atlas.split()
        previews = [material_preview(atlas), channels[0].convert("RGB"), channels[1].convert("RGB"), channels[2].convert("RGB"), direction_preview(channels[3])]
        draw.text((10, y + 54), name, fill=(228, 230, 234))
        for column, preview in enumerate(previews):
            tile = preview.resize((thumb, thumb), Image.Resampling.LANCZOS)
            sheet.paste(tile, (label_width + column * (thumb + 12), y))
    y = header + len(MATERIALS) * row_height
    draw.text((10, y + 54), "shared", fill=(228, 230, 234))
    for column, name in enumerate(("blue-noise", "micro-grain")):
        tile = shared[name].convert("RGB").resize((thumb, thumb), Image.Resampling.LANCZOS)
        sheet.paste(tile, (label_width + column * (thumb + 12), y))
        draw.text((label_width + column * (thumb + 12), y + thumb + 4), name, fill=(180, 188, 198))
    sheet.save(output, "PNG", optimize=True)


def resolve_source(sources: Path, name: str) -> Path:
    candidates = [path for path in sources.glob(f"{name}.*") if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    if len(candidates) != 1:
        raise SystemExit(f"Expected exactly one source plate for {name}, found {len(candidates)} in {sources}.")
    return candidates[0]


def load_prompts(sources: Path) -> dict[str, str]:
    path = sources / "prompts.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Missing or invalid source prompt manifest: {path}: {error}") from error
    if set(payload) != set(MATERIALS) or not all(isinstance(payload[name], str) and payload[name].strip() for name in MATERIALS):
        raise SystemExit("prompts.json must contain one non-empty prompt for every material.")
    return payload


def build(output: Path) -> dict[str, Any]:
    sources = output / "sources"
    prompts = load_prompts(sources)
    output.mkdir(parents=True, exist_ok=True)
    material_images: dict[str, Image.Image] = {}
    manifest_assets: dict[str, Any] = {}
    for name in MATERIALS:
        source = resolve_source(sources, name)
        star_metadata: dict[str, int] = {}
        if name == "star-holo":
            atlas, star_metadata = build_star_holo(source)
        else:
            atlas = build_material(name, source)
        path = output / f"{name}.webp"
        atlas.save(path, "WEBP", lossless=True, quality=100, method=6, exact=True)
        decoded = Image.open(path).convert("RGBA")
        if decoded.tobytes() != atlas.tobytes():
            raise SystemExit(f"Lossless WebP round-trip failed for {name}.")
        material_images[name] = decoded
        manifest_assets[name] = {
            "runtime": path.name,
            "source": f"sources/{source.name}",
            "prompt": prompts[name],
            "width": SIZE,
            "height": SIZE,
            "mode": "RGBA",
            "encoding": "lossless-webp",
            "sha256": sha256_file(path),
            "pixelSha256": pixel_sha256(decoded),
            "sourceSha256": sha256_file(source),
            "edgeMae": edge_mae(decoded),
            "channelStats": channel_stats(decoded),
            "densityCoverage": density_coverage(decoded),
            **star_metadata,
        }

    shared = {"blue-noise": build_blue_noise(), "micro-grain": build_micro_grain()}
    manifest_shared: dict[str, Any] = {}
    for name, image in shared.items():
        path = output / f"{name}.webp"
        image.save(path, "WEBP", lossless=True, quality=100, method=6, exact=True)
        decoded = Image.open(path).convert("RGBA")
        if decoded.tobytes() != image.tobytes():
            raise SystemExit(f"Lossless WebP round-trip failed for {name}.")
        shared[name] = decoded
        manifest_shared[name] = {
            "runtime": path.name,
            "width": SIZE,
            "height": SIZE,
            "mode": "RGBA",
            "encoding": "lossless-webp",
            "sha256": sha256_file(path),
            "pixelSha256": pixel_sha256(decoded),
            "edgeMae": edge_mae(decoded),
            "channelStats": channel_stats(decoded),
            "origin": "Deterministic local synthesis; no image model or external texture.",
        }

    sheet_path = output / "contact-sheet.png"
    contact_sheet(material_images, shared, sheet_path)
    manifest = {
        "schemaVersion": 1,
        "version": "1.1.0",
        "assetPack": "original-holographic-material-atlases-v1.1",
        "size": [SIZE, SIZE],
        "channelContract": CHANNELS,
        "sourceGeneration": {
            "tool": "OpenAI built-in image generation",
            "usage": "One original source plate per material; locally transformed into semantic channels.",
            "thirdPartyCodeOrAssets": False,
            "externalUrls": [],
        },
        "assets": manifest_assets,
        "shared": manifest_shared,
        "contactSheet": {"path": sheet_path.name, "sha256": sha256_file(sheet_path)},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "assets" / "react-template" / "holo-textures")
    arguments = parser.parse_args()
    manifest = build(arguments.output.resolve())
    print(json.dumps({"output": str(arguments.output.resolve()), "assets": len(manifest["assets"]), "shared": len(manifest["shared"]), "contactSheet": manifest["contactSheet"]["path"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
