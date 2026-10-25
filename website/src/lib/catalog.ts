// The driver catalog, imported from drivers/catalog.json at build time. The file grows as driver
// workstreams merge, so nothing here names a driver.

import catalog from "../../../drivers/catalog.json";

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
}

export const STATUS_ORDER = ["verified", "implemented", "in progress", "stub", "planned"];

export function drivers(): Driver[] {
  return (catalog.drivers as Driver[]).slice().sort((a, b) => {
    const status = STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status);
    return status || a.tier - b.tier || a.name.localeCompare(b.name);
  });
}

export function countBy<T extends string | number>(items: Driver[], key: (driver: Driver) => T): Map<T, number> {
  const counts = new Map<T, number>();
  for (const item of items) counts.set(key(item), (counts.get(key(item)) ?? 0) + 1);
  return counts;
}

/** Which lamp a status gets. Verified and implemented run, the rest don't yet. */
export function statusLamp(status: string): "ok" | "warning" | "unverified" {
  if (status === "verified" || status === "implemented") return "ok";
  if (status === "in progress" || status === "stub") return "warning";
  return "unverified";
}

export const TIER_NAMES: Record<number, string> = {
  0: "Reference",
  1: "Tier 1",
  2: "Tier 2",
  3: "Tier 3",
};
