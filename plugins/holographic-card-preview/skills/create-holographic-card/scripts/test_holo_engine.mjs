import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  MATERIAL_FAMILIES,
  TEXTURE_KINDS,
  NEUTRAL_REVEAL,
  MAX_DEVICE_PIXEL_RATIO,
  buildFragmentShader,
  clampDevicePixelRatio,
  interactionReveal,
  createHolographicRenderer,
} from "../assets/react-template/holo-engine.js";

const engineSource = await readFile(new URL("../assets/react-template/holo-engine.js", import.meta.url), "utf8");
for (const name of [...MATERIAL_FAMILIES, "blue-noise", "micro-grain"]) {
  assert.match(engineSource, new RegExp(`new URL\\(\\"\\./holo-textures/${name}\\.webp\\", import\\.meta\\.url\\)`));
}

assert.deepEqual(MATERIAL_FAMILIES, [
  "clear-coat", "pearl", "brushed-metal", "spectral-lines", "etched-holo", "cosmic-flake", "star-holo",
]);
assert.deepEqual(TEXTURE_KINDS, ["none", "micro-grain", "scanline", "geometric", "contour", "sparse-flake"]);
assert.equal(NEUTRAL_REVEAL, 0.7);
assert.equal(MAX_DEVICE_PIXEL_RATIO, 2);
assert.match(engineSource, /MOBILE_MAX_CANVAS_PIXELS = 1600000/);
assert.match(engineSource, /mode = "idle"/);
assert.match(engineSource, /releaseTime\) \/ 1200/);
assert.match(engineSource, /uTime/);
assert.equal(clampDevicePixelRatio(0.5), 1);
assert.equal(clampDevicePixelRatio(3), 2);
assert.equal(interactionReveal(0, 0), 0.7);
assert.ok(interactionReveal(1, 0) > 0.9);
assert.equal(interactionReveal(1, 1), 1);

for (const family of MATERIAL_FAMILIES) {
  const shader = buildFragmentShader(family);
  assert.match(shader, /^#version 300 es/);
  assert.match(shader, new RegExp(`materialEffect_${family.replaceAll("-", "_")}`));
  assert.match(shader, /uBackground/);
  assert.match(shader, /uMaterialAtlas/);
  assert.match(shader, /uBlueNoise/);
  assert.match(shader, /uMicroGrain/);
  assert.match(shader, /decodeAtlas/);
  assert.match(shader, /reflectionMask/);
  assert.match(shader, /flagshipOptics/);
  assert.match(shader, /dodgeBlend/);
  assert.match(shader, /hardLightBlend/);
  assert.match(shader, /uPalette5/);
  assert.doesNotMatch(shader, /uMaterialFamily/);
  assert.doesNotMatch(shader, /https?:\/\//);
}
const starShader = buildFragmentShader("star-holo");
assert.match(starShader, /materialEffect_star_holo/);
assert.match(starShader, /whiteCore/);
assert.match(starShader, /rainbowEdge/);
assert.match(starShader, /pow\(saturate1\(abs\(dot\(atlas\.tangent, viewAxis\)\)\), 10\.0\)/);
assert.doesNotMatch(starShader, /flakeSample/);
assert.throws(() => buildFragmentShader("rainbow"), /Unknown material/);
assert.throws(
  () => createHolographicRenderer({ canvas: { getContext: () => null }, image: {}, presentation: {} }),
  /WebGL2 is required/,
);
const compileFailure = {
  VERTEX_SHADER: 1,
  FRAGMENT_SHADER: 2,
  COMPILE_STATUS: 3,
  createShader: () => ({}),
  shaderSource: () => {},
  compileShader: () => {},
  getShaderParameter: () => false,
  getShaderInfoLog: () => "forced compiler failure",
  deleteShader: () => {},
};
assert.throws(
  () => createHolographicRenderer({
    canvas: { getContext: () => compileFailure },
    image: { complete: true, naturalWidth: 10, naturalHeight: 14 },
    presentation: { surface: { material: "clear-coat" } },
  }),
  /forced compiler failure/,
);

const originalFetch = globalThis.fetch;
const originalImage = globalThis.Image;
const originalCreateImageBitmap = globalThis.createImageBitmap;
const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;
const fetchLog = [];
let fetchFailure = "";
let decodeFailure = "";

globalThis.fetch = async (url, options = {}) => {
  const value = String(url);
  fetchLog.push(value);
  await Promise.resolve();
  if (options.signal?.aborted) throw new Error("aborted");
  if (fetchFailure && value.includes(fetchFailure)) return { ok: false, status: 404, blob: async () => ({ assetUrl: value }) };
  return { ok: true, status: 200, blob: async () => ({ assetUrl: value }) };
};
URL.createObjectURL = blob => blob.assetUrl;
URL.revokeObjectURL = () => {};
class FakeImage {
  constructor() { this.naturalWidth = 512; this.naturalHeight = 512; this.width = 512; this.height = 512; this.complete = true; this.src = ""; }
  async decode() {
    await Promise.resolve();
    if (decodeFailure && this.src.includes(decodeFailure)) throw new Error("forced decode failure");
  }
  close() {}
}
globalThis.Image = FakeImage;
globalThis.createImageBitmap = async blob => {
  if (decodeFailure && blob.assetUrl.includes(decodeFailure)) throw new Error("forced decode failure");
  const image = new FakeImage();
  image.src = blob.assetUrl;
  return image;
};

function mockContext(options = {}) {
  const noop = () => {};
  let textureId = 0;
  const metrics = { mipmaps: 0, repeatParameters: 0, deletedTextures: 0, deletedPrograms: 0, uniforms: new Map() };
  const context = {
    VERTEX_SHADER: 1, FRAGMENT_SHADER: 2, COMPILE_STATUS: 3, LINK_STATUS: 4,
    ARRAY_BUFFER: 5, STATIC_DRAW: 6, TEXTURE_2D: 7, UNPACK_FLIP_Y_WEBGL: 8,
    TEXTURE_MIN_FILTER: 9, TEXTURE_MAG_FILTER: 10, LINEAR: 11, TEXTURE_WRAP_S: 12,
    TEXTURE_WRAP_T: 13, CLAMP_TO_EDGE: 14, RGBA: 15, UNSIGNED_BYTE: 16,
    TEXTURE0: 100, FLOAT: 18, TRIANGLES: 19, LINEAR_MIPMAP_LINEAR: 20, REPEAT: 21, NO_ERROR: 0,
    createShader: () => ({}), shaderSource: noop, compileShader: noop,
    getShaderParameter: () => true, getShaderInfoLog: () => "", deleteShader: noop,
    createProgram: () => ({}), attachShader: noop, linkProgram: noop,
    getProgramParameter: () => true, getProgramInfoLog: () => "", deleteProgram: () => { metrics.deletedPrograms += 1; },
    createVertexArray: () => ({}), createBuffer: () => ({}), bindVertexArray: noop,
    bindBuffer: noop, bufferData: noop, createTexture: () => ({ id: ++textureId }), bindTexture: noop,
    pixelStorei: noop,
    texParameteri: (_target, parameter, value) => { if ((parameter === 12 || parameter === 13) && value === 21) metrics.repeatParameters += 1; },
    texImage2D: (...args) => { if (options.failMaterialUpload && args.at(-1) instanceof FakeImage) throw new Error("forced upload failure"); },
    generateMipmap: () => { metrics.mipmaps += 1; }, getError: () => 0, getParameter: () => 4096, viewport: noop,
    useProgram: noop, getAttribLocation: () => 0, enableVertexAttribArray: noop,
    vertexAttribPointer: noop, activeTexture: noop, getUniformLocation: (_program, name) => name,
    uniform1i: noop, uniform2f: noop, uniform1f: (name, value) => metrics.uniforms.set(name, value), uniform3fv: noop,
    drawArrays: noop, deleteTexture: () => { metrics.deletedTextures += 1; }, deleteBuffer: noop, deleteVertexArray: noop,
  };
  context.metrics = metrics;
  return context;
}
function mockCanvas(context = mockContext()) {
  const listeners = {};
  return {
    width: 0, height: 0, listeners, context,
    getContext: () => context,
    getBoundingClientRect: () => ({ width: 420, height: 588 }),
    addEventListener: (name, handler) => { listeners[name] = handler; },
    removeEventListener: (name) => { delete listeners[name]; },
  };
}
const validPresentation = {
  surface: { material: "clear-coat", accent: "#a7d9e8" },
  foil: { enabled: true, target: "background", colors: ["#a7d9e8", "#8e80c2"], intensity: 0.2 },
  texture: { kind: "micro-grain", target: "background", intensity: 0.1 },
  sparkle: { enabled: true, target: "background", intensity: 0.08 },
  glare: { enabled: true, target: "background", intensity: 0.15 },
  motion: { smoothing: 0.18 },
};
globalThis.devicePixelRatio = 3;
const firstCanvas = mockCanvas(), secondCanvas = mockCanvas(), errors = [];
const firstRenderer = createHolographicRenderer({ canvas: firstCanvas, image: { complete: true, naturalWidth: 10, naturalHeight: 14 }, presentation: validPresentation, onError: error => errors.push(error) });
const secondRenderer = createHolographicRenderer({ canvas: secondCanvas, image: { complete: true, naturalWidth: 10, naturalHeight: 14 }, presentation: validPresentation });
assert.equal(typeof firstRenderer.ready, "function");
await Promise.all([firstRenderer.ready(), secondRenderer.ready()]);
assert.equal(firstCanvas.width, 840);
assert.equal(firstCanvas.height, 1176);
assert.equal(firstCanvas.context.metrics.mipmaps, 3);
assert.equal(firstCanvas.context.metrics.repeatParameters, 6);
assert.equal(firstRenderer.diagnostics().ready, true);
assert.equal(firstRenderer.diagnostics().mode, "idle");
assert.equal(fetchLog.filter(url => url.endsWith("clear-coat.webp")).length, 2);
assert.equal(fetchLog.filter(url => url.endsWith("blue-noise.webp")).length, 2);
assert.equal(fetchLog.filter(url => url.endsWith("micro-grain.webp")).length, 2);

const pearlPresentation = structuredClone(validPresentation);
pearlPresentation.surface.material = "pearl";
secondRenderer.setPresentation(pearlPresentation);
await secondRenderer.ready();
assert.equal(secondCanvas.context.metrics.mipmaps, 4);
assert.ok(fetchLog.some(url => url.endsWith("pearl.webp")));
assert.throws(() => secondRenderer.setPresentation({ surface: { material: "rainbow" } }), /Unknown material/);

const unbounded = structuredClone(pearlPresentation);
unbounded.foil.intensity = 4;
unbounded.texture.intensity = 3;
unbounded.sparkle.intensity = 2;
unbounded.glare.intensity = 5;
secondRenderer.setPresentation(unbounded);
secondRenderer.render();
for (const name of ["uFoilIntensity", "uTextureIntensity", "uSparkleIntensity", "uGlareIntensity"]) {
  assert.ok(secondCanvas.context.metrics.uniforms.get(name) <= 1, `${name} must be clamped`);
}
secondRenderer.setReducedMotion(true);
secondRenderer.setPointer(1, 1);
assert.equal(secondRenderer.diagnostics().animationPending, false);
assert.equal(secondRenderer.diagnostics().mode, "reduced-motion");
secondRenderer.setReducedMotion(false);
secondRenderer.releasePointer();
assert.equal(secondRenderer.diagnostics().mode, "release");
secondRenderer.setPaused(true);
assert.equal(secondRenderer.diagnostics().mode, "paused");
assert.equal(secondRenderer.diagnostics().animationPending, false);

let prevented = false;
firstCanvas.listeners.webglcontextlost({ preventDefault: () => { prevented = true; } });
assert.equal(prevented, true);
assert.equal(errors[0].code, "context-lost");
assert.equal(firstRenderer.diagnostics().failed, true);
assert.equal(secondRenderer.diagnostics().failed, false);
firstRenderer.dispose();
secondRenderer.dispose();

fetchFailure = "blue-noise.webp";
const loadErrors = [];
const loadFailureRenderer = createHolographicRenderer({ canvas: mockCanvas(), image: { complete: true, naturalWidth: 10, naturalHeight: 14 }, presentation: validPresentation, onError: error => loadErrors.push(error) });
await assert.rejects(loadFailureRenderer.ready(), error => error.code === "material-texture-load");
assert.equal(loadErrors[0].code, "material-texture-load");
fetchFailure = "";

decodeFailure = "micro-grain.webp";
const decodeFailureRenderer = createHolographicRenderer({ canvas: mockCanvas(), image: { complete: true, naturalWidth: 10, naturalHeight: 14 }, presentation: validPresentation });
await assert.rejects(decodeFailureRenderer.ready(), error => error.code === "material-texture-decode");
decodeFailure = "";

const uploadFailureRenderer = createHolographicRenderer({ canvas: mockCanvas(mockContext({ failMaterialUpload: true })), image: { complete: true, naturalWidth: 10, naturalHeight: 14 }, presentation: validPresentation });
await assert.rejects(uploadFailureRenderer.ready(), error => error.code === "material-texture-upload");

const disposedRenderer = createHolographicRenderer({ canvas: mockCanvas(), image: { complete: true, naturalWidth: 10, naturalHeight: 14 }, presentation: validPresentation });
disposedRenderer.dispose();
await assert.rejects(disposedRenderer.ready(), error => error.code === "renderer-disposed");

globalThis.fetch = originalFetch;
globalThis.Image = originalImage;
globalThis.createImageBitmap = originalCreateImageBitmap;
URL.createObjectURL = originalCreateObjectURL;
URL.revokeObjectURL = originalRevokeObjectURL;

console.log("WebGL2 engine contract tests passed");
