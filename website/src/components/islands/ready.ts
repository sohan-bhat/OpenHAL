import { useEffect, type RefObject } from "react";

/**
 * Tells the intent directive (src/directives/intent.mjs) that the island's handlers are in place,
 * so a press or shortcut that arrived while the island loaded can be replayed.
 */
export function useIslandReady(ref: RefObject<Element | null>): void {
  useEffect(() => {
    ref.current?.dispatchEvent(new Event("oh:island-ready", { bubbles: true }));
  }, [ref]);
}

/** The site's root, such as / or /OpenHAL/, taken from the header's wordmark link, which always points there. */
export function siteBase(): string {
  if (typeof document === "undefined") return "/";
  return document.querySelector<HTMLAnchorElement>("a.oh-brand")?.getAttribute("href") ?? "/";
}

/** A root-relative address moved under the site's base, so links keep working under /OpenHAL/. */
export function withBase(path: string): string {
  return path.startsWith("/") ? `${siteBase()}${path.slice(1)}` : path;
}
