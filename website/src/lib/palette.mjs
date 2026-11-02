import * as radix from "@radix-ui/colors";

/**
 * The site's palette, built from Radix Colors 3 steps as published. The harmony is olive, the gray
 * with a faint military green, and gold, the calm khaki neutral beside it, with pink as the one
 * striking accent. The status colors stay the values the owner tuned on 2026-10-26 and 2026-11-01,
 * because Radix's step 11 for green, blue and tomato is brighter than the dulled green and red the
 * owner asked for. design/tokens.css, the D2 themes, Mermaid's theme, the social images and the
 * theme-color tags all take their values from here, and scripts/palette.mjs writes the files that
 * can't import it.
 */
export const STEPS = {
  bg: ["olive", 1],
  surface: ["olive", 3],
  border: ["olive", 6],
  text: ["olive", 12],
  "text-2": ["olive", 11],
  "scrollbar-thumb": ["olive", 9],
  neutral: ["gold", 11],
  highlight: ["gold", 4],
  accent: { light: ["pink", 11], dark: ["pinkDark", 11] },
  "accent-fill": { light: ["pinkDark", 11], dark: ["pinkDark", 11] },
  "accent-fill-hover": { light: ["pinkDark", 10], dark: ["pinkDark", 10] },
  "on-accent": { light: ["oliveDark", 1], dark: ["oliveDark", 1] },
  ok: { light: "#3c754f", dark: "#72b88e" },
  confirm: { light: "#1d5fb4", dark: "#7db2f0" },
  blocked: { light: "#a14034", dark: "#d57a72" },
  unverified: ["olive", 11],
  "blocked-fill": ["tomato", 3],
};

function spec(token, theme) {
  const entry = STEPS[token];
  if (Array.isArray(entry)) return theme === "dark" ? [`${entry[0]}Dark`, entry[1]] : entry;
  return entry[theme];
}

function hex(token, theme) {
  const found = spec(token, theme);
  if (typeof found === "string") return found;
  const [scale, step] = found;
  const value = radix[scale]?.[`${scale.replace(/Dark$/, "")}${step}`];
  if (!value) throw new Error(`Radix Colors has no ${scale} step ${step}`);
  return value.toLowerCase();
}

function resolve(theme) {
  return Object.fromEntries(Object.keys(STEPS).map((token) => [token, hex(token, theme)]));
}

/** The resolved hex values, by theme and token name. */
export const palette = { light: resolve("light"), dark: resolve("dark") };

/** Where a token's value comes from, such as "oliveDark 1", or "owner" for a status color. */
export function source(token, theme) {
  const found = spec(token, theme);
  return typeof found === "string" ? "owner" : `${found[0]} ${found[1]}`;
}
