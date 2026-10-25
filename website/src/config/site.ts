export const REPOSITORY_URL = "https://github.com/sohan-bhat/OpenHAL";
export const REPOSITORY_DIR = "OpenHAL";
export const DEFAULT_BRANCH = "main";

export function editUrl(repoPath: string): string {
  return `${REPOSITORY_URL}/edit/${DEFAULT_BRANCH}/${repoPath}`;
}

export function sourceUrl(repoPath: string): string {
  return `${REPOSITORY_URL}/blob/${DEFAULT_BRANCH}/${repoPath}`;
}

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
