import assert from "node:assert/strict";
import { createPointerMotionController, INTERACTION_FRAME_INTERVAL_MS } from "../assets/react-template/pointer-motion.js";

const queued = [];
let nextHandle = 1;
const cancelled = new Set();
const requestFrame = callback => {
  const handle = nextHandle++;
  queued.push({ handle, callback });
  return handle;
};
const cancelFrame = handle => cancelled.add(handle);
const runFrame = now => {
  const entry = queued.shift();
  assert.ok(entry, "expected a queued animation frame");
  if (!cancelled.has(entry.handle)) entry.callback(now);
};

const frames = [];
const controller = createPointerMotionController({
  smoothing: 0.18,
  getBounds: () => ({ left: 20, top: 40, width: 400, height: 560 }),
  onFrame: (point, now) => frames.push({ point, now }),
  requestFrame,
  cancelFrame,
});

for (let index = 0; index < 100; index += 1) controller.moveClient(20 + index * 4, 40 + index * 5.6);
assert.equal(queued.length, 1, "a pointer burst must queue exactly one frame");
runFrame(0);
assert.equal(frames.length, 1);
assert.ok(frames[0].point.x > 50 && frames[0].point.y > 50, "the final coalesced point must drive the first frame");

for (let now = 1000 / 120; now <= 1000; now += 1000 / 120) runFrame(now);
const intervals = frames.slice(1).map((frame, index) => frame.now - frames[index].now);
assert.ok(intervals.every(interval => interval >= INTERACTION_FRAME_INTERVAL_MS - 0.5), "120 Hz input must not schedule a 25 ms third-frame cadence");
assert.ok(intervals.every(interval => interval <= INTERACTION_FRAME_INTERVAL_MS * 2.1), "interaction updates must remain near 60 Hz");
assert.ok(Math.abs(frames.at(-1).point.x - 99) < 1, "the controller converges on the latest x coordinate");
assert.ok(Math.abs(frames.at(-1).point.y - 99) < 1, "the controller converges on the latest y coordinate");

const queuedBeforeRelease = queued.length;
controller.release();
assert.ok(cancelled.size > 0, "release cancels the pending animation frame");
assert.equal(queued.length, queuedBeforeRelease, "release does not queue a new frame");
controller.dispose();

console.log("Pointer motion controller tests passed");
