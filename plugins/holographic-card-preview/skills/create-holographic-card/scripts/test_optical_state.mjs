import assert from "node:assert/strict";
import {
  IDLE_REVEAL,
  computeOpticalState,
  expandFoilColors,
  idlePoint,
  interactionReveal,
  perceptualIntensity,
} from "../assets/react-template/optical-state.js";

function saturation(hex) {
  const value = Number.parseInt(hex.slice(1), 16);
  const channels = [(value >> 16) & 255, (value >> 8) & 255, value & 255].map((channel) => channel / 255);
  const max = Math.max(...channels);
  const min = Math.min(...channels);
  const lightness = (max + min) / 2;
  return max === min ? 0 : (max - min) / (1 - Math.abs(2 * lightness - 1));
}

assert.equal(IDLE_REVEAL, 0.7);
assert.equal(expandFoilColors(["#ff0000", "#00ff00", "#0000ff"]).length, 6);
assert.equal(expandFoilColors(["#112233", "#223344", "#334455", "#445566", "#556677", "#667788", "#ffffff"])[5], "#667788");
const silver = expandFoilColors(["#bfc1c4"]);
assert.equal(silver.length, 6);
assert.ok(new Set(silver).size >= 5);
assert.ok(silver.every((color) => saturation(color) <= 0.2), "neutral palettes must not become rainbow spectra");
const silverPair = expandFoilColors(["#c6c2bd", "#bcc5ca"]);
assert.equal(silverPair.length, 6);
assert.ok(silverPair.every((color) => saturation(color) <= 0.2));
const spectrum = expandFoilColors(["#ff4c67"]);
assert.ok(spectrum.some((color) => saturation(color) > 0.5), "color palettes retain the flagship spectrum expansion");
const suppliedSix = ["#b7bcc3", "#d6d8d8", "#aeb5bd", "#e5e1da", "#c2c8cd", "#929aa4"];
assert.deepEqual(expandFoilColors(suppliedSix), suppliedSix);
assert.equal(perceptualIntensity(0), 0);
assert.ok(perceptualIntensity(0.18, "foil") > 0.55, "legacy foil must remain visibly reflective");
assert.ok(perceptualIntensity(0.78, "foil") > 0.95);
assert.equal(interactionReveal(0, 0), IDLE_REVEAL);
assert.ok(interactionReveal(1, 1) > 0.99);

const idleA = idlePoint(0);
const idleB = idlePoint(2750);
assert.notDeepEqual(idleA, idleB);
assert.ok(Math.abs(idleA.x) <= 1 && Math.abs(idleA.y) <= 1);

const state = computeOpticalState({
  foil: { enabled: true, intensity: 0.18 },
  texture: { enabled: true, intensity: 0.12 },
  sparkle: { enabled: true, intensity: 0.08 },
  glare: { enabled: true, intensity: 0.15 },
  motion: { maxX: 9, maxY: 7, scale: 1.01 },
}, 0.5, -0.25);
assert.equal(state.rotateY, 5.5, "legacy motion is promoted to flagship amplitude");
assert.equal(state.rotateX, 2.75);
assert.ok(state.foilOpacity > 0.4);
assert.ok(state.glareOpacity > 0.25);
assert.notEqual(state.foilX, state.stripeX, "optical layers must move at independent rates");

const disabled = computeOpticalState({
  foil: { enabled: false, intensity: 1 },
  texture: { enabled: false, intensity: 1 },
  sparkle: { enabled: false, intensity: 1 },
  glare: { enabled: false, intensity: 1 },
}, 0, 0);
assert.equal(disabled.foilOpacity, 0);
assert.equal(disabled.textureOpacity, 0);
assert.equal(disabled.sparkleOpacity, 0);
assert.equal(disabled.glareOpacity, 0);

console.log("optical-state tests passed");
