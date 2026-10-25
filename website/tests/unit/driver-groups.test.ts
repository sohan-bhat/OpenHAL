import { describe, expect, it } from "vitest";
import catalog from "../../../drivers/catalog.json";
import groupData from "../../src/data/driver-groups.json";
import { deviceDrivers, driverCounts, driverGroups, referenceDrivers } from "../../src/lib/catalog";

const devices = catalog.drivers.filter((driver) => driver.tier >= 1);

describe("driver counts", () => {
  it("count as tested on simulator only the implemented drivers of tier 1 or higher", () => {
    const tested = catalog.drivers.filter((driver) => driver.status === "implemented" && driver.tier >= 1).length;
    expect(driverCounts().tested).toBe(tested);
  });

  it("leave the tier 0 reference driver out of every count", () => {
    expect(driverCounts().total).toBe(devices.length);
    expect(driverCounts().verified).toBe(devices.filter((driver) => driver.status === "verified").length);
    expect(driverCounts().planned).toBe(devices.filter((driver) => driver.status === "planned").length);
    expect(deviceDrivers().every((driver) => driver.tier >= 1)).toBe(true);
    expect(referenceDrivers().map((driver) => driver.name).sort()).toEqual(
      catalog.drivers.filter((driver) => driver.tier === 0).map((driver) => driver.name).sort(),
    );
    expect(driverCounts([...deviceDrivers(), ...referenceDrivers()])).toEqual(driverCounts());
  });
});

describe("driver groups on the overview", () => {
  it("put every device driver in exactly one group", () => {
    const listed = groupData.groups.flatMap((group) => group.drivers);
    expect([...listed].sort()).toEqual(devices.map((driver) => driver.name).sort());
    expect(new Set(listed).size).toBe(listed.length);
  });

  it("name only drivers the catalog has, and never the reference driver", () => {
    const names = new Set(devices.map((driver) => driver.name));
    for (const group of groupData.groups) for (const name of group.drivers) expect(names.has(name), name).toBe(true);
  });

  it("count honestly from the catalog", () => {
    for (const group of driverGroups()) {
      const statuses = group.drivers.map((driver) => driver.status);
      expect(group.tested).toBe(statuses.filter((status) => status === "implemented").length);
      expect(group.verified).toBe(statuses.filter((status) => status === "verified").length);
    }
    expect(driverGroups().reduce((sum, group) => sum + group.tested, 0)).toBe(driverCounts().tested);
  });
});
