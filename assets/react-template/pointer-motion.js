export const INTERACTION_FRAME_INTERVAL_MS = 1000 / 60;

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const fallbackRequestFrame = callback => {
  const timer = setTimeout(() => callback(performance.now()), 16);
  timer.unref?.();
  return timer;
};

/**
 * Coalesces pointer input into a single, stable 60 Hz visual clock. Both the
 * DOM transform and the WebGL material receive the same smoothed point.
 */
export function createPointerMotionController({ smoothing, getBounds, onFrame, requestFrame = globalThis.requestAnimationFrame?.bind(globalThis) || fallbackRequestFrame, cancelFrame = globalThis.cancelAnimationFrame?.bind(globalThis) || clearTimeout }) {
  let frame = 0;
  let lastFrameTime = 0;
  let hasFrameTime = false;
  let pointerActive = false;
  let pendingClientPoint = null;
  let current = { x: 50, y: 50 };
  let target = { ...current };
  let activeSmoothing = smoothing;

  const schedule = () => {
    if (!frame) frame = requestFrame(tick);
  };
  const updateTargetFromClient = () => {
    if (!pendingClientPoint) return;
    const bounds = getBounds();
    const { x, y } = pendingClientPoint;
    pendingClientPoint = null;
    if (!bounds || bounds.width <= 0 || bounds.height <= 0) return;
    target = {
      x: clamp((x - bounds.left) / bounds.width * 100, 0, 100),
      y: clamp((y - bounds.top) / bounds.height * 100, 0, 100),
    };
  };
  const tick = now => {
    frame = 0;
    updateTargetFromClient();
    if (!hasFrameTime || now - lastFrameTime >= INTERACTION_FRAME_INTERVAL_MS - 0.25) {
      const frameElapsed = hasFrameTime ? Math.min(50, now - lastFrameTime) : INTERACTION_FRAME_INTERVAL_MS;
      lastFrameTime = now;
      hasFrameTime = true;
      const duration = clamp(Number(activeSmoothing) || 0.18, 0.08, 0.4) * 180;
      const amount = 1 - Math.exp(-frameElapsed / duration);
      current = {
        x: current.x + (target.x - current.x) * amount,
        y: current.y + (target.y - current.y) * amount,
      };
      onFrame({ ...current }, now);
    }
    const settled = Math.abs(current.x - target.x) < 0.01 && Math.abs(current.y - target.y) < 0.01;
    if (pointerActive || pendingClientPoint || !settled) schedule();
    else hasFrameTime = false;
  };

  return {
    moveClient(x, y) {
      pendingClientPoint = { x, y };
      pointerActive = true;
      schedule();
    },
    setPoint(x, y) {
      target = { x: clamp(x, 0, 100), y: clamp(y, 0, 100) };
      pointerActive = false;
      schedule();
    },
    setSmoothing(value) {
      activeSmoothing = value;
    },
    release() {
      pointerActive = false;
      pendingClientPoint = null;
      lastFrameTime = 0;
      hasFrameTime = false;
      if (frame) cancelFrame(frame);
      frame = 0;
    },
    dispose() {
      this.release();
    },
  };
}
