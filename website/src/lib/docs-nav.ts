import { getCollection } from "astro:content";
import type { SideGroup } from "./nav-types";
import { FIXED_ROUTES } from "./markdown/routes.mjs";

const DOC_GROUPS = ["Get started", "Tutorials", "Reference", "Firmware"];

const SHORT: Record<string, string> = {
  "OpenHAL device file specification, version 0.1": "Device file format",
  "Command line reference": "Command line",
  "MCP server": "MCP server",
  "Spec changelog": "Device file changelog",
  "Mapping to the Model Hardware Standard": "MHS mapping",
  "OpenHAL firmware protocol, version 1": "Firmware protocol",
};

export function docTitle(entry: { id: string; body?: string; data: Record<string, unknown> }): string {
  if (typeof entry.data.title === "string") return entry.data.title;
  const match = /^# (.+)$/m.exec(entry.body ?? "");
  return match ? match[1].replace(/`/g, "").trim() : entry.id;
}

export function navTitle(title: string): string {
  return SHORT[title] ?? title;
}

export async function docsSidebar(): Promise<SideGroup[]> {
  const entries = new Map((await getCollection("docs")).map((entry) => [entry.id, entry]));
  return DOC_GROUPS.map((name) => ({
    name,
    items: FIXED_ROUTES.filter((item) => item.group === name && entries.has(item.repo)).map((item) => ({
      title: navTitle(docTitle(entries.get(item.repo)!)),
      href: item.route,
    })),
  })).filter((group) => group.items.length > 0);
}
