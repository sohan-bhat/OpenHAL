const GROUPS_KEY = "openhal-sidebar-groups";
const SCROLL_KEY = "openhal-sidebar-scroll";
const WIDE = "(min-width: 50rem)";

/**
 * True while a person keeps the documentation sidebar hidden. The page's head script reads the
 * choice from localStorage and marks the root before the first paint, so this reads the root.
 */
export function isCollapsed(): boolean {
  return typeof document !== "undefined" && document.documentElement.dataset.sidebar === "collapsed";
}

/** The groups a person closed or opened in this tab, by the labels that lead to each group. */
export function storedGroups(): Record<string, boolean> {
  try {
    const groups: unknown = JSON.parse(sessionStorage.getItem(GROUPS_KEY) || "{}");
    return groups && typeof groups === "object" ? (groups as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

/** Keeps a group open or closed on the next pages of this tab. */
export function rememberGroup(key: string, open: boolean): void {
  const groups = storedGroups();
  groups[key] = open;
  try {
    sessionStorage.setItem(GROUPS_KEY, JSON.stringify(groups));
  } catch {}
}

/**
 * Whether a group starts open. The group that holds the current page always does, and any other
 * group the way a person left it, or open unless Starlight's route data starts it closed.
 */
export function startsOpen(key: string, current: boolean, closed: boolean, groups: Record<string, boolean> = storedGroups()): boolean {
  return current || (groups[key] ?? !closed);
}

function savedScroll(): { hash: string; top: number } | null {
  try {
    const saved: unknown = JSON.parse(sessionStorage.getItem(SCROLL_KEY) || "null");
    return saved && typeof saved === "object" ? (saved as { hash: string; top: number }) : null;
  } catch {
    return null;
  }
}

/**
 * Gives the server-rendered sidebar the state the island renders once it loads, before the first
 * paint: hidden or shown, each group open or closed, and the scroll position the sidebar had on the
 * section's last page. A prerendered page applies the state again when it becomes the shown page,
 * since a person may have changed it meanwhile, and the scroll position is kept as the page goes.
 */
export function restore(island: Element): void {
  const scroller = () => island.querySelector<HTMLElement>("[data-slot=sidebar-content]");
  const apply = () => {
    const collapsed = isCollapsed();
    const sidebar = island.querySelector<HTMLElement>("[data-slot=sidebar]");
    if (sidebar) {
      sidebar.dataset.state = collapsed ? "collapsed" : "expanded";
      sidebar.dataset.collapsible = collapsed ? "offcanvas" : "";
    }
    island.querySelector("[data-slot=sidebar-rail]")?.setAttribute("aria-expanded", String(!collapsed));
    const groups = storedGroups();
    for (const group of island.querySelectorAll<HTMLElement>("[data-group]")) {
      const open = startsOpen(group.dataset.group ?? "", group.hasAttribute("data-current"), group.hasAttribute("data-closed"), groups);
      const state = open ? "open" : "closed";
      const parts = [...group.children];
      const trigger = parts.find((part) => part.hasAttribute("aria-expanded"));
      const content = parts.find((part) => part !== trigger && part.id);
      group.dataset.state = state;
      for (const part of parts) if (part.hasAttribute("data-state")) part.setAttribute("data-state", state);
      trigger?.setAttribute("aria-expanded", String(open));
      if (open && content) trigger?.setAttribute("aria-controls", content.id);
      else trigger?.removeAttribute("aria-controls");
    }
    const pane = scroller();
    const saved = savedScroll();
    if (pane && saved && saved.hash === pane.dataset.hash && matchMedia(WIDE).matches) pane.scrollTop = saved.top;
  };
  apply();
  if ((document as Document & { prerendering?: boolean }).prerendering) document.addEventListener("prerenderingchange", apply, { once: true });
  addEventListener("pagehide", () => {
    const pane = scroller();
    if (!pane || !matchMedia(WIDE).matches) return;
    try {
      sessionStorage.setItem(SCROLL_KEY, JSON.stringify({ hash: pane.dataset.hash, top: pane.scrollTop }));
    } catch {}
  });
}
