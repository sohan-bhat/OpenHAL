import { STATUS_ORDER, countBy, type Driver } from "./catalog";

export function catalogSentence(all: Driver[]): string {
  const counts = countBy(all, (driver) => driver.status);
  const parts = STATUS_ORDER.filter((status) => counts.has(status)).map((status) => `${counts.get(status)} ${status}`);
  const list = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}` : parts[0];
  const verified = counts.get("verified") ?? 0;
  const hardware = verified === 0 ? "None is verified on hardware yet." : `${verified} verified on real hardware.`;
  return `${list} in drivers/catalog.json. ${hardware}`;
}
