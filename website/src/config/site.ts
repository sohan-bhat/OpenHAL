import { REPOSITORY_URL } from "./repo.mjs";

export { DEFAULT_BRANCH, REPOSITORY_DIR, REPOSITORY_URL, editUrl, sourceUrl } from "./repo.mjs";

export interface NavLink {
  href: string;
  label: string;
  match: string[];
  external?: boolean;
}

export const NAV: NavLink[] = [
  { href: "/", label: "Overview", match: ["/", "/docs/"] },
  { href: "/spec/latest/", label: "Specification", match: ["/spec/"] },
  { href: "/drivers/", label: "Drivers", match: ["/drivers/"] },
  { href: "/library/", label: "Device Library", match: ["/library/"] },
  { href: "/sdks/", label: "SDKs", match: ["/sdks/"] },
  { href: "/inspector/", label: "Inspector", match: ["/inspector/"] },
  { href: "/blog/", label: "Blog", match: ["/blog/"] },
  { href: REPOSITORY_URL, label: "GitHub", match: [], external: true },
];
