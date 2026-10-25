import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const captures = fileURLToPath(new URL("../../public/captures/", import.meta.url));
const page = readFileSync(fileURLToPath(new URL("../../src/pages/inspector.astro", import.meta.url)), "utf8");
const files = readdirSync(captures).filter((name) => name.startsWith("inspector-"));

describe("Inspector captures", () => {
  it("cover the device, the message log and the stop in both themes, as WebP", () => {
    const expected = ["device", "log", "stopped"].flatMap((view) => ["light", "dark"].map((theme) => `inspector-${view}-${theme}.webp`));
    expect(files.sort()).toEqual(expected.sort());
  });

  it("stay under 600 KB together", () => {
    const total = files.reduce((sum, name) => sum + statSync(`${captures}${name}`).size, 0);
    expect(total).toBeLessThan(600 * 1024);
  });

  it("each say in their alt text what they show", () => {
    const alts = [...page.matchAll(/alt: "([^"]+)"/g)].map((match) => match[1]);
    expect(alts).toHaveLength(3);
    for (const alt of alts) expect(alt.length).toBeGreaterThan(40);
    expect(alts.join(" ")).toContain("LIMIT_EXCEEDED");
    expect(alts.join(" ")).toContain("INTERLOCK_BLOCKED");
  });
});
