// The playground validates against spec/schema/device-file.schema.json after expanding shorthands,
// as the Python models do. Every spec example must pass, and broken files must fail with a path.

import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { deviceProblems } from "../../src/lib/playground/validate";

const examples = fileURLToPath(new URL("../../../spec/examples/", import.meta.url));

describe("spec examples pass the schema and the model checks", () => {
  for (const name of readdirSync(examples)) {
    it(name, () => {
      const result = deviceProblems(readFileSync(`${examples}${name}`, "utf8"));
      expect(result.problems).toEqual([]);
      expect(result.file).not.toBeNull();
    });
  }
});

describe("broken files are reported with their place", () => {
  it("a missing max", () => {
    const result = deviceProblems("device: Fan\nconnect: { mock: fan }\nwrite:\n  speed: { unit: percent, min: 0 }\n");
    expect(result.file).toBeNull();
    expect(result.problems.map((p) => p.message).join(" ")).toContain("Number values need both min and max.");
  });

  it("an unknown key", () => {
    const result = deviceProblems("device: Fan\nconnect: { mock: fan }\nspeed: 3\n");
    expect(result.problems[0].where).toBe("file");
    expect(result.problems[0].source).toBe("schema");
  });

  it("a YAML alias", () => {
    const result = deviceProblems("device: &a Fan\nconnect: { mock: fan }\nnotes: *a\n");
    expect(result.problems[0].message).toContain("not allowed");
  });

  it("an unknown unit", () => {
    const result = deviceProblems("device: Fan\nconnect: { mock: fan }\nwrite:\n  speed: { unit: blorp, min: 0, max: 1 }\n");
    expect(result.problems.map((p) => p.message).join(" ")).toContain("Unknown unit 'blorp'.");
  });
});
