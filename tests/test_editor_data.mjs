import test from "node:test";
import assert from "node:assert/strict";
import {
  shotNumber,
  currentTheme,
  THEMES,
} from "../src/golf_video_studio/web/editor-data.js";

test("manual shot number survives reorder; blank restores auto", () => {
  const a = { id: "a", hole: 1 },
    b = { id: "b", hole: 1, number: 7 },
    c = { id: "c", hole: 2 };
  assert.equal(shotNumber([a, b, c], b), 7);
  assert.equal(shotNumber([b, a, c], b), 7);
  assert.equal(shotNumber([a, b, c], c), 1);
  b.number = null;
  assert.equal(shotNumber([a, b, c], b), 2);
});
test("themes only replace colors and preserve user alpha/position", () => {
  const style = {
    ...THEMES.broadcast,
    overlay_opacity: 0.45,
    opacity: 0.6,
    x: 0.2,
  };
  Object.assign(style, THEMES.forest);
  assert.equal(currentTheme(style), "forest");
  assert.equal(style.overlay_opacity, 0.45);
  assert.equal(style.opacity, 0.6);
  assert.equal(style.x, 0.2);
  style.accent = "#abcdef";
  assert.equal(currentTheme(style), "custom");
});

import {
  recommendedGeometry,
  scoreKind,
} from "../src/golf_video_studio/web/editor-data.js";
test("recommended layouts preserve design aspect and keep simultaneous shot/card apart", () => {
  for (const video of [
    { width: 1920, height: 1080 },
    { width: 1080, height: 1920 },
    { width: 3840, height: 1600 },
  ]) {
    const shot = recommendedGeometry("shot", video),
      card = recommendedGeometry("full", video);
    for (const [type, geometry] of [
      ["shot", shot],
      ["full", card],
      ["front", recommendedGeometry("front", video)],
    ]) {
      assert.ok(geometry.x >= 0 && geometry.y >= 0);
      assert.ok(
        geometry.x + geometry.width <= 1 && geometry.y + geometry.height <= 1,
      );
      const target =
        type === "shot" ? 620 / 254 : type === "full" ? 688 / 430 : 688 / 292;
      assert.ok(
        Math.abs(
          (geometry.width * video.width) / (geometry.height * video.height) -
            target,
        ) < 0.00001,
      );
    }
    assert.ok(card.y + card.height < shot.y);
  }
});
test("score editor marks unknown, single and double relative scores consistently", () => {
  assert.equal(scoreKind({ par: 4, score: null }), "");
  for (const [score, kind] of [
    [1, "eagle"],
    [2, "eagle"],
    [3, "birdie"],
    [4, "par"],
    [5, "bogey"],
    [6, "double"],
    [10, "double"],
  ])
    assert.equal(scoreKind({ par: 4, score }), kind);
});
