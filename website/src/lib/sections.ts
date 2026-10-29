import { getCollection } from "astro:content";
import { type NavLink, navLinks } from "../config/site";
import { latestSpecHref } from "./spec";

export interface Section extends NavLink {
  current: boolean;
  matches: string;
}

/**
 * The site's top-level sections for the header and the phone menu, with the one a path belongs
 * to marked current. The longest matching prefix wins, so the Playground beats the Specification.
 */
export async function sections(path: string): Promise<Section[]> {
  const published = (await getCollection("blog")).some((post) => !post.data.draft);
  const links = navLinks(published, latestSpecHref()).filter((link) => !link.external);
  const matchLength = (match: string[]) =>
    Math.max(0, ...match.filter((prefix) => (prefix === "/" ? path === "/" : path.startsWith(prefix))).map((prefix) => prefix.length));
  const best = Math.max(0, ...links.map((link) => matchLength(link.match)));
  return links.map((link) => ({
    ...link,
    current: best > 0 && matchLength(link.match) === best,
    matches: link.match.map((prefix) => prefix.replace(/^\//, "")).join(" "),
  }));
}
