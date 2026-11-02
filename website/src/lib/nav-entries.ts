import type { NavEntry } from "../components/islands/SidebarNav";

type RouteEntry = App.Locals["starlightRoute"]["sidebar"][number];

/** Starlight's route data for a section's pages, keeping only what the sidebar and the page sheet show. */
export function navEntries(list: RouteEntry[]): NavEntry[] {
  return list.map((entry) => {
    const badge = entry.badge ? { badge: entry.badge.text } : {};
    if (entry.type === "group") return { label: entry.label, entries: navEntries(entry.entries), ...(entry.collapsed ? { closed: true } : {}), ...badge };
    const attrs = Object.fromEntries(Object.entries(entry.attrs).filter((pair): pair is [string, string | number | boolean] => ["string", "number", "boolean"].includes(typeof pair[1])));
    return { label: entry.label, href: entry.href, ...(entry.isCurrent ? { current: true } : {}), ...badge, ...(Object.keys(attrs).length ? { attrs } : {}) };
  });
}
