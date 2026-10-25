import { describe, expect, it } from "vitest";
import catalog from "../../../drivers/catalog.json";
import groupData from "../../src/data/driver-groups.json";
import { driverGroups } from "../../src/lib/catalog";

describe("driver groups on the overview", () => {
  it("put every catalog driver in exactly one group", () => {
    const listed = groupData.groups.flatMap((group) => group.drivers);
    const names = catalog.drivers.map((driver) => driver.name).sort();
    expect([...listed].sort()).toEqual(names);
    expect(new Set(listed).size).toBe(listed.length);
  });

  it("name only drivers the catalog has", () => {
    const names = new Set(catalog.drivers.map((driver) => driver.name));
    for (const group of groupData.groups) for (const name of group.drivers) expect(names.has(name), name).toBe(true);
  });

  it("count honestly from the catalog", () => {
    for (const group of driverGroups()) {
      const statuses = group.drivers.map((driver) => driver.status);
      expect(group.tested).toBe(statuses.filter((status) => status === "implemented").length);
      expect(group.verified).toBe(statuses.filter((status) => status === "verified").length);
    }
  });
});
