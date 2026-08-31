import { IDLE_REVEAL, expandFoilColors, idlePoint, interactionReveal, perceptualIntensity } from "./optical-state.js";
export { interactionReveal } from "./optical-state.js";

export const MATERIAL_FAMILIES = Object.freeze([
  "clear-coat", "pearl", "brushed-metal", "spectral-lines", "etched-holo", "cosmic-flake", "star-holo",
]);
export const TEXTURE_KINDS = Object.freeze([
  "none", "micro-grain", "scanline", "geometric", "contour", "sparse-flake",
]);
export const NEUTRAL_REVEAL = IDLE_REVEAL;
export const MAX_DEVICE_PIXEL_RATIO = 2;
// Mobile uses the same optical shader and nearly the same sampling density as
// desktop. The budget is only a guardrail for unusually large WebView sizes;
// normal 5:7 phone cards stay below it at DPR 2.
export const MOBILE_MAX_DEVICE_PIXEL_RATIO = 2;
export const MOBILE_MAX_CANVAS_PIXELS = 1600000;
export const IDLE_FRAME_INTERVAL_MS = 1000 / 12;
export const ACTIVE_FRAME_INTERVAL_MS = 1000 / 60;
export const MATERIAL_PROFILES = Object.freeze({
  "clear-coat": Object.freeze({ family: "clear-coat", rimFactor: 0.62, backgroundGlareFactor: 0.52, surfaceGlareFactor: 0.38 }),
  pearl: Object.freeze({ family: "pearl", rimFactor: 0.76, backgroundGlareFactor: 0.44, surfaceGlareFactor: 0.25 }),
  "brushed-metal": Object.freeze({ family: "brushed-metal", rimFactor: 0.52, backgroundGlareFactor: 0.38, surfaceGlareFactor: 0.18 }),
  "spectral-lines": Object.freeze({ family: "spectral-lines", rimFactor: 0.66, backgroundGlareFactor: 0.34, surfaceGlareFactor: 0.16 }),
  "etched-holo": Object.freeze({ family: "etched-holo", rimFactor: 0.56, backgroundGlareFactor: 0.30, surfaceGlareFactor: 0.14 }),
  "cosmic-flake": Object.freeze({ family: "cosmic-flake", rimFactor: 0.72, backgroundGlareFactor: 0.36, surfaceGlareFactor: 0.18 }),
  "star-holo": Object.freeze({ family: "star-holo", rimFactor: 0.68, backgroundGlareFactor: 0.40, surfaceGlareFactor: 0.20 }),
});

const MATERIAL_SET = new Set(MATERIAL_FAMILIES);
const TEXTURE_INDEX = Object.freeze(Object.fromEntries(TEXTURE_KINDS.map((kind, index) => [kind, index])));
const MATERIAL_TEXTURE_URLS = Object.freeze({
  "clear-coat": new URL("./holo-textures/clear-coat.webp", import.meta.url).href,
  pearl: new URL("./holo-textures/pearl.webp", import.meta.url).href,
  "brushed-metal": new URL("./holo-textures/brushed-metal.webp", import.meta.url).href,
  "spectral-lines": new URL("./holo-textures/spectral-lines.webp", import.meta.url).href,
  "etched-holo": new URL("./holo-textures/etched-holo.webp", import.meta.url).href,
  "cosmic-flake": new URL("./holo-textures/cosmic-flake.webp", import.meta.url).href,
  "star-holo": new URL("./holo-textures/star-holo.webp", import.meta.url).href,
});
const BLUE_NOISE_URL = new URL("./holo-textures/blue-noise.webp", import.meta.url).href;
const MICRO_GRAIN_URL = new URL("./holo-textures/micro-grain.webp", import.meta.url).href;

const VERTEX_SHADER = `#version 300 es
in vec2 aPosition;
out vec2 vUv;
void main() {
  vUv = aPosition * 0.5 + 0.5;
  gl_Position = vec4(aPosition, 0.0, 1.0);
}`;

const FRAGMENT_HEADER = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;
uniform sampler2D uBackground;
uniform sampler2D uMaterialAtlas;
uniform sampler2D uBlueNoise;
uniform sampler2D uMicroGrain;
uniform vec2 uResolution;
uniform vec2 uTilt;
uniform vec3 uPalette0;
uniform vec3 uPalette1;
uniform vec3 uPalette2;
uniform vec3 uPalette3;
uniform vec3 uPalette4;
uniform vec3 uPalette5;
uniform vec3 uAccent;
uniform vec3 uFrameColor;
uniform vec3 uFrameHighlight;
uniform vec3 uFrameShadow;
uniform float uFrameInset;
uniform float uInnerRadius;
uniform float uAspect;
uniform float uReveal;
uniform float uTime;
uniform float uFoilIntensity;
uniform float uTextureIntensity;
uniform float uSparkleIntensity;
uniform float uGlareIntensity;
uniform int uTextureKind;

const float TAU = 6.28318530718;
float saturate1(float value) { return clamp(value, 0.0, 1.0); }
float luminance(vec3 color) { return dot(color, vec3(0.2126, 0.7152, 0.0722)); }
vec3 paletteRamp(float value) {
  float phase = fract(value);
  float segment = phase * 6.0;
  if (segment < 1.0) return mix(uPalette0, uPalette1, segment);
  if (segment < 2.0) return mix(uPalette1, uPalette2, segment - 1.0);
  if (segment < 3.0) return mix(uPalette2, uPalette3, segment - 2.0);
  if (segment < 4.0) return mix(uPalette3, uPalette4, segment - 3.0);
  if (segment < 5.0) return mix(uPalette4, uPalette5, segment - 4.0);
  return mix(uPalette5, uPalette0, segment - 5.0);
}
vec3 screenBlend(vec3 base, vec3 light) { return 1.0 - (1.0 - base) * (1.0 - light); }
vec3 hardLightBlend(vec3 base, vec3 light) {
  return mix(2.0 * base * light, 1.0 - 2.0 * (1.0 - base) * (1.0 - light), step(vec3(0.5), light));
}
vec3 dodgeBlend(vec3 base, vec3 light) { return min(vec3(1.0), base / max(vec3(0.13), 1.0 - light)); }
struct AtlasData {
  float height;
  float roughness;
  float density;
  float angle;
  vec2 tangent;
  vec3 normal;
};
AtlasData decodeAtlas(vec2 uv) {
  vec4 packed = texture(uMaterialAtlas, uv);
  vec2 texel = 1.0 / vec2(textureSize(uMaterialAtlas, 0));
  float dx = texture(uMaterialAtlas, uv + vec2(texel.x, 0.0)).r
           - texture(uMaterialAtlas, uv - vec2(texel.x, 0.0)).r;
  float dy = texture(uMaterialAtlas, uv + vec2(0.0, texel.y)).r
           - texture(uMaterialAtlas, uv - vec2(0.0, texel.y)).r;
  float angle = packed.a * TAU;
  AtlasData data;
  data.height = packed.r;
  data.roughness = packed.g;
  data.density = packed.b;
  data.angle = angle;
  data.tangent = vec2(cos(angle), sin(angle));
  data.normal = normalize(vec3(-dx * 2.8, -dy * 2.8, 1.0));
  return data;
}
float blueNoise(vec2 uv, vec2 offset) {
  return texture(uBlueNoise, uv * vec2(1.73, 1.31) + offset).r;
}
float auxiliaryTexture(vec2 uv, vec3 base, AtlasData atlas) {
  vec2 pixel = uv * uResolution;
  float dither = blueNoise(uv, vec2(0.17, 0.41));
  if (uTextureKind == 1) return texture(uMicroGrain, uv * 1.37).r * mix(0.72, 1.0, dither);
  if (uTextureKind == 2) {
    float drift = (dither - 0.5) * 0.7;
    return pow(saturate1(0.5 + 0.5 * cos(pixel.y * 1.74 + drift)), 10.0);
  }
  if (uTextureKind == 3) {
    vec2 oriented = vec2(dot(pixel / 29.0, atlas.tangent), dot(pixel / 29.0, vec2(-atlas.tangent.y, atlas.tangent.x)));
    vec2 cell = abs(fract(oriented + dither * 0.06) - 0.5);
    return smoothstep(0.43, 0.49, max(cell.x, cell.y)) * mix(0.55, 1.0, dither);
  }
  if (uTextureKind == 4) {
    float contour = abs(fract(luminance(base) * 9.0 + atlas.height * 3.0 + dither * 0.08) - 0.5);
    return smoothstep(0.43, 0.49, contour);
  }
  if (uTextureKind == 5) {
    float sparse = smoothstep(0.91, 0.98, dither);
    return sparse * smoothstep(0.36, 0.72, atlas.density);
  }
  return 0.0;
}
float pointerGlare(vec2 uv) {
  vec2 center = vec2(0.5 + uTilt.x * 0.42, 0.5 - uTilt.y * 0.42);
  vec2 delta = (uv - center) * vec2(uResolution.x / max(uResolution.y, 1.0), 1.0);
  return pow(saturate1(1.0 - length(delta) / 0.62), 2.4);
}
float sparkleField(vec2 uv, AtlasData atlas) {
  float noise = blueNoise(uv * 2.31, floor((uTilt + uTime * vec2(0.37, -0.21)) * 13.0) * 0.013);
  vec2 viewAxis = normalize(uTilt + vec2(0.001));
  float facing = pow(saturate1(abs(dot(atlas.tangent, viewAxis))), 7.0);
  return smoothstep(0.94, 0.995, noise) * smoothstep(0.28, 0.82, atlas.density) * facing;
}
float reflectionMask(vec2 uv, vec3 base, AtlasData atlas) {
  vec2 texel = 1.5 / max(uResolution, vec2(1.0));
  float lum = luminance(base);
  float edge = abs(luminance(texture(uBackground, clamp(uv + vec2(texel.x, 0.0), 0.0, 1.0)).rgb)
                 - luminance(texture(uBackground, clamp(uv - vec2(texel.x, 0.0), 0.0, 1.0)).rgb));
  edge += abs(luminance(texture(uBackground, clamp(uv + vec2(0.0, texel.y), 0.0, 1.0)).rgb)
            - luminance(texture(uBackground, clamp(uv - vec2(0.0, texel.y), 0.0, 1.0)).rgb));
  float saturation = max(max(base.r, base.g), base.b) - min(min(base.r, base.g), base.b);
  float brightSurface = smoothstep(0.22, 0.84, lum);
  float paleOrMetal = smoothstep(0.18, 0.82, lum) * (1.0 - saturation * 0.48);
  float linePreservation = 1.0 - smoothstep(0.02, 0.19, lum);
  float structural = smoothstep(0.025, 0.18, edge) * 0.42 + atlas.density * 0.21;
  return clamp((brightSurface * 0.48 + paleOrMetal * 0.46 + structural) * (1.0 - linePreservation * 0.86), 0.04, 1.0);
}
vec3 flagshipOptics(vec2 uv, vec3 base, AtlasData atlas, float mask) {
  vec2 centered = uv - 0.5;
  float bandA = dot(centered, normalize(vec2(0.91, 0.42))) * 2.65
              + uTilt.x * 0.57 - uTilt.y * 0.31 + uTime * 0.018 + atlas.height * 0.13;
  float bandB = dot(centered, normalize(vec2(-0.36, 0.93))) * 4.10
              - uTilt.x * 0.34 + uTilt.y * 0.66 - uTime * 0.027 - atlas.height * 0.09;
  float broadA = pow(0.5 + 0.5 * cos((bandA - 0.12) * TAU), 1.35);
  float broadB = pow(0.5 + 0.5 * cos((bandB + 0.27) * TAU), 2.15);
  vec3 spectrumA = paletteRamp(bandA * 0.46 + 0.12) * (0.34 + broadA * 0.66);
  vec3 spectrumB = paletteRamp(0.58 - bandB * 0.31) * (0.30 + broadB * 0.70);
  vec3 dodged = dodgeBlend(base, spectrumA * mask * uFoilIntensity * 0.72);
  vec3 crossed = hardLightBlend(dodged, spectrumB * mask * uFoilIntensity * 0.84 + vec3(0.08));
  return mix(base, crossed, clamp(mask * uFoilIntensity * 0.88, 0.0, 0.92));
}
float roundedRectMask(vec2 uv, float radius) {
  // Evaluate the SDF in physical card coordinates. The old square-space SDF
  // made the vertical corners collapse on a 5:7 canvas.
  vec2 p = (uv - 0.5) * vec2(uAspect, 1.0);
  vec2 halfSize = vec2(max(uAspect, 0.001) * 0.5, 0.5);
  float r = min(radius, min(halfSize.x, halfSize.y) - 0.001);
  vec2 q = abs(p) - (halfSize - vec2(r));
  float distance = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
  float aa = max(fwidth(distance), 0.001);
  return 1.0 - smoothstep(0.0, aa, distance);
}
float innerSurfaceMask(vec2 uv, float inset, float radius) {
  vec2 size = max(vec2(0.001), vec2(1.0 - inset * 2.0));
  vec2 innerUv = (uv - inset) / size;
  float inside = step(0.0, innerUv.x) * step(innerUv.x, 1.0) * step(0.0, innerUv.y) * step(innerUv.y, 1.0);
  return inside * roundedRectMask(innerUv, radius);
}
vec3 coatSweepOptics(vec2 uv, AtlasData atlas, float mask) {
  vec2 centered = uv - 0.5;
  float sweepA = dot(centered, normalize(vec2(0.86, 0.51))) * 2.15
               + uTilt.x * 0.68 - uTilt.y * 0.43 + uTime * 0.018;
  float sweepB = dot(centered, normalize(vec2(-0.52, 0.84))) * 3.45
               - uTilt.x * 0.31 + uTilt.y * 0.57 - uTime * 0.013;
  float broad = pow(saturate1(0.5 + 0.5 * cos(sweepA * TAU)), 2.0);
  float stripe = pow(saturate1(0.5 + 0.5 * cos(sweepB * TAU + atlas.height * 1.8)), 6.0);
  vec3 foil = paletteRamp(sweepA * 0.43 + atlas.angle / TAU) * broad * 0.78;
  vec3 bands = paletteRamp(0.68 - sweepB * 0.26) * stripe * 0.58;
  return dodgeBlend(vec3(0.18), (foil + bands) * mask * uFoilIntensity);
}
`;

const MATERIAL_BODIES = Object.freeze({
  "clear-coat": `
vec2 materialDistortion(vec2 uv, AtlasData atlas) {
  return atlas.normal.xy * (0.0008 + atlas.height * 0.0015) * (0.25 + length(uTilt));
}
vec3 materialEffect_clear_coat(vec2 uv, vec3 base, AtlasData atlas) {
  vec3 light = normalize(vec3(uTilt * vec2(0.72, -0.72), 0.62));
  float ndl = saturate1(dot(atlas.normal, light));
  float grazing = pow(saturate1(1.0 - atlas.normal.z * 0.58), 3.0);
  float gloss = pow(ndl, mix(48.0, 12.0, atlas.roughness));
  float defect = mix(1.0, 0.45, atlas.density);
  float phase = dot(atlas.tangent, uTilt) * 0.12 + atlas.height * 0.04;
  return (vec3(gloss * defect) + paletteRamp(phase) * grazing * 0.16) * 0.82;
}
vec3 materialEffect(vec2 uv, vec3 base, AtlasData atlas) { return materialEffect_clear_coat(uv, base, atlas); }
`,
  pearl: `
vec2 materialDistortion(vec2 uv, AtlasData atlas) { return atlas.normal.xy * 0.00035 * length(uTilt); }
vec3 materialEffect_pearl(vec2 uv, vec3 base, AtlasData atlas) {
  float axis = dot(uv - 0.5, atlas.tangent);
  float drift = dot(uTilt, atlas.tangent);
  float bandA = 0.5 + 0.5 * cos((axis + drift * 0.16 + atlas.height * 0.09) * 24.0);
  float bandB = 0.5 + 0.5 * cos((axis - drift * 0.19 - atlas.height * 0.07) * 19.0 + 1.7);
  float mica = smoothstep(0.16, 0.78, atlas.density) * mix(0.62, 1.0, 1.0 - atlas.roughness);
  vec3 interference = mix(paletteRamp(bandA * 0.36), paletteRamp(0.55 + bandB * 0.28), 0.5);
  vec3 milk = mix(vec3(luminance(base)), uAccent, 0.12);
  return mix(milk, interference, 0.72) * mica * 0.72;
}
vec3 materialEffect(vec2 uv, vec3 base, AtlasData atlas) { return materialEffect_pearl(uv, base, atlas); }
`,
  "brushed-metal": `
vec2 materialDistortion(vec2 uv, AtlasData atlas) { return vec2(0.0); }
vec3 materialEffect_brushed_metal(vec2 uv, vec3 base, AtlasData atlas) {
  vec2 crossAxis = vec2(-atlas.tangent.y, atlas.tangent.x);
  vec2 lightAxis = normalize(uTilt + vec2(0.001));
  float along = abs(dot(atlas.tangent, lightAxis));
  float cross = abs(dot(crossAxis, lightAxis));
  float groove = pow(saturate1(1.0 - along), mix(22.0, 5.0, atlas.roughness));
  float crossSheen = pow(saturate1(1.0 - cross), mix(36.0, 9.0, atlas.roughness));
  float structure = mix(0.34, 1.0, atlas.height) * mix(0.76, 1.0, atlas.density);
  vec3 metal = mix(vec3(luminance(base)), paletteRamp(atlas.angle / TAU + dot(uTilt, crossAxis) * 0.08), 0.24);
  return metal * (groove * 0.52 + crossSheen * 0.86) * structure;
}
vec3 materialEffect(vec2 uv, vec3 base, AtlasData atlas) { return materialEffect_brushed_metal(uv, base, atlas); }
`,
  "spectral-lines": `
vec2 materialDistortion(vec2 uv, AtlasData atlas) { return vec2(0.0); }
vec3 materialEffect_spectral_lines(vec2 uv, vec3 base, AtlasData atlas) {
  vec2 secondAxis = normalize(vec2(-atlas.tangent.y, atlas.tangent.x) + vec2(0.31, -0.17));
  float phaseA = dot(uv * uResolution / 18.0, atlas.tangent) + dot(uTilt, atlas.tangent) * 2.7 + atlas.height;
  float phaseB = dot(uv * uResolution / 23.0, secondAxis) - dot(uTilt, secondAxis) * 2.2 - atlas.height * 0.8;
  float broken = smoothstep(0.08, 0.62, atlas.density) * mix(0.62, 1.0, blueNoise(uv, vec2(0.43, 0.11)));
  float lineA = pow(saturate1(0.5 + 0.5 * cos(phaseA * TAU)), mix(18.0, 8.0, atlas.roughness));
  float lineB = pow(saturate1(0.5 + 0.5 * cos(phaseB * TAU)), mix(22.0, 10.0, atlas.roughness));
  return (paletteRamp(phaseA * 0.11) * lineA + paletteRamp(0.5 + phaseB * 0.13) * lineB * 0.78) * broken;
}
vec3 materialEffect(vec2 uv, vec3 base, AtlasData atlas) { return materialEffect_spectral_lines(uv, base, atlas); }
`,
  "etched-holo": `
vec2 materialDistortion(vec2 uv, AtlasData atlas) { return vec2(0.0); }
vec3 materialEffect_etched_holo(vec2 uv, vec3 base, AtlasData atlas) {
  vec2 crossAxis = vec2(-atlas.tangent.y, atlas.tangent.x);
  float edge = smoothstep(0.12, 0.72, abs(atlas.normal.x) + abs(atlas.normal.y));
  float phaseA = dot(uv * uResolution / 31.0, atlas.tangent) + dot(uTilt, crossAxis) * 1.7;
  float phaseB = dot(uv * uResolution / 37.0, crossAxis) - dot(uTilt, atlas.tangent) * 1.3 + 0.31;
  float segment = smoothstep(0.18, 0.74, atlas.density) * mix(0.45, 1.0, blueNoise(uv * 1.41, vec2(0.07, 0.61)));
  float hatch = pow(saturate1(0.5 + 0.5 * cos((phaseA + phaseB) * TAU)), mix(15.0, 6.0, atlas.roughness));
  return mix(uAccent, paletteRamp(phaseA * 0.17 + phaseB * 0.09), 0.58) * edge * segment * hatch;
}
vec3 materialEffect(vec2 uv, vec3 base, AtlasData atlas) { return materialEffect_etched_holo(uv, base, atlas); }
`,
  "cosmic-flake": `
vec2 materialDistortion(vec2 uv, AtlasData atlas) { return vec2(0.0); }
float flakeSample(vec2 uv, float scale, vec2 offset, vec2 drift) {
  vec4 packed = texture(uMaterialAtlas, uv * scale + offset + uTilt * drift);
  float noise = blueNoise(uv * scale, offset.yx);
  float angle = packed.a * TAU;
  vec2 tangent = vec2(cos(angle), sin(angle));
  float facing = pow(saturate1(abs(dot(tangent, normalize(uTilt + vec2(0.001))))), 6.0);
  return smoothstep(0.42, 0.86, packed.b) * mix(0.62, 1.0, noise) * facing;
}
vec3 materialEffect_cosmic_flake(vec2 uv, vec3 base, AtlasData atlas) {
  float large = flakeSample(uv, 1.0, vec2(0.0), vec2(0.006, -0.004));
  float medium = flakeSample(uv, 2.07, vec2(0.173, 0.419), vec2(-0.010, 0.008));
  float small = flakeSample(uv, 4.31, vec2(0.617, 0.283), vec2(0.016, -0.013));
  return paletteRamp(atlas.angle / TAU + dot(uTilt, atlas.tangent) * 0.11) * large * 0.92
       + paletteRamp(atlas.height * 0.43 + 0.34) * medium * 0.67
       + mix(vec3(1.0), uAccent, 0.38) * small * 0.48;
}
vec3 materialEffect(vec2 uv, vec3 base, AtlasData atlas) { return materialEffect_cosmic_flake(uv, base, atlas); }
`,
  "star-holo": `
vec2 materialDistortion(vec2 uv, AtlasData atlas) { return atlas.normal.xy * 0.00024 * length(uTilt); }
vec3 materialEffect_star_holo(vec2 uv, vec3 base, AtlasData atlas) {
  float starMask = smoothstep(0.24, 0.68, atlas.density);
  float core = smoothstep(0.42, 0.76, atlas.height) * starMask;
  float edge = max(0.0, starMask - core * 0.68);
  vec2 viewAxis = normalize(uTilt + vec2(0.001));
  float angleFacing = pow(saturate1(abs(dot(atlas.tangent, viewAxis))), 10.0);
  float embossedBase = starMask * mix(0.10, 0.15, 1.0 - atlas.roughness);
  vec3 whiteCore = vec3(1.0) * core * (embossedBase + angleFacing * 1.16);
  vec3 rainbowEdge = paletteRamp(atlas.angle / TAU + dot(uTilt, atlas.tangent) * 0.08)
                   * edge * (0.08 + angleFacing * 0.62);
  return whiteCore + rainbowEdge;
}
vec3 materialEffect(vec2 uv, vec3 base, AtlasData atlas) { return materialEffect_star_holo(uv, base, atlas); }
`,
});

const FRAGMENT_MAIN = `
void main() {
  float outerMask = roundedRectMask(vUv, 0.055);
  float innerMask = innerSurfaceMask(vUv, uFrameInset, uInnerRadius);
  vec2 surfaceUv = clamp((vUv - uFrameInset) / max(vec2(0.001), vec2(1.0 - uFrameInset * 2.0)), vec2(0.001), vec2(0.999));
  AtlasData atlas = decodeAtlas(surfaceUv);
  vec2 distortion = materialDistortion(surfaceUv, atlas) * clamp(uFoilIntensity, 0.0, 1.0) * uReveal;
  vec2 sampleUv = clamp(surfaceUv + distortion, vec2(0.001), vec2(0.999));
  vec3 base = texture(uBackground, sampleUv).rgb;
  float mask = reflectionMask(surfaceUv, base, atlas);
  vec3 spectral = flagshipOptics(surfaceUv, base, atlas, mask);
  vec3 material = materialEffect(surfaceUv, base, atlas) * clamp(uFoilIntensity, 0.0, 1.0);
  vec3 coat = coatSweepOptics(surfaceUv, atlas, mask);
  float textureValue = auxiliaryTexture(surfaceUv, base, atlas) * clamp(uTextureIntensity, 0.0, 1.0);
  float sparkle = sparkleField(surfaceUv, atlas) * clamp(uSparkleIntensity, 0.0, 1.0);
  float glare = pointerGlare(surfaceUv) * clamp(uGlareIntensity, 0.0, 1.0);
  vec3 textureResponse = mix(vec3(0.64), paletteRamp(atlas.angle / TAU + uTime * 0.01), 0.52) * textureValue * mask * 0.58;
  vec3 optical = material * mask * 0.74 + textureResponse + paletteRamp(atlas.height * 0.37 + uTime * 0.014) * sparkle * 1.05 + vec3(glare * 0.72);
  vec2 lightDirection = normalize(uTilt + vec2(0.001));
  float sided = dot(surfaceUv - 0.5, lightDirection);
  float litSide = smoothstep(-0.18, 0.52, sided);
  float darkSide = 1.0 - smoothstep(-0.68, -0.05, sided);
  vec3 shaped = spectral * mix(0.76, 1.12, litSide) * (1.0 - darkSide * (0.22 + uFoilIntensity * 0.18));
  vec3 result = shaped + optical * uReveal;
  result = screenBlend(result, coat * uReveal * 0.56);
  result = mix(base, screenBlend(result, vec3(glare * 0.34)), uReveal);
  float edge = 1.0 - smoothstep(0.0, 0.12, abs(vUv.x - 0.5) + abs(vUv.y - 0.5));
  float frameLight = smoothstep(0.04, 0.82, dot(vUv, normalize(vec2(0.84, 0.54))) + uTilt.x * 0.18 - uTilt.y * 0.12);
  vec3 frameBase = mix(uFrameShadow, uFrameColor, frameLight);
  frameBase = mix(frameBase, uFrameHighlight, edge * (0.12 + uFoilIntensity * 0.28));
  vec3 composited = mix(frameBase, result, innerMask);
  outColor = vec4(clamp(composited, 0.0, 1.0), outerMask);
}`;

export class HolographicRendererError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "HolographicRendererError";
    this.code = code;
  }
}

export function clampDevicePixelRatio(value, { mobile = false } = {}) {
  const limit = mobile ? MOBILE_MAX_DEVICE_PIXEL_RATIO : MAX_DEVICE_PIXEL_RATIO;
  return Math.min(limit, Math.max(1, Number.isFinite(Number(value)) ? Number(value) : 1));
}

export function buildFragmentShader(family) {
  if (!MATERIAL_SET.has(family)) throw new HolographicRendererError("unknown-material", `Unknown material: ${family}`);
  return `${FRAGMENT_HEADER}${MATERIAL_BODIES[family]}${FRAGMENT_MAIN}`;
}

function clampIntensity(value) {
  return Math.max(0, Math.min(1, Number(value) || 0));
}

function hexColor(value, fallback) {
  const match = /^#([0-9a-f]{6})$/i.exec(typeof value === "string" ? value : fallback);
  const raw = match ? match[1] : fallback.slice(1);
  return [0, 2, 4].map(offset => parseInt(raw.slice(offset, offset + 2), 16) / 255);
}

function compileShader(gl, type, source) {
  const shader = gl.createShader(type);
  if (!shader) throw new HolographicRendererError("shader-create", "Unable to create a WebGL2 shader.");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const detail = gl.getShaderInfoLog(shader) || "unknown compiler error";
    gl.deleteShader(shader);
    throw new HolographicRendererError("shader-compile", `WebGL2 shader compilation failed: ${detail}`);
  }
  return shader;
}

function createProgram(gl, family) {
  const vertex = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER);
  const fragment = compileShader(gl, gl.FRAGMENT_SHADER, buildFragmentShader(family));
  const program = gl.createProgram();
  if (!program) throw new HolographicRendererError("program-create", "Unable to create a WebGL2 program.");
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.linkProgram(program);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const detail = gl.getProgramInfoLog(program) || "unknown linker error";
    gl.deleteProgram(program);
    throw new HolographicRendererError("program-link", `WebGL2 program linking failed: ${detail}`);
  }
  return program;
}

function backgroundIntensity(presentation, kind) {
  const value = presentation?.[kind] || {};
  let target = value.target;
  if (target === "surface" && kind === "foil" && presentation?.surface?.material !== "clear-coat") target = "background";
  if (target === "surface" && (kind === "texture" || kind === "sparkle")) target = "background";
  if (target !== "background") return 0;
  if ((kind === "foil" || kind === "sparkle" || kind === "glare") && !value.enabled) return 0;
  return perceptualIntensity(clampIntensity(value.intensity), kind);
}

async function loadTextureImage(url, label, signal) {
  let response;
  try {
    response = await fetch(url, { cache: "force-cache", signal });
  } catch (error) {
    throw new HolographicRendererError("material-texture-load", `Unable to load ${label}: ${error}`);
  }
  if (!response.ok) throw new HolographicRendererError("material-texture-load", `Unable to load ${label}: HTTP ${response.status}.`);
  let blob;
  try {
    blob = await response.blob();
  } catch (error) {
    throw new HolographicRendererError("material-texture-load", `Unable to read ${label}: ${error}`);
  }
  try {
    if (typeof createImageBitmap === "function") {
      const bitmap = await createImageBitmap(blob);
      if (!bitmap.width || !bitmap.height) throw new Error("decoded bitmap has no dimensions");
      return bitmap;
    }
    if (typeof Image !== "function") throw new Error("image decoding is unavailable");
    const image = new Image();
    image.decoding = "async";
    image.src = url;
    if (typeof image.decode === "function") await image.decode();
    else await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = () => reject(new Error("image decode failed")); });
    if (!image.naturalWidth || !image.naturalHeight) throw new Error("decoded image has no dimensions");
    return image;
  } catch (error) {
    throw new HolographicRendererError("material-texture-decode", `Unable to decode ${label}: ${error}`);
  }
}

export function createHolographicRenderer({ canvas, image, presentation, mobile = false, onError = () => {} }) {
  const gl = canvas?.getContext?.("webgl2", {
    // A transparent WebGL surface preserves the rounded card corners in
    // Android WebView instead of filling the surrounding rectangle black.
    alpha: true,
    antialias: !mobile,
    depth: false,
    stencil: false,
    premultipliedAlpha: false,
    powerPreference: "high-performance",
    preserveDrawingBuffer: false,
  });
  if (!gl) throw new HolographicRendererError("webgl2-unavailable", "WebGL2 is required for holographic material rendering.");
  if (!image || !image.complete || !image.naturalWidth || !image.naturalHeight) {
    throw new HolographicRendererError("image-unavailable", "The background image must be loaded before WebGL2 initialization.");
  }

  let activePresentation = presentation;
  let family = presentation?.surface?.material;
  if (!MATERIAL_SET.has(family)) throw new HolographicRendererError("unknown-material", `Unknown material: ${family}`);
  let uniformState = null;
  const refreshUniformState = () => {
    const accent = activePresentation?.surface?.accent || "#a7d9e8";
    const frameColor = hexColor(activePresentation?.frame?.color, "#8d82c9");
    uniformState = {
      accent,
      colors: expandFoilColors(activePresentation?.foil?.colors, accent).map(color => hexColor(color, accent)),
      accentRgb: hexColor(accent, "#a7d9e8"),
      frameColor,
      frameHighlight: frameColor.map(value => Math.min(1, value * 1.18)),
      frameShadow: frameColor.map(value => value * 0.84),
      frameInset: activePresentation?.frame?.style === "none" ? 0 : Math.max(0.008, Math.min(0.14, (Number(activePresentation?.frame?.width) || 0) / 100)),
      innerRadius: Math.max(0.018, Math.min(0.18, (Number(activePresentation?.radius?.inner) || 5) / 100)),
      foil: backgroundIntensity(activePresentation, "foil"),
      texture: backgroundIntensity(activePresentation, "texture"),
      sparkle: backgroundIntensity(activePresentation, "sparkle"),
      glare: backgroundIntensity(activePresentation, "glare") * MATERIAL_PROFILES[family].backgroundGlareFactor,
      textureKind: TEXTURE_INDEX[activePresentation?.texture?.kind] ?? 0,
    };
  };
  refreshUniformState();
  let program = createProgram(gl, family);
  let failed = false;
  let disposed = false;
  let graphicsReleased = false;
  let texturesReady = false;
  let reducedMotion = false;
  let paused = false;
  let mode = "idle";
  let frame = 0;
  let epoch = performance.now();
  let releaseTime = 0;
  let releasePoint = { x: 0, y: 0 };
  let currentPoint = { x: 0, y: 0 };
  let targetPoint = { x: 0, y: 0 };
  let loadGeneration = 0;
  let readyError = null;
  let readyPromise = Promise.resolve();
  let loadController = null;
  let lastSize = { cssWidth: 0, cssHeight: 0, width: 1, height: 1, dpr: 1 };
  let resizeDirty = true;
  let lastRenderAt = 0;
  let previousFrameTime = 0;
  const frameIntervals = [];
  const uniformCache = new Map();
  const requestFrame = globalThis.requestAnimationFrame?.bind(globalThis) || (callback => {
    const timer = setTimeout(() => callback(performance.now()), 16);
    timer.unref?.();
    return timer;
  });
  const cancelFrame = globalThis.cancelAnimationFrame?.bind(globalThis) || clearTimeout;

  let vao = gl.createVertexArray();
  let buffer = gl.createBuffer();
  if (!vao || !buffer) throw new HolographicRendererError("buffer-create", "Unable to create WebGL2 geometry buffers.");
  gl.bindVertexArray(vao);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
  let positionLocation = gl.getAttribLocation(program, "aPosition");

  let backgroundTexture = gl.createTexture();
  if (!backgroundTexture) throw new HolographicRendererError("texture-create", "Unable to create the WebGL2 background texture.");
  gl.bindTexture(gl.TEXTURE_2D, backgroundTexture);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  try {
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
  } catch (error) {
    throw new HolographicRendererError("texture-upload", `Unable to upload the background image to WebGL2: ${error}`);
  }

  let materialTexture = null;
  let blueNoiseTexture = null;
  let microGrainTexture = null;

  function releaseGraphics() {
    if (graphicsReleased) return;
    graphicsReleased = true;
    for (const texture of [materialTexture, blueNoiseTexture, microGrainTexture, backgroundTexture]) {
      if (texture) { try { gl.deleteTexture(texture); } catch {} }
    }
    materialTexture = blueNoiseTexture = microGrainTexture = backgroundTexture = null;
    if (program) { try { gl.deleteProgram(program); } catch {} program = null; }
    if (buffer) { try { gl.deleteBuffer(buffer); } catch {} buffer = null; }
    if (vao) { try { gl.deleteVertexArray(vao); } catch {} vao = null; }
  }

  function fail(error) {
    if (failed || disposed) return;
    failed = true;
    texturesReady = false;
    if (frame) cancelFrame(frame);
    frame = 0;
    loadController?.abort();
    releaseGraphics();
    onError(error instanceof Error ? error : new HolographicRendererError("runtime", String(error)));
  }

  function handleContextLost(event) {
    event.preventDefault();
    fail(new HolographicRendererError("context-lost", "The WebGL2 context was lost. Reload the preview to continue."));
  }
  canvas.addEventListener("webglcontextlost", handleContextLost, false);

  function uploadMaterialTexture(source, label) {
    const texture = gl.createTexture();
    if (!texture) throw new HolographicRendererError("texture-create", `Unable to create ${label}.`);
    try {
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
      gl.generateMipmap(gl.TEXTURE_2D);
      if (typeof gl.getError === "function" && gl.getError() !== (gl.NO_ERROR ?? 0)) throw new Error("WebGL reported a texture upload error");
      return texture;
    } catch (error) {
      gl.deleteTexture(texture);
      throw new HolographicRendererError("material-texture-upload", `Unable to upload ${label}: ${error}`);
    }
  }

  function resize() {
    if (disposed || failed) return { width: canvas.width || 1, height: canvas.height || 1, dpr: 1 };
    const bounds = canvas.getBoundingClientRect();
    const requestedDpr = clampDevicePixelRatio(globalThis.devicePixelRatio || 1, { mobile });
    const cssWidth = canvas.clientWidth || bounds.width;
    const cssHeight = canvas.clientHeight || bounds.height;
    const requestedPixels = Math.max(1, cssWidth * cssHeight * requestedDpr * requestedDpr);
    const pixelScale = mobile
      ? Math.min(1, Math.sqrt(MOBILE_MAX_CANVAS_PIXELS / requestedPixels))
      : 1;
    const dpr = requestedDpr * pixelScale;
    const width = Math.max(1, Math.round(cssWidth * dpr));
    const height = Math.max(1, Math.round(cssHeight * dpr));
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    gl.viewport(0, 0, width, height);
    lastSize = { cssWidth, cssHeight, width, height, dpr };
    resizeDirty = false;
    return { width, height, dpr };
  }

  function uniform(name) {
    if (!uniformCache.has(name)) uniformCache.set(name, gl.getUniformLocation(program, name));
    return uniformCache.get(name);
  }

  function bindTextureUnit(texture, unit, uniformName) {
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.uniform1i(uniform(uniformName), unit);
  }

  function render(point = currentPoint, now = performance.now()) {
    if (failed || disposed || !texturesReady) return;
    try {
      const size = resizeDirty ? resize() : lastSize;
      gl.useProgram(program);
      gl.bindVertexArray(vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.enableVertexAttribArray(positionLocation);
      gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);
      bindTextureUnit(backgroundTexture, 0, "uBackground");
      bindTextureUnit(materialTexture, 1, "uMaterialAtlas");
      bindTextureUnit(blueNoiseTexture, 2, "uBlueNoise");
      bindTextureUnit(microGrainTexture, 3, "uMicroGrain");
      gl.uniform2f(uniform("uResolution"), size.width, size.height);
      gl.uniform2f(uniform("uTilt"), point.x, point.y);
      gl.uniform1f(uniform("uReveal"), interactionReveal(point.x, point.y));
      gl.uniform1f(uniform("uTime"), (now - epoch) / 1000);

      uniformState.colors.forEach((color, index) => gl.uniform3fv(uniform(`uPalette${index}`), color));
      gl.uniform3fv(uniform("uAccent"), uniformState.accentRgb);
      gl.uniform3fv(uniform("uFrameColor"), uniformState.frameColor);
      gl.uniform3fv(uniform("uFrameHighlight"), uniformState.frameHighlight);
      gl.uniform3fv(uniform("uFrameShadow"), uniformState.frameShadow);
      gl.uniform1f(uniform("uFrameInset"), uniformState.frameInset);
      gl.uniform1f(uniform("uInnerRadius"), uniformState.innerRadius);
      gl.uniform1f(uniform("uAspect"), size.width / Math.max(size.height, 1));
      gl.uniform1f(uniform("uFoilIntensity"), uniformState.foil);
      gl.uniform1f(uniform("uTextureIntensity"), uniformState.texture);
      gl.uniform1f(uniform("uSparkleIntensity"), uniformState.sparkle);
      gl.uniform1f(uniform("uGlareIntensity"), uniformState.glare);
      gl.uniform1i(uniform("uTextureKind"), uniformState.textureKind);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
    } catch (error) {
      fail(error);
    }
  }

  function trackReady(task) {
    readyError = null;
    readyPromise = task.catch(error => {
      if (!disposed) { readyError = error; fail(error); }
    });
  }

  function beginInitialLoad() {
    const generation = ++loadGeneration;
    loadController?.abort();
    loadController = typeof AbortController === "function" ? new AbortController() : null;
    const signal = loadController?.signal;
    trackReady(Promise.all([
      loadTextureImage(MATERIAL_TEXTURE_URLS[family], `${family} material texture`, signal),
      loadTextureImage(BLUE_NOISE_URL, "blue-noise texture", signal),
      loadTextureImage(MICRO_GRAIN_URL, "micro-grain texture", signal),
    ]).then(([materialImage, blueImage, grainImage]) => {
      if (disposed || failed || generation !== loadGeneration) return;
      const uploaded = [];
      try {
        uploaded.push(uploadMaterialTexture(materialImage, `${family} material texture`));
        uploaded.push(uploadMaterialTexture(blueImage, "blue-noise texture"));
        uploaded.push(uploadMaterialTexture(grainImage, "micro-grain texture"));
      } catch (error) {
        for (const texture of uploaded) gl.deleteTexture(texture);
        throw error;
      } finally {
        materialImage.close?.();
        blueImage.close?.();
        grainImage.close?.();
      }
      [materialTexture, blueNoiseTexture, microGrainTexture] = uploaded;
      texturesReady = true;
      if (reducedMotion) render({ x: 0.48, y: -0.36 });
      else ensureAnimation();
    }));
  }

  function ensureAnimation() {
    if (!frame && !failed && !disposed && !paused && !reducedMotion && texturesReady) {
      previousFrameTime = 0;
      frame = requestFrame(animate);
    }
  }

  function animate(now) {
    frame = 0;
    if (failed || disposed || paused || reducedMotion || !texturesReady) return;
    const targetInterval = mode === "idle" ? IDLE_FRAME_INTERVAL_MS : ACTIVE_FRAME_INTERVAL_MS;
    if (lastRenderAt && now - lastRenderAt < targetInterval) {
      frame = requestFrame(animate);
      return;
    }
    if (previousFrameTime) {
      frameIntervals.push(now - previousFrameTime);
      if (frameIntervals.length > 600) frameIntervals.shift();
    }
    const elapsed = previousFrameTime ? Math.min(50, now - previousFrameTime) : 16.67;
    previousFrameTime = now;
    if (mode === "idle") {
      currentPoint = idlePoint(now - epoch);
    } else if (mode === "interactive") {
      const smoothing = Math.max(0.08, Math.min(0.4, Number(activePresentation?.motion?.smoothing || 0.18)));
      const amount = 1 - Math.exp(-elapsed / (smoothing * 180));
      currentPoint = {
        x: currentPoint.x + (targetPoint.x - currentPoint.x) * amount,
        y: currentPoint.y + (targetPoint.y - currentPoint.y) * amount,
      };
    } else if (mode === "release") {
      const progress = Math.min(1, (now - releaseTime) / 1200);
      const destination = idlePoint(now - epoch);
      const overshoot = Math.sin(progress * Math.PI * 3) * (1 - progress) * 0.11;
      const eased = 1 - Math.pow(1 - progress, 3);
      currentPoint = {
        x: releasePoint.x + (destination.x - releasePoint.x) * eased + overshoot,
        y: releasePoint.y + (destination.y - releasePoint.y) * eased - overshoot * 0.72,
      };
      if (progress >= 1) mode = "idle";
    }
    lastRenderAt = now;
    render(currentPoint, now);
    frame = requestFrame(animate);
  }

  function setPointer(x, y, immediate = false, renderImmediately = immediate) {
    if (disposed || failed) return;
    if (reducedMotion) {
      currentPoint = targetPoint = { x: 0.48, y: -0.36 };
      render(currentPoint);
      return;
    }
    const next = {
      x: Math.max(-1, Math.min(1, Number(x) || 0)),
      y: Math.max(-1, Math.min(1, Number(y) || 0)),
    };
    targetPoint = next;
    mode = immediate ? "locked" : "interactive";
    if (immediate) {
      currentPoint = next;
      if (renderImmediately) render(currentPoint);
    }
    ensureAnimation();
  }

  function releasePointer() {
    if (disposed || failed || reducedMotion) return;
    releasePoint = { ...currentPoint };
    releaseTime = performance.now();
    mode = "release";
    ensureAnimation();
  }

  function setPresentation(nextPresentation) {
    if (disposed || failed) return;
    const nextFamily = nextPresentation?.surface?.material;
    if (!MATERIAL_SET.has(nextFamily)) throw new HolographicRendererError("unknown-material", `Unknown material: ${nextFamily}`);
    if (nextFamily === family) {
      activePresentation = nextPresentation;
      if (reducedMotion) render({ x: 0.48, y: -0.36 });
      else ensureAnimation();
      return;
    }
    let nextProgram;
    try { nextProgram = createProgram(gl, nextFamily); }
    catch (error) { fail(error); throw error; }
    if (!texturesReady) {
      gl.deleteProgram(program);
      program = nextProgram;
      positionLocation = gl.getAttribLocation(program, "aPosition");
      family = nextFamily;
      activePresentation = nextPresentation;
      refreshUniformState();
      uniformCache.clear();
      beginInitialLoad();
      return;
    }
    const generation = ++loadGeneration;
    loadController?.abort();
    loadController = typeof AbortController === "function" ? new AbortController() : null;
    trackReady(loadTextureImage(MATERIAL_TEXTURE_URLS[nextFamily], `${nextFamily} material texture`, loadController?.signal).then(source => {
      if (disposed || failed || generation !== loadGeneration) { gl.deleteProgram(nextProgram); return; }
      let nextTexture;
      try { nextTexture = uploadMaterialTexture(source, `${nextFamily} material texture`); }
      finally { source.close?.(); }
      const previousProgram = program;
      const previousTexture = materialTexture;
      program = nextProgram;
      materialTexture = nextTexture;
      family = nextFamily;
      activePresentation = nextPresentation;
      refreshUniformState();
      uniformCache.clear();
      gl.deleteProgram(previousProgram);
      gl.deleteTexture(previousTexture);
      if (reducedMotion) render({ x: 0.48, y: -0.36 });
      else ensureAnimation();
    }).catch(error => {
      try { gl.deleteProgram(nextProgram); } catch {}
      throw error;
    }));
  }

  function setReducedMotion(value) {
    reducedMotion = Boolean(value);
    if (reducedMotion) {
      if (frame) cancelFrame(frame);
      frame = 0;
      lastRenderAt = 0;
      mode = "reduced-motion";
      currentPoint = targetPoint = { x: 0.48, y: -0.36 };
      render(currentPoint);
    } else {
      mode = "idle";
      epoch = performance.now();
      ensureAnimation();
    }
  }

  function setPaused(value) {
    paused = Boolean(value);
    if (paused) {
      if (frame) cancelFrame(frame);
      frame = 0;
      previousFrameTime = 0;
      lastRenderAt = 0;
      return;
    }
    if (!reducedMotion) ensureAnimation();
  }

  function diagnostics() {
    const sorted = [...frameIntervals].sort((a, b) => a - b);
    const averageFrameMs = frameIntervals.length ? frameIntervals.reduce((sum, value) => sum + value, 0) / frameIntervals.length : 0;
    const p95FrameMs = sorted.length ? sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.95) - 1)] : 0;
    return {
      frames: frameIntervals.length,
      averageFrameMs: Number(averageFrameMs.toFixed(3)),
      p95FrameMs: Number(p95FrameMs.toFixed(3)),
      width: canvas.width,
      height: canvas.height,
      cssWidth: Number(lastSize.cssWidth.toFixed(2)),
      cssHeight: Number(lastSize.cssHeight.toFixed(2)),
      dpr: Number(lastSize.dpr.toFixed(3)),
      pixelArea: canvas.width * canvas.height,
      maxTextureSize: typeof gl.getParameter === "function" ? gl.getParameter(gl.MAX_TEXTURE_SIZE) : null,
      mobile,
      failed,
      ready: texturesReady,
      animationPending: Boolean(frame),
      mode: paused ? "paused" : mode,
      targetFrameMs: mode === "idle" ? Number(IDLE_FRAME_INTERVAL_MS.toFixed(3)) : Number(ACTIVE_FRAME_INTERVAL_MS.toFixed(3)),
    };
  }

  function ready() {
    return readyPromise.then(() => {
      if (readyError) throw readyError;
      if (disposed) throw new HolographicRendererError("renderer-disposed", "The holographic renderer was disposed before it became ready.");
    });
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    loadGeneration += 1;
    loadController?.abort();
    if (frame) cancelFrame(frame);
    frame = 0;
    canvas.removeEventListener("webglcontextlost", handleContextLost, false);
    releaseGraphics();
  }

  resize();
  beginInitialLoad();
  return {
    ready,
    setPointer,
    releasePointer,
    setPresentation,
    setReducedMotion,
    setPaused,
    resize: () => { resize(); render(); },
    render: () => render(),
    diagnostics,
    dispose,
  };
}
