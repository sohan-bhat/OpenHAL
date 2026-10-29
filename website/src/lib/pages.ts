import { getCollection } from "astro:content";
import { PITCH } from "../config/brand";
import { drivers } from "./catalog";
import { docTitle } from "./docs-nav";
import { showDrafts } from "./drafts";
import { libraryEntries } from "./library";
import { routeFor } from "./markdown/routes.mjs";
import { specPages } from "./spec";
import { versionLabel } from "./spec-meta.mjs";

export interface PageInfo {
  path: string;
  title: string;
  kind: string;
}

export const HOME_TITLE = PITCH;

export function ogPath(pathname: string): string {
  const slug = pathname.replace(/^\/+|\/+$/g, "");
  return `/og/${slug || "index"}.png`;
}

export function ogSlug(pathname: string): string {
  return pathname.replace(/^\/+|\/+$/g, "") || "index";
}

export async function allPages(): Promise<PageInfo[]> {
  const pages: PageInfo[] = [
    { path: "/", title: HOME_TITLE, kind: "Overview" },
    { path: "/docs/", title: "Documentation", kind: "Docs" },
    { path: "/spec/", title: "Specification", kind: "Specification" },
    { path: "/spec/playground/", title: "Playground", kind: "Specification" },
    { path: "/drivers/", title: "Drivers", kind: "Drivers" },
    { path: "/library/", title: "Device Library", kind: "Device Library" },
    { path: "/sdks/", title: "SDKs", kind: "SDKs" },
    { path: "/sdks/python/reference/", title: "Python API reference", kind: "SDKs" },
    { path: "/sdks/typescript/", title: "TypeScript SDK", kind: "SDKs" },
    { path: "/inspector/", title: "Inspector", kind: "Inspector" },
    { path: "/blog/", title: "Blog", kind: "Blog" },
    { path: "/404/", title: "Page not found", kind: "Overview" },
  ];
  for (const entry of await getCollection("repo")) {
    const route = routeFor(entry.id);
    if (!route || route.startsWith("/drivers/") && !route.endsWith("coverage/")) continue;
    pages.push({ path: route, title: docTitle(entry), kind: route.startsWith("/sdks/") ? "SDKs" : route.startsWith("/drivers/") ? "Drivers" : "Docs" });
  }
  for (const page of await specPages()) {
    pages.push({ path: page.href, title: page.title, kind: `Specification ${versionLabel(page.version)}` });
  }
  for (const driver of drivers()) {
    pages.push({ path: `/drivers/${driver.name}/`, title: driver.name, kind: "Drivers" });
  }
  for (const post of await getCollection("blog")) {
    if (post.data.draft && !showDrafts()) continue;
    pages.push({ path: `/blog/${post.id}/`, title: post.data.title, kind: "Blog" });
  }
  for (const entry of libraryEntries()) {
    pages.push({ path: `/library/${entry.slug}/`, title: entry.title, kind: "Device Library" });
  }
  const seen = new Set<string>();
  return pages.filter((page) => !seen.has(page.path) && seen.add(page.path));
}
