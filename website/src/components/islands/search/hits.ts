export interface Section {
  label: string;
  match: string[];
}

export interface PagefindSub {
  title: string;
  url: string;
  excerpt: string;
}

export interface PagefindData {
  url: string;
  excerpt: string;
  meta: { title?: string };
  sub_results?: PagefindSub[];
}

export interface Hit {
  id: string;
  url: string;
  title: string;
  heading?: string;
  excerpt: string;
}

export interface Group {
  section: string;
  hits: Hit[];
}

export interface Segment {
  text: string;
  mark: boolean;
}

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };

/** Turns the HTML entities Pagefind writes into text. */
export function decode(text: string): string {
  return text.replace(/&(#x[\da-f]+|#\d+|\w+);/gi, (whole, name: string) => {
    if (name[0] === "#") {
      const code = name[1].toLowerCase() === "x" ? parseInt(name.slice(2), 16) : parseInt(name.slice(1), 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : whole;
    }
    return ENTITIES[name.toLowerCase()] ?? whole;
  });
}

/** Splits an excerpt that marks its matches with <mark> into text runs, so it renders without innerHTML. */
export function marked(excerpt: string): Segment[] {
  const out: Segment[] = [];
  let mark = false;
  for (const part of excerpt.split(/(<mark>|<\/mark>)/)) {
    if (part === "<mark>") mark = true;
    else if (part === "</mark>") mark = false;
    else if (part) out.push({ text: decode(part.replace(/<[^>]*>/g, "")), mark });
  }
  return out;
}

/** The words of a query worth marking in a title, longest first so a longer match wins. */
export function terms(query: string): string[] {
  return [...new Set(query.toLowerCase().split(/[^\p{L}\p{N}_/.-]+/u).filter((word) => word.length > 1))].sort((a, b) => b.length - a.length);
}

/** Marks where the query's words appear in a title, ignoring case. */
export function highlight(text: string, query: string): Segment[] {
  const words = terms(query);
  if (!words.length) return [{ text, mark: false }];
  const pattern = new RegExp(`(${words.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return text
    .split(pattern)
    .filter(Boolean)
    .map((part) => ({ text: part, mark: words.includes(part.toLowerCase()) }));
}

/** The path of a result's address below the site's base, such as /docs/quickstart/. */
export function localPath(url: string, base: string): string {
  const path = url.split("#")[0];
  return base !== "/" && path.startsWith(base) ? path.slice(base.length - 1) : path;
}

/** The header section a page belongs to. The longest matching prefix wins, as in the header. */
export function sectionOf(path: string, sections: Section[]): string {
  let best = "";
  let length = -1;
  for (const section of sections) {
    for (const prefix of section.match) {
      const hit = prefix === "/" ? path === "/" : path.startsWith(prefix);
      if (hit && prefix.length > length) {
        best = section.label;
        length = prefix.length;
      }
    }
  }
  return best || "Other pages";
}

/**
 * Pagefind's results as rows: each page, then up to two of its sections whose text matched,
 * grouped under the header section the page belongs to, in the order the best result of each
 * section ranks.
 */
export function group(results: PagefindData[], sections: Section[], base: string, subsPerPage = 2): Group[] {
  const groups = new Map<string, Hit[]>();
  for (const result of results) {
    const title = decode(result.meta.title ?? "") || localPath(result.url, base);
    const section = sectionOf(localPath(result.url, base), sections);
    const hits = groups.get(section) ?? [];
    const subs = (result.sub_results ?? [])
      .filter((sub) => sub.url.includes("#") && !sub.url.endsWith("#_top") && sub.excerpt.includes("<mark>") && decode(sub.title) !== title)
      .slice(0, subsPerPage);
    const repeated = subs.some((sub) => sub.excerpt === result.excerpt);
    hits.push({ id: result.url, url: result.url, title, excerpt: repeated ? "" : result.excerpt });
    for (const sub of subs) hits.push({ id: sub.url, url: sub.url, title, heading: decode(sub.title), excerpt: sub.excerpt });
    groups.set(section, hits);
  }
  return [...groups].map(([section, hits]) => ({ section, hits }));
}
