import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseLibrary } from "../../src/lib/library";

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
    expect(entries.map((entry) => entry.slug)).toEqual(["broken-fan", "rigol-dp832"]);
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

  it("is empty when there are no files", () => {
    expect(parseLibrary({})).toEqual([]);
  });
});
