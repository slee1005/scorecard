// Color presets change colors only: positioning, timing and alpha remain personal.
export const THEMES = {
  broadcast: { background: "#102c42", color: "#f6fbff", accent: "#34c6e5" },
  forest: { background: "#142f29", color: "#f6faed", accent: "#bbdf84" },
  ocean: { background: "#102d4a", color: "#f3f8ff", accent: "#60c9ff" },
  paper: { background: "#f5f1e8", color: "#20312d", accent: "#166b59" },
  crimson: { background: "#341d30", color: "#fff6f4", accent: "#fbb2a0" },
  midnight: { background: "#151d2b", color: "#f3f6fc", accent: "#bdcdf8" },
};
export function shotNumber(shots, shot) {
  return (
    shot.number ??
    shots
      .filter((s) => s.hole === shot.hole)
      .findIndex((s) => s.id === shot.id) + 1
  );
}
export function currentTheme(style) {
  return (
    Object.keys(THEMES).find((key) =>
      Object.entries(THEMES[key]).every(
        ([field, value]) => style[field]?.toLowerCase() === value,
      ),
    ) || "custom"
  );
}

export function recommendedGeometry(type, video) {
  const aspect =
    video?.width > 0 && video?.height > 0 ? video.width / video.height : 16 / 9;
  const shot = type === "shot" || type === "minimal";
  const ratio = shot ? 620 / 254 : type === "full" ? 688 / 430 : 688 / 292;
  const maxWidth = aspect < 1 ? 0.92 : shot ? 0.46 : 0.72;
  const maxHeight = shot ? 0.28 : type === "full" ? 0.56 : 0.35;
  const width = Math.min(maxWidth, (maxHeight * ratio) / aspect);
  const height = (width * aspect) / ratio;
  return { x: 0.04, y: shot ? 0.96 - height : 0.04, width, height };
}

export function scoreKind(hole) {
  if (hole.par == null || hole.score == null) return "";
  const delta = hole.score - hole.par;
  return delta <= -2
    ? "eagle"
    : delta === -1
      ? "birdie"
      : delta === 0
        ? "par"
        : delta === 1
          ? "bogey"
          : "double";
}
