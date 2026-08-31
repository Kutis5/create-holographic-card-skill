const SAMPLE_SIZE = 48;
const EDGE_FRACTION = 0.2;
const MIN_ALPHA = 230;
const DEFAULT_COLOR = "#75808f";

const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));

function parseHex(value) {
  const match = /^#([0-9a-f]{6})$/i.exec(typeof value === "string" ? value : "");
  const hex = match ? match[1] : DEFAULT_COLOR.slice(1);
  return [0, 2, 4].map(offset => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255);
}

function channelHex(value) {
  return Math.round(clamp(value, 0, 1) * 255).toString(16).padStart(2, "0");
}

function rgbHex(rgb) {
  return `#${rgb.map(channelHex).join("")}`;
}

function srgbToLinear(value) {
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function linearToSrgb(value) {
  return value <= 0.0031308 ? value * 12.92 : 1.055 * value ** (1 / 2.4) - 0.055;
}

function rgbToHsl([red, green, blue]) {
  const maximum = Math.max(red, green, blue);
  const minimum = Math.min(red, green, blue);
  const lightness = (maximum + minimum) / 2;
  const delta = maximum - minimum;
  if (delta === 0) return [0, 0, lightness];
  const saturation = delta / (1 - Math.abs(2 * lightness - 1));
  let hue;
  if (maximum === red) hue = ((green - blue) / delta) % 6;
  else if (maximum === green) hue = (blue - red) / delta + 2;
  else hue = (red - green) / delta + 4;
  return [((hue * 60) + 360) % 360, saturation, lightness];
}

function hslToRgb([hue, saturation, lightness]) {
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
  const section = hue / 60;
  const intermediate = chroma * (1 - Math.abs((section % 2) - 1));
  let channels;
  if (section < 1) channels = [chroma, intermediate, 0];
  else if (section < 2) channels = [intermediate, chroma, 0];
  else if (section < 3) channels = [0, chroma, intermediate];
  else if (section < 4) channels = [0, intermediate, chroma];
  else if (section < 5) channels = [intermediate, 0, chroma];
  else channels = [chroma, 0, intermediate];
  const match = lightness - chroma / 2;
  return channels.map(value => value + match);
}

function relatedPalette(rgb, preserveBase = false) {
  const [hue, rawSaturation, rawLightness] = rgbToHsl(rgb);
  const saturation = rawSaturation < 0.08 ? 0 : clamp(rawSaturation, 0.28, 0.68);
  const lightness = clamp(rawLightness, 0.28, 0.52);
  const base = preserveBase ? rgbHex(rgb) : rgbHex(hslToRgb([hue, saturation, lightness]));
  const highlight = rgbHex(hslToRgb([hue, saturation * 0.85, clamp(lightness + 0.18, 0, 1)]));
  const shadow = rgbHex(hslToRgb([hue, saturation * 0.95, clamp(lightness - 0.16, 0, 1)]));
  return Object.freeze({ base, highlight, shadow });
}

export function paletteFromColor(color) {
  return relatedPalette(parseHex(color), true);
}

export function analyzeFramePixels(data, width, height, fallbackColor = DEFAULT_COLOR) {
  const fallback = paletteFromColor(fallbackColor);
  if (!data || !Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || data.length < width * height * 4) return fallback;
  const band = Math.max(1, Math.ceil(Math.min(width, height) * EDGE_FRACTION));
  const minimumSamples = Math.max(4, Math.ceil((width + height) * 0.1));
  const total = [0, 0, 0];
  let totalWeight = 0;
  let samples = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (x >= band && x < width - band && y >= band && y < height - band) continue;
      const offset = (y * width + x) * 4;
      if (data[offset + 3] < MIN_ALPHA) continue;
      const rgb = [data[offset], data[offset + 1], data[offset + 2]].map(value => value / 255);
      const saturation = rgbToHsl(rgb)[1];
      const weight = 0.35 + saturation * 0.65;
      for (let channel = 0; channel < 3; channel += 1) total[channel] += srgbToLinear(rgb[channel]) * weight;
      totalWeight += weight;
      samples += 1;
    }
  }
  if (samples < minimumSamples || totalWeight <= 0) return fallback;
  const average = total.map(value => clamp(linearToSrgb(value / totalWeight), 0, 1));
  return relatedPalette(average);
}

export function extractFramePalette(image, fallbackColor = DEFAULT_COLOR) {
  const fallback = paletteFromColor(fallbackColor);
  try {
    if (!image || typeof document === "undefined" || !(image.naturalWidth > 0) || !(image.naturalHeight > 0)) return fallback;
    const canvas = document.createElement("canvas");
    canvas.width = SAMPLE_SIZE;
    canvas.height = SAMPLE_SIZE;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) return fallback;
    context.drawImage(image, 0, 0, SAMPLE_SIZE, SAMPLE_SIZE);
    const pixels = context.getImageData(0, 0, SAMPLE_SIZE, SAMPLE_SIZE);
    return analyzeFramePixels(pixels.data, SAMPLE_SIZE, SAMPLE_SIZE, fallbackColor);
  } catch {
    return fallback;
  }
}
