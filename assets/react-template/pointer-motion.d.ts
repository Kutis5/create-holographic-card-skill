export const INTERACTION_FRAME_INTERVAL_MS: number;

export interface PointerMotionController {
  moveClient(x: number, y: number): void;
  setPoint(x: number, y: number): void;
  setSmoothing(value: number): void;
  release(): void;
  dispose(): void;
}

export function createPointerMotionController(options: {
  smoothing: number;
  getBounds(): DOMRect | { left: number; top: number; width: number; height: number } | null;
  onFrame(point: { x: number; y: number }, now: number): void;
  requestFrame?: (callback: FrameRequestCallback) => number;
  cancelFrame?: (handle: number) => void;
}): PointerMotionController;
