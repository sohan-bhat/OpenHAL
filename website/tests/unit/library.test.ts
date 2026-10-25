import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { convert, parseQuantity } from "../../src/lib/kernel";
import { libraryEntries, parseLibrary } from "../../src/lib/library";

const fixtures = fileURLToPath(new URL("../fixtures/library/", import.meta.url));

function read(dir: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) Object.assign(out, read(path));
    else out[`library/${relative(fixtures, path)}`] = readFileSync(path, "utf8");
  }
  return out;
}

describe("device library", () => {
  const entries = parseLibrary(read(fixtures));

  it("lists every file, sorted by title", () => {
    expect(entries.map((entry) => entry.slug)).toEqual(["esphome-air", "broken-fan", "broken-units", "scpi-meter", "rigol-dp832", "scpi-supply"]);
  });

  it("reads identity, badges and channels", () => {
    const psu = entries.find((entry) => entry.slug === "rigol-dp832")!;
    expect(psu.title).toBe("Rigol DP832");
    expect(psu.verification).toBe("verified-on-hardware");
    expect(psu.report).toBe("reports/dp832.md");
    expect(psu.confirmed).toBe(true);
    expect(psu.hazard).toBe("medium");
    expect([psu.reads, psu.writes, psu.actions]).toEqual([1, 1, 0]);
    expect(psu.match).toEqual(["usb 1ab1:0e11"]);
  });

  it("keeps a broken file with its problem", () => {
    const broken = entries.find((entry) => entry.slug === "broken-fan")!;
    expect(broken.file).toBeNull();
    expect(broken.problems.join(" ")).toContain("is above max");
  });

  it("reads ppm and lux channels", () => {
    const air = entries.find((entry) => entry.slug === "esphome-air")!;
    expect(air.problems).toEqual([]);
    expect(air.reads).toBe(2);
    expect(convert(parseQuantity("400 ppm"), "percent")).toBeCloseTo(0.04);
    expect(convert(parseQuantity("1 klx"), "lux")).toBe(1000);
  });

  it("keeps a file with an unknown unit as a problem instead of failing", () => {
    const odd = entries.find((entry) => entry.slug === "broken-units")!;
    expect(odd.file).toBeNull();
    expect(odd.problems.join(" ")).toContain("Unknown unit 'blorp'");
  });

  it("never calls a file confirmed when no person confirmed it", () => {
    const meter = entries.find((entry) => entry.slug === "scpi-meter")!;
    expect(meter.confirmed).toBe(false);
    expect(meter.suggested).toEqual([]);
    const supply = entries.find((entry) => entry.slug === "scpi-supply")!;
    expect(supply.confirmed).toBe(false);
    expect(supply.suggested).toEqual(["ch1_output", "set_ch1 (action)"]);
  });

  it("parses every file of the starter library", () => {
    const library = libraryEntries();
    expect(library.length).toBeGreaterThan(30);
    expect(library.filter((entry) => entry.problems.length)).toEqual([]);
    expect(library.filter((entry) => entry.confirmed).map((entry) => entry.slug)).toEqual([]);
    const supply = library.find((entry) => entry.deviceId === "rigol-dp832")!;
    expect(supply.suggested).toContain("set_ch1 (action)");
  });

  it("is empty when there are no files", () => {
    expect(parseLibrary({})).toEqual([]);
  });
});
