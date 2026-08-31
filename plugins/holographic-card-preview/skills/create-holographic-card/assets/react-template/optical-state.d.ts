import type { CardPresentation } from "./presentation";

export const IDLE_REVEAL: number;
export function perceptualIntensity(value: number, kind?: "foil" | "texture" | "sparkle" | "glare"): number;
export function expandFoilColors(colors?: string[], accent?: string): string[];
export function idlePoint(elapsedMs: number): { x: number; y: number };
export function interactionReveal(x: number, y: number): number;
export function computeOpticalState(
  presentation: CardPresentation,
  x: number,
  y: number,
  recipe?: unknown,
): Record<string, number>;
