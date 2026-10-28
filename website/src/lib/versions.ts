export interface VersionEntry {
  version: string;
  status?: string | null;
  latest?: boolean;
}

export interface VersionRow {
  version: string;
  href: string;
  note: string;
  current: boolean;
}

/**
 * The versions the header's picker lists for a page. A spec page shows its own version and links
 * to the same section in each other version, or to that version's first page when the section is
 * missing there. Every other page shows the latest version and links to each version's spec.
 */
export function versionRows(path: string, versions: VersionEntry[], latest: string | null, pages: Array<{ version: string; slug: string }>) {
  const match = /^\/spec\/(\d{4}-\d{2}-\d{2}|latest)\/(.*?)\/?$/.exec(path);
  const current = match ? (match[1] === "latest" ? latest : match[1]) : latest;
  const slug = match?.[2] ?? "";
  const have = new Set(pages.map((page) => `${page.version}/${page.slug}`));
  const rows: VersionRow[] = versions.map((item) => ({
    version: item.version,
    href: `/spec/${item.version}/${slug && have.has(`${item.version}/${slug}`) ? `${slug}/` : ""}`,
    note: [item.latest ? "latest" : "", item.status ?? ""].filter(Boolean).join(" "),
    current: item.version === current,
  }));
  return { current, rows };
}
