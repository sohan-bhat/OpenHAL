import { getCollection } from "astro:content";
import { routeFor } from "./markdown/routes.mjs";
import { libraryEntries } from "./library";
import { showDrafts } from "./drafts";
import { docTitle } from "./docs-nav";
import { specVersions } from "./spec-versions";

export const HOME_TITLE = "AI agents drive real hardware. People set the limits.";

export interface PageInfo {
  path: string;
  title: string;
  kind: string;
}

export function ogPath(pathname: string): string {
  const slug = pathname.replace(/^\/+|\/+$/g, "");
  return `/og/${slug || "index"}.png`;
}

export function ogSlug(pathname: string): string {
  return pathname.replace(/^\/+|\/+$/g, "") || "index";
}

export async function allPages(): Promise<PageInfo[]> {
  const pages: PageInfo[] = [
    { path: "/", title: HOME_TITLE, kind: "OpenHAL" },
    { path: "/playground/", title: "Device file playground", kind: "Playground" },
    { path: "/devices/", title: "Supported devices", kind: "Devices" },
    { path: "/library/", title: "Device library", kind: "Library" },
    { path: "/docs/", title: "Documentation", kind: "Docs" },
    { path: "/blog/", title: "Blog", kind: "Blog" },
    { path: "/404/", title: "Page not found", kind: "OpenHAL" },
  ];
  for (const entry of await getCollection("docs")) {
    const route = routeFor(entry.id);
    if (!route) continue;
    const title = docTitle(entry);
    pages.push({ path: route, title, kind: route.startsWith("/spec/") ? "Spec" : "Docs" });
  }
  const spec = pages.find((page) => page.path === "/spec/");
  if (spec) {
    for (const version of specVersions()) {
      pages.push({ path: `/spec/${version.version}/`, title: spec.title, kind: "Spec" });
    }
  }
  for (const post of await getCollection("blog")) {
    if (post.data.draft && !showDrafts()) continue;
    pages.push({ path: `/blog/${post.id}/`, title: post.data.title, kind: "Blog" });
  }
  for (const entry of libraryEntries()) {
    pages.push({ path: `/library/${entry.slug}/`, title: entry.title, kind: "Library" });
  }
  const seen = new Set<string>();
  return pages.filter((page) => !seen.has(page.path) && seen.add(page.path));
}
