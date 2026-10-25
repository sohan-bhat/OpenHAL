import type { SideGroup } from "./nav-types";
import type { SpecPage } from "./spec";

export function specSidebar(pages: SpecPage[], hrefFor: (page: SpecPage) => string = (page) => page.href): SideGroup[] {
  return [
    {
      name: "",
      items: pages.map((page) => ({ title: page.title, href: hrefFor(page), number: page.number, depth: page.depth })),
    },
    { name: "Try it", items: [{ title: "Playground", href: "/spec/playground/" }] },
  ];
}
