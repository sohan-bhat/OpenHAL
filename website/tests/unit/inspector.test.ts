import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import data from "../../src/data/inspector-captures.json";
import { cropImages, cropSizes, cropSrcset, cropWidths, presentShots } from "../../src/lib/inspector-crops";
import { inspectorShots } from "../../src/lib/inspector-shots";
import { storyFacts } from "../../src/lib/story/facts";

const captures = fileURLToPath(new URL("../../public/captures/", import.meta.url));
const page = readFileSync(fileURLToPath(new URL("../../src/pages/inspector.astro", import.meta.url)), "utf8");
const files = readdirSync(captures).filter((name) => name.startsWith("inspector-"));
const shots = inspectorShots();

describe("Inspector captures", () => {
  it("come in both themes, as WebP, for every shot the page shows and no other", () => {
    const expected = shots.flatMap((shot) => ["light", "dark"].map((theme) => `${shot.file}-${theme}.webp`));
    expect(files.sort()).toEqual(expected.sort());
    for (const view of ["device", "log", "stopped"]) expect(shots.map((shot) => shot.file)).toContain(`inspector-${view}`);
  });

  it("stay under 600 KB together", () => {
    const total = files.reduce((sum, name) => sum + statSync(`${captures}${name}`).size, 0);
    expect(total).toBeLessThan(600 * 1024);
  });

  it("each crop inside its capture", () => {
    for (const { crop } of shots) {
      expect(crop.x + crop.w).toBeLessThanOrEqual(data.width);
      expect(crop.y + crop.h).toBeLessThanOrEqual(data.height);
    }
  });

  it("each say in their alt text what they show, with the record's numbers", () => {
    const facts = storyFacts();
    for (const list of [shots, inspectorShots(facts, [])]) {
      const alts = list.map((shot) => shot.alt);
      expect(alts.length).toBeGreaterThanOrEqual(3);
      for (const alt of alts) expect(alt.length).toBeGreaterThan(40);
      const all = alts.join(" ");
      for (const word of [facts.printer.name, facts.nozzle.refusal.name, facts.nozzle.value, facts.nozzle.max, facts.cancel.status, "STOPPED"]) expect(all).toContain(word);
    }
    expect(page).toContain("inspectorShots()");
  });

  it("are served as crops at the widths the page draws them, in AVIF and WebP, in both themes", () => {
    const images = cropImages(presentShots(shots));
    for (const shot of shots) {
      const widths = cropWidths(shot.crop);
      expect(widths[widths.length - 1]).toBe(shot.crop.w);
      expect(widths[0]).toBeGreaterThanOrEqual(Math.round(shot.crop.w * 0.85));
      for (const theme of ["light", "dark"]) {
        for (const format of ["avif", "webp"]) {
          for (const width of widths) expect(images.map((image) => image.name)).toContain(`${shot.file}-${theme}-${width}.${format}`);
        }
      }
      expect(cropSrcset(shot, "dark", "avif")).toBe(widths.map((width) => `/captures/${shot.file}-dark-${width}.avif ${width}w`).join(", "));
      expect(cropSizes(shot.crop)).toContain(`${shot.crop.w}px`);
    }
  });

  it("link the whole capture only from Open the whole screen", () => {
    const component = readFileSync(fileURLToPath(new URL("../../src/components/InspectorShots.astro", import.meta.url)), "utf8");
    expect(component).toContain("capturePath(item.file, \"light\")");
    expect(component).toContain('loading="lazy"');
    expect(component).toContain("width={item.crop.w}");
    expect(component).toContain("height={item.crop.h}");
  });
});
