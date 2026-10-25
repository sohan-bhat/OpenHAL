import type { SideGroup, SideItem } from "./nav-types";
import type { SpecPage } from "./spec";

const FOLDER_TITLES: Record<string, string> = { basic: "Base protocol", protocol: "Base protocol" };

function folderTitle(folder: string): string {
  return FOLDER_TITLES[folder] ?? folder.charAt(0).toUpperCase() + folder.slice(1).replace(/-/g, " ");
}

export function specSidebar(pages: SpecPage[], hrefFor: (page: SpecPage) => string = (page) => page.href): SideGroup[] {
  const items: SideItem[] = [];
  const labelled = new Set<string>();
  for (const page of pages) {
    const parts = page.path.split("/");
    if (page.depth === 2 && parts.length > 1) {
      const folder = parts[0];
      const top = page.number.split(".")[0];
      const hasIndex = pages.some((other) => other.version === page.version && other.depth === 1 && other.path.startsWith(`${folder}/`));
      if (!hasIndex && !labelled.has(`${page.version}/${folder}`)) {
        labelled.add(`${page.version}/${folder}`);
        items.push({ title: folderTitle(folder), number: top, depth: 1 });
      }
    }
    items.push({ title: page.slug === "" && page.depth === 1 ? "Introduction" : page.title, href: hrefFor(page), number: page.number, depth: page.depth });
  }
  return [
    { name: "", items },
    { name: "Try it", items: [{ title: "Playground", href: "/spec/playground/" }] },
  ];
}
