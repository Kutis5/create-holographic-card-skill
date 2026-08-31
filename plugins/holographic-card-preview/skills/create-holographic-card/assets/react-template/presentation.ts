export type MaterialFamily = "clear-coat" | "pearl" | "brushed-metal" | "spectral-lines" | "etched-holo" | "cosmic-flake" | "star-holo";
export type TextureKind = "none" | "micro-grain" | "scanline" | "geometric" | "contour" | "sparse-flake";
export type EffectTarget = "background" | "surface" | "frame";
export type FrameColorMode = "fixed" | "image";

export interface CardPresentation {
  version: 2;
  frame: { style: "none" | "hairline" | "narrow" | "double"; width: number; color: string; colorMode?: FrameColorMode };
  radius: { outer: number; inner: number };
  surface: { color: string; accent: string; material: MaterialFamily };
  foil: { enabled: boolean; target: EffectTarget; colors: string[]; intensity: number };
  texture: { kind: TextureKind; target: EffectTarget; intensity: number };
  sparkle: { enabled: boolean; target: EffectTarget; intensity: number };
  glare: { enabled: boolean; target: EffectTarget; intensity: number };
  depth: { parallaxX: number; parallaxY: number; lift: number; shadowOpacity: number; shadowBlur: number; rimIntensity: number };
  motion: { maxX: number; maxY: number; scale: number; smoothing: number };
  constraints: { keepInsideFrame: true };
}

export const clearCoatPresentation: CardPresentation = {
  version: 2,
  frame: { style: "narrow", width: 0.65, color: "#75808f", colorMode: "fixed" },
  radius: { outer: 5.8, inner: 5.15 },
  surface: { color: "#070a0f", accent: "#a7d9e8", material: "clear-coat" },
  foil: { enabled: true, target: "background", colors: ["#ff5470", "#ffcc66", "#50e3c2", "#5cb8ff", "#8f7cff", "#ef7dff"], intensity: 0.78 },
  texture: { kind: "micro-grain", target: "background", intensity: 0.48 },
  sparkle: { enabled: false, target: "background", intensity: 0 },
  glare: { enabled: true, target: "surface", intensity: 0.62 },
  depth: { parallaxX: 1.45, parallaxY: 1.25, lift: 19, shadowOpacity: 0.18, shadowBlur: 16, rimIntensity: 0.12 },
  motion: { maxX: 14, maxY: 14, scale: 1.024, smoothing: 0.18 },
  constraints: { keepInsideFrame: true },
};
