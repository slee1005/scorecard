// Remaining distance is persisted in yards; Putter entry/display is in feet.
export function remainingFactor(club?: string) {
  return club === "Putter" ? 3 : 1;
}
export function displayRemaining(shot: {
  club?: string;
  remaining?: number | null;
}) {
  return shot.remaining == null
    ? null
    : shot.club === "Putter"
      ? Math.round(shot.remaining * 3 * 1e6) / 1e6
      : shot.remaining;
}
export function remainingToYards(value: number | null, factor: number) {
  return value == null ? null : value / (factor === 3 ? 3 : 1);
}
