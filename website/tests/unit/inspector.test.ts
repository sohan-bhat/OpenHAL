import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { inspectorShots } from "../../src/lib/inspector-shots";
import { storyFacts } from "../../src/lib/story/facts";

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

  it("each say in their alt text what they show, with the record's numbers", () => {
    const facts = storyFacts();
    const alts = inspectorShots(facts).map((shot) => shot.alt);
    expect(alts).toHaveLength(3);
    for (const alt of alts) expect(alt.length).toBeGreaterThan(40);
    const all = alts.join(" ");
    for (const word of [facts.printer.name, facts.nozzle.refusal.name, facts.nozzle.value, facts.nozzle.max, facts.cancel.status, "STOPPED"]) expect(all).toContain(word);
    expect(page).toContain("inspectorShots()");
  });
});
