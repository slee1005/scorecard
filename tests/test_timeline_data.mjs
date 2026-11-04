import test from "node:test";
import assert from "node:assert/strict";
import {
  timePercent,
  timelineTicks,
  pointerTime,
  draggedStart,
  zoomScroll,
} from "../src/golf_video_studio/web/timeline-data.js";
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-7, `${a} != ${b}`);
test("ruler, markers and seek share the full-duration axis at every zoom and scroll", () => {
  for (const zoom of [1, 2, 4, 8])
    for (const duration of [20, 1216]) {
      const width = 640 * zoom;
      for (const scroll of [0, (width - 640) / 2, width - 640])
        for (const time of [0, 5, duration / 2, duration]) {
          const left = 15 - scroll,
            x = left + (timePercent(time, duration) / 100) * width;
          near(pointerTime(x, left, width, duration), time);
        }
    }
});
test("five-second events keep their exact duration on a twenty-minute video", () => {
  for (const zoom of [1, 2, 4, 8]) {
    const width = 640 * zoom;
    const span =
      ((timePercent(155, 1200) - timePercent(150, 1200)) / 100) * width;
    near(span, (5 / 1200) * width);
    near(pointerTime(span, 0, width, 1200), 5);
  }
});
test("zoom preserves the visible playhead position", () => {
  near(zoomScroll(640, 2560, 0, 640, 300, 1200), 480);
  near(zoomScroll(2560, 5120, 480, 640, 300, 1200), 1120);
  near(zoomScroll(5120, 640, 1120, 640, 300, 1200), 0);
});
test("zoom anchors the viewport center when the playhead is off screen", () => {
  near(zoomScroll(2560, 5120, 1000, 640, 0, 1200), 2320);
  near(zoomScroll(5120, 640, 2320, 640, 0, 1200), 0);
});
test("marker dragging includes scroll movement and clamps the complete interval", () => {
  near(draggedStart(150, 155, 32, 32, 5120, 1200), 165);
  near(draggedStart(150, 155, -100000, 0, 5120, 1200), 0);
  near(draggedStart(150, 155, 100000, 0, 5120, 1200), 1195);
  near(pointerTime(-100, 0, 5120, 1200), 0);
  near(pointerTime(6000, 0, 5120, 1200), 1200);
});
test("zoomed ruler adds exact ticks without duplicate or out-of-range times", () => {
  for (const duration of [20, 1216, 86400])
    for (const zoom of [1, 2, 4, 8]) {
      const ticks = timelineTicks(duration, zoom);
      assert.equal(ticks[0].time, 0);
      assert.equal(ticks.at(-1).time, duration);
      assert.equal(new Set(ticks.map((t) => t.time)).size, ticks.length);
      assert.ok(ticks.length <= 8 * zoom + 2);
      for (const tick of ticks) {
        assert.ok(tick.time >= 0 && tick.time <= duration);
        near(tick.percent, (tick.time / duration) * 100);
      }
    }
});
