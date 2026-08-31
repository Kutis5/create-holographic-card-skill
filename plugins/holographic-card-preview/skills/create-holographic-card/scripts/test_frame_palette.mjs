import assert from "node:assert/strict";
import { analyzeFramePixels, paletteFromColor } from "../assets/react-template/frame-palette.js";

function pixels(width, height, edge, center, edgeAlpha = 255) {
  const data = new Uint8ClampedArray(width * height * 4);
  const band = Math.max(1, Math.ceil(Math.min(width, height) * 0.2));
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const isEdge = x < band || x >= width - band || y < band || y >= height - band;
      const color = isEdge ? edge : center;
      const offset = (y * width + x) * 4;
      data.set([...color, isEdge ? edgeAlpha : 255], offset);
    }
  }
  return data;
}

function rgb(hex) {
  return [1, 3, 5].map(offset => Number.parseInt(hex.slice(offset, offset + 2), 16));
}

const redEdge = analyzeFramePixels(pixels(20, 20, [210, 40, 55], [20, 40, 220]), 20, 20, "#75808f");
const changedCenter = analyzeFramePixels(pixels(20, 20, [210, 40, 55], [20, 220, 40]), 20, 20, "#75808f");
assert.deepEqual(redEdge, changedCenter, "center pixels must not influence the edge palette");
const [red, , blue] = rgb(redEdge.base);
assert.ok(red > blue * 2, `expected a red edge palette, received ${redEdge.base}`);
assert.notEqual(redEdge.base, redEdge.highlight);
assert.notEqual(redEdge.base, redEdge.shadow);

const neutral = analyzeFramePixels(pixels(20, 20, [128, 128, 128], [250, 20, 20]), 20, 20);
const neutralRgb = rgb(neutral.base);
assert.equal(Math.max(...neutralRgb) - Math.min(...neutralRgb), 0, "neutral edges must remain achromatic");

const fallback = paletteFromColor("#315b86");
assert.deepEqual(analyzeFramePixels(pixels(20, 20, [20, 200, 50], [0, 0, 0], 0), 20, 20, "#315b86"), fallback);
assert.deepEqual(analyzeFramePixels([], 0, 0, "#315b86"), fallback);
assert.equal(fallback.base, "#315b86", "fixed palettes must preserve the explicit base color");

console.log("frame palette tests passed");
