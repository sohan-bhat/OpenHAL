export type View = "devices" | "confirmations" | "audit" | "routines" | "writer" | "settings";

export interface Route {
  view: View;
  id: string | null;
}

const VIEWS: View[] = ["devices", "confirmations", "audit", "routines", "writer", "settings"];

export const NAV: { view: View; label: string }[] = [
  { view: "devices", label: "Devices" },
  { view: "confirmations", label: "Confirmations" },
  { view: "audit", label: "Audit log" },
  { view: "routines", label: "Routines" },
  { view: "writer", label: "Driver writer" },
  { view: "settings", label: "Settings" },
];

export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  const view = VIEWS.includes(parts[0] as View) ? (parts[0] as View) : "devices";
  return { view, id: parts[1] ?? null };
}

export function href(view: View, id?: string | null): string {
  return id ? `#/${view}/${encodeURIComponent(id)}` : `#/${view}`;
}

class Router {
  route = $state<Route>(parseHash(typeof location === "undefined" ? "" : location.hash));

  constructor() {
    if (typeof window !== "undefined") {
      window.addEventListener("hashchange", () => {
        this.route = parseHash(location.hash);
      });
    }
  }

  go(view: View, id?: string | null): void {
    location.hash = href(view, id);
  }
}

export const router = new Router();
