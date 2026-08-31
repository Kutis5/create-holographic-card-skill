const IDLE_REVEAL = 0.7;

const INTENSITY_GAIN = Object.freeze({
  foil: 4.8,
  texture: 3.2,
  sparkle: 5.5,
  glare: 4,
});

function clamp(value, min = 0, max = 1) {
  return Math.min(max, Math.max(min, Number.isFinite(value) ? value : min));
}

function parseHex(value) {
  const match = /^#?([\da-f]{6})$/i.exec(String(value || "").trim());
  if (!match) return null;
  const integer = Number.parseInt(match[1], 16);
  return [(integer >> 16) & 255, (integer >> 8) & 255, integer & 255];
}

function toHex(rgb) {
  return `#${rgb.map((channel) => Math.round(clamp(channel, 0, 255)).toString(16).padStart(2, "0")).join("")}`;
}

function rgbToHsl([red, green, blue]) {
  const r = red / 255;
  const g = green / 255;
  const b = blue / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  let hue = 0;
  if (delta) {
    if (max === r) hue = ((g - b) / delta) % 6;
    else if (max === g) hue = (b - r) / delta + 2;
    else hue = (r - g) / delta + 4;
    hue = (hue * 60 + 360) % 360;
  }
  const lightness = (max + min) / 2;
  const saturation = delta ? delta / (1 - Math.abs(2 * lightness - 1)) : 0;
  return [hue, saturation, lightness];
}

function hslToRgb([hue, saturation, lightness]) {
  const h = ((hue % 360) + 360) % 360;
  const s = clamp(saturation);
  const l = clamp(lightness);
  const chroma = (1 - Math.abs(2 * l - 1)) * s;
  const x = chroma * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - chroma / 2;
  let rgb;
  if (h < 60) rgb = [chroma, x, 0];
  else if (h < 120) rgb = [x, chroma, 0];
  else if (h < 180) rgb = [0, chroma, x];
  else if (h < 240) rgb = [0, x, chroma];
  else if (h < 300) rgb = [x, 0, chroma];
  else rgb = [chroma, 0, x];
  return rgb.map((channel) => (channel + m) * 255);
}

function mixRgb(a, b, amount) {
  const t = clamp(amount);
  return a.map((channel, index) => channel + (b[index] - channel) * t);
}

function expandNeutralFoilColors(source) {
  const lightnessOffsets = [-0.05, 0.035, -0.02, 0.05, -0.035, 0.025];
  return lightnessOffsets.map((offset, index) => {
    const position = source.length === 1 ? 0 : (index / 5) * (source.length - 1);
    const left = Math.floor(position);
    const right = Math.min(source.length - 1, left + 1);
    const [hue, saturation, lightness] = rgbToHsl(mixRgb(source[left], source[right], position - left));
    return toHex(hslToRgb([hue, Math.min(saturation, 0.2), clamp(lightness + offset, 0.36, 0.82)]));
  });
}

export function perceptualIntensity(value, kind = "foil") {
  const gain = INTENSITY_GAIN[kind] || INTENSITY_GAIN.foil;
  return clamp(1 - Math.exp(-gain * clamp(Number(value) || 0)));
}

export function expandFoilColors(colors, accent = "#78d7ff") {
  const parsed = (Array.isArray(colors) ? colors : []).map(parseHex).filter(Boolean);
  const fallback = parseHex(accent) || [120, 215, 255];
  const source = parsed.length ? parsed : [fallback];
  if (source.length >= 6) return source.slice(0, 6).map(toHex);

  if (source.every((color) => rgbToHsl(color)[1] <= 0.2)) {
    return expandNeutralFoilColors(source);
  }

  const [baseHue, baseSaturation, baseLightness] = rgbToHsl(source[0]);
  const spectrumOffsets = [0, 54, 112, 176, 238, 304];
  const result = [];
  for (let index = 0; index < 6; index += 1) {
    const position = source.length === 1 ? 0 : (index / 5) * (source.length - 1);
    const left = Math.floor(position);
    const right = Math.min(source.length - 1, left + 1);
    const interpolated = mixRgb(source[left], source[right], position - left);
    const spectrum = hslToRgb([
      baseHue + spectrumOffsets[index],
      clamp(Math.max(baseSaturation, 0.62), 0.56, 0.9),
      clamp(baseLightness, 0.46, 0.66),
    ]);
    const spectrumWeight = source.length === 1 ? 0.64 : 0.34;
    result.push(toHex(mixRgb(interpolated, spectrum, spectrumWeight)));
  }
  return result;
}

export function idlePoint(elapsedMs) {
  const phase = (Math.max(0, Number(elapsedMs) || 0) / 11000) * Math.PI * 2;
  return {
    x: clamp(Math.sin(phase) * 0.62 + Math.sin(phase * 0.37 + 0.9) * 0.11, -1, 1),
    y: clamp(Math.cos(phase * 0.83 + 0.4) * 0.52 + Math.sin(phase * 0.29) * 0.08, -1, 1),
  };
}

export function interactionReveal(x, y) {
  const distance = clamp(Math.hypot(Number(x) || 0, Number(y) || 0) / Math.SQRT2);
  return IDLE_REVEAL + distance * (1 - IDLE_REVEAL);
}

export function computeOpticalState(presentation, x, y, recipe = {}) {
  const px = clamp(Number(x) || 0, -1, 1);
  const py = clamp(Number(y) || 0, -1, 1);
  const motion = presentation?.motion || {};
  const foil = presentation?.foil || {};
  const texture = presentation?.texture || {};
  const sparkle = presentation?.sparkle || {};
  const glare = presentation?.glare || {};
  const maxX = Math.max(11, Math.min(14, Number(motion.maxX) || 14));
  const maxY = Math.max(11, Math.min(14, Number(motion.maxY) || 14));
  const reveal = interactionReveal(px, py);
  const foilStrength = foil.enabled === false ? 0 : perceptualIntensity(foil.intensity, "foil");
  const textureStrength = texture.enabled === false ? 0 : perceptualIntensity(texture.intensity, "texture");
  const sparkleStrength = sparkle.enabled === false ? 0 : perceptualIntensity(sparkle.intensity, "sparkle");
  const glareStrength = glare.enabled === false ? 0 : perceptualIntensity(glare.intensity, "glare");
  const pointerX = (px + 1) * 50;
  const pointerY = (py + 1) * 50;

  return {
    x: px,
    y: py,
    pointerX,
    pointerY,
    reveal,
    rotateX: -py * maxX,
    rotateY: px * maxY,
    scale: Math.max(1.018, Number(motion.scale) || 1.018),
    subjectX: px * (Number(recipe.subjectParallax) || 5.5),
    subjectY: py * (Number(recipe.subjectParallax) || 5.5),
    foilX: 50 + px * 27,
    foilY: 50 + py * 23,
    stripeX: 50 - px * 18,
    stripeY: 50 - py * 31,
    glareX: 50 + px * 42,
    glareY: 50 + py * 42,
    foilOpacity: foilStrength * reveal,
    textureOpacity: textureStrength * reveal,
    sparkleOpacity: sparkleStrength * reveal,
    glareOpacity: glareStrength * reveal,
    rimOpacity: clamp(foilStrength * 0.58 + glareStrength * 0.28 + textureStrength * 0.14),
    shadowX: -px * 21,
    shadowY: 18 + py * 18,
    shadowBlur: 30 + reveal * 24,
    darkSideX: 50 - px * 40,
    darkSideY: 50 - py * 40,
  };
}

export { IDLE_REVEAL };
