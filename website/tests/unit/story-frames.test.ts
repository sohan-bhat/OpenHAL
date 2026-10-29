import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { IDS } from "../../src/lib/story/facts";
import { FRAMES } from "../../src/lib/story/frames";
import { SCENARIO_PATH, scenarioFrom } from "../../src/lib/scenario-data.mjs";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const python = readFileSync(`${root}openhal/demo/frames.py`, "utf8");
const record = scenarioFrom(readFileSync(`${root}${SCENARIO_PATH}`, "utf8")).record as { exchanges: Array<{ id: string; frame?: string }> };

function body(name: string): string {
  const start = python.indexOf(`def ${name}(`);
  const end = python.indexOf("\ndef ", start + 1);
  return python.slice(start, end < 0 ? undefined : end);
}

const points = (code: string) =>
  [...code.replace(/_strand\([^)]*\)/g, "").replace(/for \w+ in \([^)]*\)/g, "").matchAll(/\((\d+), (\d+)\)/g)].map((match) => `${match[1]} ${match[2]}`);
const drawn = (frame: (typeof FRAMES)[keyof typeof FRAMES]) => frame.items.map((item) => item.d).join(" ");

describe("the webcam frames on the example page", () => {
  it("are the two frames the record reads, in its order", () => {
    const look = record.exchanges.find((exchange) => exchange.id === IDS.look)!;
    const loose = record.exchanges.find((exchange) => exchange.id === IDS.loose)!;
    expect(look.frame).toMatch(/first-layer\.jpg$/);
    expect(loose.frame).toMatch(/come-loose\.jpg$/);
    expect(python).toMatch(/NAMES: Final = \("first-layer", "come-loose"\)/);
  });

  it("draw every point openhal/demo/frames.py draws", () => {
    const bed = points(body("_bed"));
    for (const point of [...bed, ...points(body("_first_layer"))]) expect(drawn(FRAMES.lifting)).toContain(point);
    for (const point of [...bed, ...points(body("_come_loose"))]) expect(drawn(FRAMES.loose)).toContain(point);
  });

  it("put the toolhead where the demo frames put it", () => {
    const nozzles = [...python.matchAll(/_toolhead\(image, \((\d+), (\d+)\)\)|nozzle = \((\d+), (\d+)\)/g)].map((match) => `${match[1] ?? match[3]} ${match[2] ?? match[4]}`);
    expect(drawn(FRAMES.lifting)).toContain(nozzles[0]);
    expect(drawn(FRAMES.loose)).toContain(nozzles[1]);
  });

  it("draw the print as it started from the first frame's own points, with the corner flat and nothing marked", () => {
    const flat = drawn(FRAMES.printing);
    for (const point of points(body("_bed"))) expect(flat).toContain(point);
    for (const point of ["214 372", "232 332", "400 332", "214 377", "428 377"]) {
      expect(drawn(FRAMES.lifting)).toContain(point);
      expect(flat).toContain(point);
    }
    expect(flat).toContain("428 372");
    expect(flat).not.toContain("438 324");
    expect(flat).toContain("262 326");
    expect(FRAMES.printing.items.filter((item) => item.seen)).toEqual([]);
  });

  it("are line drawings that fill a shape only with the page's background, to hide what is behind the shape", () => {
    for (const frame of Object.values(FRAMES)) for (const item of frame.items) expect(["none", "bg"]).toContain(item.fill);
  });

  it("mark the lifted corner and the loose print as what the agent notices, and never the toolhead or the bed", () => {
    const seen = (frame: (typeof FRAMES)[keyof typeof FRAMES]) => frame.items.filter((item) => item.seen).map((item) => item.d).join(" ");
    const corner = points(body("_first_layer")).filter((point) => seen(FRAMES.lifting).includes(point));
    expect(corner.length).toBeGreaterThan(0);
    for (const point of points(body("_bed"))) {
      expect(seen(FRAMES.lifting)).not.toContain(point);
      expect(seen(FRAMES.loose)).not.toContain(point);
    }
    expect(FRAMES.loose.items.filter((item) => item.seen).length).toBeGreaterThan(FRAMES.lifting.items.filter((item) => item.seen).length);
    for (const frame of Object.values(FRAMES)) expect(frame.items.filter((item) => item.fill === "bg" && !item.seen).length).toBe(3);
  });
});
