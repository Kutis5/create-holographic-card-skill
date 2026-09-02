import type { CardPresentation } from "./presentation";

export const MATERIAL_FAMILIES: readonly ["clear-coat", "pearl", "brushed-metal", "spectral-lines", "etched-holo", "cosmic-flake", "star-holo"];
export const TEXTURE_KINDS: readonly ["none", "micro-grain", "scanline", "geometric", "contour", "sparse-flake"];
export const NEUTRAL_REVEAL: 0.7;
export const MAX_DEVICE_PIXEL_RATIO: 2;
export const MOBILE_MAX_DEVICE_PIXEL_RATIO: 2;
export const MOBILE_MAX_CANVAS_PIXELS: 1600000;
export const IDLE_FRAME_INTERVAL_MS: number;
export const ACTIVE_FRAME_INTERVAL_MS: number;
export const MATERIAL_PROFILES: Readonly<Record<CardPresentation["surface"]["material"], {
  readonly family: CardPresentation["surface"]["material"];
  readonly rimFactor: number;
  readonly backgroundGlareFactor: number;
  readonly surfaceGlareFactor: number;
}>>;

export class HolographicRendererError extends Error {
  readonly code: string;
  constructor(code: string, message: string);
}

export interface HolographicRendererDiagnostics {
  frames: number;
  averageFrameMs: number;
  p95FrameMs: number;
  width: number;
  height: number;
  cssWidth: number;
  cssHeight: number;
  dpr: number;
  pixelArea: number;
  maxTextureSize: number;
  mobile: boolean;
  failed: boolean;
  ready: boolean;
  animationPending: boolean;
  mode: "idle" | "interactive" | "locked" | "external" | "release" | "reduced-motion" | "paused";
}

export interface HolographicRenderer {
  /** Resolves after the atlas and shared textures are decoded, uploaded, and the first frame is rendered. */
  ready(): Promise<void>;
  setPointer(x: number, y: number, immediate?: boolean): void;
  /** Render exactly one externally scheduled interaction frame. */
  renderPointerFrame(x: number, y: number, now?: number): void;
  releasePointer(): void;
  setPresentation(presentation: CardPresentation): void;
  setReducedMotion(value: boolean): void;
  setPaused(value: boolean): void;
  resize(): void;
  render(): void;
  diagnostics(): HolographicRendererDiagnostics;
  dispose(): void;
}

export function clampDevicePixelRatio(value: number, options?: { mobile?: boolean }): number;
export function interactionReveal(x: number, y: number): number;
export function buildFragmentShader(family: CardPresentation["surface"]["material"]): string;
export function createHolographicRenderer(options: {
  canvas: HTMLCanvasElement;
  image: HTMLImageElement;
  presentation: CardPresentation;
  mobile?: boolean;
  onError?: (error: Error) => void;
}): HolographicRenderer;
