import catalog from "../../../drivers/catalog.json";
import groupData from "../data/driver-groups.json";

export interface Estimate {
  devices: string;
  reasoning: string;
  sources: string[];
}

export interface Driver {
  name: string;
  tier: number;
  status: string;
  protocols: string[];
  families: string[];
  hazard_default: string;
  tests: string;
  estimate: Estimate | null;
  conformance?: string;
}

export const STATUS_ORDER = ["verified", "implemented", "in progress", "stub", "planned"];

const WORDS: Record<string, string> = {
  verified: "verified on hardware",
  implemented: "tested on simulator",
  "in progress": "in progress",
  stub: "stub",
  planned: "planned",
};

export function statusWord(status: string): string {
  return WORDS[status] ?? status;
}

export function statusClass(status: string): "ok" | "unverified" | "planned" {
  if (status === "verified") return "ok";
  if (status === "planned") return "planned";
  return "unverified";
}

export function drivers(): Driver[] {
  return (catalog.drivers as Driver[]).slice().sort((a, b) => {
    const status = STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status);
    return status || a.tier - b.tier || a.name.localeCompare(b.name);
  });
}

export function isReference(driver: Driver): boolean {
  return driver.tier === 0;
}

export function deviceDrivers(): Driver[] {
  return drivers().filter((driver) => !isReference(driver));
}

export function referenceDrivers(): Driver[] {
  return drivers().filter(isReference);
}

export interface DriverCounts {
  total: number;
  tested: number;
  verified: number;
  planned: number;
}

export function driverCounts(list: Driver[] = deviceDrivers()): DriverCounts {
  const devices = list.filter((driver) => !isReference(driver));
  return {
    total: devices.length,
    tested: devices.filter((driver) => driver.status === "implemented").length,
    verified: devices.filter((driver) => driver.status === "verified").length,
    planned: devices.filter((driver) => driver.status === "planned").length,
  };
}

export const TIER_NAMES: Record<number, string> = {
  0: "Reference",
  1: "Tier 1",
  2: "Tier 2",
  3: "Tier 3",
};

export function conformanceOf(driver: Driver): string | null {
  return typeof driver.conformance === "string" && driver.conformance ? driver.conformance : null;
}

export interface DriverGroup {
  name: string;
  drivers: Driver[];
  tested: number;
  verified: number;
}

export function driverGroups(): DriverGroup[] {
  const byName = new Map(deviceDrivers().map((driver) => [driver.name, driver]));
  return groupData.groups
    .map((group) => {
      const members = group.drivers.map((name) => byName.get(name)).filter((driver): driver is Driver => driver !== undefined);
      const counts = driverCounts(members);
      return { name: group.name, drivers: members, tested: counts.tested, verified: counts.verified };
    })
    .filter((group) => group.drivers.length > 0);
}
