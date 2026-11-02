import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as radix from "@radix-ui/colors";
import { converter } from "culori";
import { describe, expect, it } from "vitest";
import { FILES } from "../../scripts/palette.mjs";
import { contrasts, distances } from "../../src/lib/palette-checks.mjs";
import { palette, source, STEPS } from "../../src/lib/palette.mjs";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const toOklch = converter("oklch");
const oklch = (hex: string) => toOklch(hex) as { l: number; c: number; h: number };
const STATUS = ["ok", "confirm", "blocked"];

describe("the palette", () => {
  it("takes every color but the owner's status colors from a Radix Colors step as published", () => {
    for (const theme of ["light", "dark"] as const) {
      for (const token of Object.keys(STEPS)) {
        const from = source(token, theme);
        if (STATUS.includes(token)) {
          expect(from, token).toBe("owner");
          continue;
        }
        const [scale, step] = from.split(" ");
        const published = (radix as Record<string, Record<string, string>>)[scale][`${scale.replace(/Dark$/, "")}${step}`];
        expect(palette[theme][token as keyof typeof palette.light], `${theme} ${token}`).toBe(published.toLowerCase());
      }
    }
  });

  it("writes the same values into design/tokens.css, the D2 themes and scripts/diagrams.py", () => {
    for (const [path, make] of Object.entries(FILES)) {
      const file = readFileSync(`${root}${path}`, "utf8");
      expect(make(file), `${path} is stale, run node scripts/palette.mjs`).toBe(file);
    }
  });

  it("tints the near-black and the off-white with the faintest olive green and keeps the neutral warm, never blue", () => {
    for (const theme of ["light", "dark"] as const) {
      for (const token of ["bg", "surface"] as const) {
        const color = oklch(palette[theme][token]);
        expect(color.h, `${theme} ${token} hue`).toBeGreaterThan(110);
        expect(color.h, `${theme} ${token} hue`).toBeLessThan(160);
        expect(color.c, `${theme} ${token} chroma`).toBeLessThan(0.006);
      }
      const neutral = oklch(palette[theme].neutral);
      expect(neutral.h, `${theme} neutral hue`).toBeGreaterThan(60);
      expect(neutral.h, `${theme} neutral hue`).toBeLessThan(100);
    }
    expect(oklch(palette.dark.bg).l).toBeLessThan(0.2);
    expect(oklch(palette.light.bg).l).toBeGreaterThan(0.98);
  });

  it("passes WCAG AA for every pair in both themes", () => {
    for (const row of contrasts()) expect(row.ratio, `${row.theme} ${row.fg} on ${row.bg}`).toBeGreaterThanOrEqual(row.need);
  });

  it("keeps the status colors, the pink, the neutral and the page apart under protanopia, deuteranopia and tritanopia", () => {
    const rows = distances();
    const pair = (a: string, b: string) => rows.filter((row) => (row.a === a && row.b === b) || (row.a === b && row.b === a));
    for (const [a, b] of [
      ["ok", "confirm"],
      ["ok", "blocked"],
      ["confirm", "blocked"],
    ]) {
      for (const row of pair(a, b)) expect(row.delta, `${row.theme} ${row.vision} ${a} and ${b}`).toBeGreaterThanOrEqual(7);
    }
    for (const status of STATUS) for (const row of pair("accent", status)) expect(row.delta, `${row.theme} ${row.vision} pink and ${status}`).toBeGreaterThanOrEqual(5.6);
    for (const other of ["accent", "neutral", ...STATUS]) for (const row of pair("bg", other)) expect(row.delta, `${row.theme} ${row.vision} page and ${other}`).toBeGreaterThanOrEqual(30);
    for (const row of pair("neutral", "accent")) expect(row.delta, `${row.theme} ${row.vision} neutral and pink`).toBeGreaterThanOrEqual(15);
    for (const status of STATUS) for (const row of pair("neutral", status).filter((one) => one.vision === "normal")) expect(row.delta, `${row.theme} neutral and ${status}`).toBeGreaterThanOrEqual(15);
  });
});
