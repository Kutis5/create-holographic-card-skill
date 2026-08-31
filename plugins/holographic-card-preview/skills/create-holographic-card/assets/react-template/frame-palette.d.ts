export interface FramePalette {
  readonly base: string;
  readonly highlight: string;
  readonly shadow: string;
}

export function paletteFromColor(color: string): FramePalette;
export function analyzeFramePixels(data: Uint8ClampedArray | Uint8Array | number[], width: number, height: number, fallbackColor?: string): FramePalette;
export function extractFramePalette(image: CanvasImageSource, fallbackColor?: string): FramePalette;
