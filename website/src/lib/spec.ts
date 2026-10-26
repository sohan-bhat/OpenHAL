import { type CollectionEntry, getCollection } from "astro:content";
import { docTitle } from "./docs-nav";
import { numberPages, orderPages, readVersions, slugOf } from "./spec-meta.mjs";

export { numberPages };

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

export async function specPages(version?: string): Promise<SpecPage[]> {
  const { versions } = readVersions();
  const wanted = version ? [version] : versions.map((item) => item.version);
  if (!wanted.length) return [];
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
