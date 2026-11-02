import { differenceCiede2000, filterDeficiencyDeuter, filterDeficiencyProt, filterDeficiencyTrit, wcagContrast } from "culori";
import { palette } from "./palette.mjs";

/** The pairs that carry text or marks, with the least contrast each needs (WCAG 2.2 AA). */
export const PAIRS = [
  ["text", "bg", 4.5],
  ["text", "surface", 4.5],
  ["text", "highlight", 4.5],
  ["text-2", "bg", 4.5],
  ["text-2", "surface", 4.5],
  ["text-2", "highlight", 4.5],
  ["neutral", "bg", 4.5],
  ["neutral", "surface", 4.5],
  ["neutral", "highlight", 4.5],
  ["accent", "bg", 3],
  ["accent", "surface", 3],
  ["accent", "highlight", 3],
  ["on-accent", "accent-fill", 4.5],
  ["on-accent", "accent-fill-hover", 4.5],
  ["ok", "bg", 4.5],
  ["ok", "surface", 4.5],
  ["confirm", "bg", 4.5],
  ["confirm", "surface", 4.5],
  ["blocked", "bg", 4.5],
  ["blocked", "surface", 4.5],
  ["unverified", "bg", 4.5],
  ["scrollbar-thumb", "bg", 3],
];

/**
 * Contrast of every pair in both themes, measured with culori's WCAG 2 formula.
 * @returns {Array<{ theme: string, fg: string, bg: string, need: number, ratio: number }>}
 */
export function contrasts() {
  return PAIRS.flatMap(([fg, bg, need]) =>
    ["light", "dark"].map((theme) => ({ theme, fg, bg, need, ratio: wcagContrast(palette[theme][fg], palette[theme][bg]) })),
  );
}

/** The colors whose distances matter under color vision deficiency. */
export const SEEN = ["accent", "neutral", "bg", "ok", "confirm", "blocked"];

const VISION = {
  normal: (color) => color,
  protanopia: filterDeficiencyProt(1),
  deuteranopia: filterDeficiencyDeuter(1),
  tritanopia: filterDeficiencyTrit(1),
};

const delta = differenceCiede2000();

/**
 * CIEDE2000 distance between every pair of SEEN, after culori's Machado 2009 simulation of each
 * dichromacy at full severity, in both themes.
 * @returns {Array<{ theme: string, vision: string, a: string, b: string, delta: number }>}
 */
export function distances() {
  /** @type {Array<{ theme: string, vision: string, a: string, b: string, delta: number }>} */
  const rows = [];
  for (const theme of ["light", "dark"]) {
    for (const [vision, simulate] of Object.entries(VISION)) {
      for (let i = 0; i < SEEN.length; i++) {
        for (let j = i + 1; j < SEEN.length; j++) {
          const [a, b] = [SEEN[i], SEEN[j]];
          rows.push({ theme, vision, a, b, delta: delta(simulate(palette[theme][a]), simulate(palette[theme][b])) });
        }
      }
    }
  }
  return rows;
}
