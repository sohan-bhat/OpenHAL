import { type CollectionEntry, getCollection } from "astro:content";
import { docTitle } from "./docs-nav";
import { orderPages, readVersions, slugOf } from "./spec-meta.mjs";

export interface SpecPage {
  version: string;
  path: string;
  slug: string;
  href: string;
  title: string;
  number: string;
  depth: number;
  repo: string;
  entry: CollectionEntry<"spec">;
}

export function numberPages(paths: string[]): Map<string, { number: string; depth: number }> {
  const out = new Map<string, { number: string; depth: number }>();
  let top = 0;
  let sub = 0;
  let current = "";
  for (const path of orderPages(paths)) {
    const parts = path.split("/");
    const head = parts.length > 1 ? parts[0] : path;
    const isIndex = parts.length > 1 && /^(index|overview|readme)\.md$/i.test(parts[parts.length - 1]);
    if (head !== current || parts.length === 1) {
      top += 1;
      sub = 0;
      current = head;
      if (parts.length === 1 || isIndex) {
        out.set(path, { number: `${top}`, depth: 1 });
        continue;
      }
    }
    if (isIndex) {
      out.set(path, { number: `${top}`, depth: 1 });
      continue;
    }
    sub += 1;
    out.set(path, { number: `${top}.${sub}`, depth: 2 });
  }
  return out;
}

export async function specPages(version?: string): Promise<SpecPage[]> {
  const { versions } = readVersions();
  const wanted = version ? [version] : versions.map((item) => item.version);
  const entries = await getCollection("spec");
  const pages: SpecPage[] = [];
  for (const ver of wanted) {
    const mine = entries.filter((entry) => entry.id.startsWith(`spec/${ver}/`));
    const paths = mine.map((entry) => entry.id.slice(`spec/${ver}/`.length));
    const numbers = numberPages(paths);
    for (const path of orderPages(paths)) {
      const entry = mine.find((item) => item.id === `spec/${ver}/${path}`)!;
      const slug = slugOf(path);
      const meta = numbers.get(path) ?? { number: "", depth: 1 };
      pages.push({
        version: ver,
        path,
        slug,
        href: slug ? `/spec/${ver}/${slug}/` : `/spec/${ver}/`,
        title: docTitle(entry),
        number: meta.number,
        depth: meta.depth,
        repo: entry.id,
        entry,
      });
    }
  }
  return pages;
}

export function latestVersion(): string | null {
  return readVersions().latest;
}
