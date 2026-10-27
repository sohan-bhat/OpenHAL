import { REPOSITORY_URL } from "./repo.mjs";

export { DEFAULT_BRANCH, REPOSITORY_DIR, REPOSITORY_URL, editUrl, sourceUrl } from "./repo.mjs";

export interface NavLink {
  href: string;
  label: string;
  match: string[];
  external?: boolean;
}

export const BLOG: NavLink = { href: "/blog/", label: "Blog", match: ["/blog/"] };

/** The main navigation. SDKs and the Inspector live under Docs, and the blog joins once a post is published. */
export function navLinks(published: boolean): NavLink[] {
  return [
    { href: "/", label: "Overview", match: ["/"] },
    { href: "/docs/", label: "Docs", match: ["/docs/", "/sdks/", "/inspector/"] },
    { href: "/spec/latest/", label: "Specification", match: ["/spec/"] },
    { href: "/spec/playground/", label: "Playground", match: ["/spec/playground/"] },
    { href: "/drivers/", label: "Drivers", match: ["/drivers/"] },
    { href: "/library/", label: "Device Library", match: ["/library/"] },
    ...(published ? [BLOG] : []),
    { href: REPOSITORY_URL, label: "GitHub", match: [], external: true },
  ];
}
