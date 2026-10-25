// The docs navigation, built from the docs collection so new driver pages appear on their own.

import { getCollection } from "astro:content";
import { FIXED_ROUTES, groupFor, routeFor } from "./markdown/routes.mjs";

export interface NavItem {
  title: string;
  href: string;
  repo: string;
}

export interface NavGroup {
  name: string;
  items: NavItem[];
}

const GROUP_ORDER = ["Guides", "Interfaces", "Reference", "Drivers", "Firmware", "Spec"];

export async function docsNav(): Promise<NavGroup[]> {
  const groups = new Map<string, NavItem[]>();
  const entries = await getCollection("docs");
  const order = new Map(entries.map((entry, index) => [entry.id, index]));
  for (const entry of entries) {
    const href = routeFor(entry.id);
    if (!href) continue;
    const name = groupFor(entry.id);
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name)!.push({ title: navTitle(docTitle(entry)), href, repo: entry.id });
  }
  const fixed = FIXED_ROUTES.map((item) => item.repo);
  return GROUP_ORDER.filter((name) => groups.has(name)).map((name) => ({
    name,
    items: groups.get(name)!.sort((a, b) => rank(a.repo, fixed, order) - rank(b.repo, fixed, order)),
  }));
}

function rank(repo: string, fixed: string[], order: Map<string, number>): number {
  const index = fixed.indexOf(repo);
  return index === -1 ? 1000 + (order.get(repo) ?? 0) : index;
}

/** A document's title, its first level one heading, as remarkTitle takes it when rendering. */
export function docTitle(entry: { id: string; body?: string; data: Record<string, unknown> }): string {
  if (typeof entry.data.title === "string") return entry.data.title;
  const match = /^# (.+)$/m.exec(entry.body ?? "");
  return match ? match[1].replace(/`/g, "").trim() : entry.id;
}

/** Shorter titles for the sidebar. The page keeps the document's own heading. */
export function navTitle(title: string): string {
  return title
    .replace(/^OpenHAL device file specification, version /, "Spec ")
    .replace(/^Command line reference$/, "Command line")
    .replace(/^Python library$/, "Python library");
}
