import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { CHART_FILES, CHART_SIZES, HOW_CHART, chartLead, pathText } from "../../src/lib/story/how";
import { REPO_ROOT } from "../../src/lib/spec-meta.mjs";

describe("How it works", () => {
  it("names every label of the chart, word for word", () => {
    expect([HOW_CHART.agent, HOW_CHART.request, HOW_CHART.hub, HOW_CHART.checks]).toEqual(["Agent", "request", "OpenHAL hub", "checks the device file"]);
    expect(HOW_CHART.paths.map((path) => [path.label, ...path.values, ...path.outcomes])).toEqual([
      ["Under the limit", "shoulder to 20°", "limit 30°", "Arm moves"],
      ["Over the limit", "shoulder to 45°", "limit 30°", "Blocked"],
      ["Needs approval", "turn motors on", "You approve", "Arm moves"],
    ]);
  });

  it("reads the three paths as plain sentences", () => {
    expect(chartLead()).toBe("Agent sends a request, and the OpenHAL hub checks the device file.");
    expect(HOW_CHART.paths.map(pathText)).toEqual([
      "Under the limit, shoulder to 20°, limit 30°. Arm moves.",
      "Over the limit, shoulder to 45°, limit 30°. Blocked.",
      "Needs approval, turn motors on. You approve, then Arm moves.",
    ]);
  });

  it("ships each image as a 2x export of its shape's size", () => {
    for (const name of CHART_FILES) {
      const png = readFileSync(join(REPO_ROOT, "docs", "assets", name));
      expect(png.subarray(1, 4).toString("latin1"), name).toBe("PNG");
      const size = CHART_SIZES[name.includes("wide") ? "wide" : "narrow"];
      expect([png.readUInt32BE(16), png.readUInt32BE(20)], name).toEqual([size.width * 2, size.height * 2]);
    }
  });
});
