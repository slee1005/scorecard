// Every timeline row uses the same full-duration content width, including after scrolling.
export function timePercent(time, duration) {
  return Math.max(0, Math.min(1, time / duration)) * 100;
}
export function timelineTicks(duration, zoom) {
  const target = duration / (8 * zoom);
  const steps = [
    0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600,
    7200, 14400,
  ];
  const step = steps.find((value) => value >= target) || duration;
  const values = Array.from(
    { length: Math.ceil(duration / step) },
    (_, i) => i * step,
  );
  values.push(duration);
  return values.map((time) => ({
    time,
    percent: timePercent(time, duration),
    fractional: step < 1,
  }));
}
export function pointerTime(clientX, contentLeft, contentWidth, duration) {
  return Math.max(
    0,
    Math.min(duration, ((clientX - contentLeft) / contentWidth) * duration),
  );
}
export function draggedStart(
  start,
  end,
  dx,
  scrollDelta,
  contentWidth,
  duration,
) {
  return Math.max(
    0,
    Math.min(
      duration - (end - start),
      start + ((dx + scrollDelta) / contentWidth) * duration,
    ),
  );
}
export function zoomScroll(
  oldWidth,
  newWidth,
  scrollLeft,
  viewportWidth,
  time,
  duration,
) {
  const head = (time / duration) * oldWidth - scrollLeft;
  const anchor = head >= 0 && head <= viewportWidth ? head : viewportWidth / 2;
  const fraction = (scrollLeft + anchor) / oldWidth;
  return Math.max(
    0,
    Math.min(newWidth - viewportWidth, fraction * newWidth - anchor),
  );
}
