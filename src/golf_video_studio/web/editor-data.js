// Color presets change colors only: positioning, timing and alpha remain personal.
export const THEMES = {
  broadcast: { background: "#101c26", color: "#ffffff", accent: "#29c4b5" },
  forest: { background: "#122d24", color: "#f4f8e8", accent: "#b6d87d" },
  ocean: { background: "#102d4a", color: "#f3f8ff", accent: "#60c9ff" },
  paper: { background: "#f3efe6", color: "#172a28", accent: "#127260" },
  crimson: { background: "#361b2b", color: "#fff4f3", accent: "#ff9c98" },
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
