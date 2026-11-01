import { describe, expect, it } from "vitest";
import { countLine, isFiltered, matches, readChoices, writeChoices } from "../../src/lib/catalog-filter";

const FIELDS = ["q", "tier", "status", "conformance", "hazard"];

describe("catalog filters in the address", () => {
  it("reads only the fields a page offers and leaves out empty ones", () => {
    expect(readChoices("?q=scpi&hazard=high&tier=&other=1", FIELDS)).toEqual({ q: "scpi", hazard: "high" });
    expect(readChoices("", FIELDS)).toEqual({});
  });

  it("writes the choices in the fields' order, and nothing when no filter is set", () => {
    expect(writeChoices({ hazard: "high", q: "power supply" }, FIELDS)).toBe("?q=power+supply&hazard=high");
    expect(writeChoices({ q: "", hazard: "" }, FIELDS)).toBe("");
  });

  it("reads back what it writes", () => {
    const choices = { q: "moonraker", tier: "2", conformance: "core" };
    expect(readChoices(writeChoices(choices, FIELDS), FIELDS)).toEqual(choices);
  });
});

describe("catalog filter matching", () => {
  const row = { text: "moonraker http klipper 3d printers", values: { tier: "2", status: "implemented", hazard: "high", conformance: "core" } };

  it("needs every word of the search somewhere in the row", () => {
    expect(matches(row, { q: "klipper print" })).toBe(true);
    expect(matches(row, { q: "klipper serial" })).toBe(false);
    expect(matches(row, { q: "KLIPPER" })).toBe(true);
  });

  it("needs the chosen value of every select", () => {
    expect(matches(row, { hazard: "high", tier: "2" })).toBe(true);
    expect(matches(row, { hazard: "low" })).toBe(false);
    expect(matches(row, { hazard: "" })).toBe(true);
  });

  it("never matches a status on a row without one, such as a reference driver", () => {
    expect(matches({ text: "memory", values: { tier: "0" } }, { status: "implemented" })).toBe(false);
  });
});

describe("the count line", () => {
  it("says the total alone until a filter is set", () => {
    expect(countLine(34, 34, "drivers", false)).toBe("34 drivers.");
    expect(countLine(3, 34, "drivers", true)).toBe("3 of 34 drivers.");
    expect(countLine(0, 12, "device files", true)).toBe("0 of 12 device files.");
    expect(isFiltered({ q: " " })).toBe(false);
  });
});
