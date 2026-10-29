import type { SideGroup, SideItem } from "./nav-types";

export interface SidebarLink {
  label: string;
  link: string;
}

export interface SidebarGroup {
  label: string;
  items: SidebarEntry[];
  collapsed?: boolean;
}

export type SidebarEntry = SidebarLink | SidebarGroup;

const labelOf = (item: SideItem) => (item.number ? `${item.number} ${item.title}` : item.title);

/**
 * A section's items as Starlight sidebar entries. An item without a link, such as a spec folder,
 * becomes a group that holds the deeper items after it, and a page that has deeper items opens
 * its own group.
 */
function entries(items: SideItem[]): SidebarEntry[] {
  const out: SidebarEntry[] = [];
  let open: SidebarGroup | null = null;
  items.forEach((item, index) => {
    if ((item.depth ?? 1) > 1 && open) {
      if (item.href) open.items.push({ label: labelOf(item), link: item.href });
      return;
    }
    open = null;
    const opens = (items[index + 1]?.depth ?? 1) > 1;
    if (!item.href || opens) {
      open = { label: labelOf(item), items: item.href ? [{ label: item.title, link: item.href }] : [] };
      out.push(open);
      return;
    }
    out.push({ label: labelOf(item), link: item.href });
  });
  return out;
}

/** Turns the site's section sidebars into Starlight's sidebar configuration. Unnamed groups list their links at the top level. */
export function starlightSidebar(groups: SideGroup[]): SidebarEntry[] {
  return groups.flatMap((group) => (group.name ? [{ label: group.name, items: entries(group.items) }] : entries(group.items)));
}
