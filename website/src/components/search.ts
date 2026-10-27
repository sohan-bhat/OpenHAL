interface PagefindResult {
  url: string;
  excerpt: string;
  meta: { title?: string; description?: string };
  sub_results?: Array<{ title: string; url: string; excerpt: string; locations?: number[] }>;
}

/**
 * Whether an excerpt reads as code or YAML rather than prose, from its keys, symbols, prompts and
 * identifiers. Prose on this site has no colons in running text, so a few "key:" words decide it.
 */
export function looksLikeCode(excerpt: string): boolean {
  const text = excerpt.replace(/<[^>]+>/g, "").replace(/&[a-z]+;|&#\d+;/g, " ").trim();
  if (!text) return false;
  const words = text.split(/\s+/);
  const keys = words.filter((word) => /^"?[A-Za-z_][\w.-]*"?:$/.test(word)).length;
  const symbols = (text.match(/[{}[\]=;<>|]|->|=>|\$ /g) ?? []).length;
  const names = words.filter((word) => /^[\w-]+(?:[_./][\w-]+)+[,.:;)]?$/.test(word) || /^--?[a-z]/.test(word)).length;
  return keys >= 2 || symbols >= 3 || names / words.length >= 0.4;
}

/** The snippet a result shows, its excerpt when that is prose, otherwise the page's description. */
export function snippetOf(excerpt: string | undefined, description: string | undefined): { html: string } | { text: string } | null {
  if (excerpt && !looksLikeCode(excerpt)) return { html: excerpt };
  if (description?.trim()) return { text: description.trim() };
  return null;
}

interface Pagefind {
  options?: (options: { excerptLength?: number }) => Promise<void>;
  init?: () => Promise<void>;
  search: (term: string) => Promise<{ results: Array<{ id: string; data: () => Promise<PagefindResult> }> } | null>;
}

const LIMIT = 8;
const CHECKED = 24;

/**
 * Wires the site search dialog. Its buttons and Ctrl K or Cmd K open it, Escape, its close button
 * and a click outside close it. The Pagefind index loads when a person points at a search button or
 * opens the dialog, so a page that is only read never fetches it.
 */
export function searchDialog(): void {
  const dialog = document.querySelector<HTMLDialogElement>("#site-search");
  if (!dialog) return;
  const input = dialog.querySelector<HTMLInputElement>("[data-search-input]");
  const list = dialog.querySelector<HTMLOListElement>("[data-search-results]");
  const status = dialog.querySelector<HTMLElement>("[data-search-status]");
  if (!input || !list || !status) return;
  const sections = JSON.parse(dialog.dataset.sections ?? "[]") as Array<{ prefix: string; label: string }>;
  const idle = status.textContent ?? "";
  const bundle = dialog.dataset.src ?? "/pagefind/pagefind.js";
  let engine: Promise<Pagefind | null> | null = null;
  let latest = 0;

  function load(): Promise<Pagefind | null> {
    if (!engine) {
      engine = import(new URL(bundle, window.location.href).href)
        .then(async (module: Pagefind) => {
          await module.options?.({ excerptLength: 20 });
          await module.init?.();
          return module;
        })
        .catch(() => null);
    }
    return engine;
  }

  function sectionOf(url: string): string {
    const path = new URL(url, window.location.href).pathname;
    const base = new URL(bundle, window.location.href).pathname.replace(/pagefind\/pagefind\.js$/, "");
    const local = `/${path.slice(base.length)}`;
    return sections.filter((item) => local.startsWith(item.prefix)).sort((a, b) => b.prefix.length - a.prefix.length)[0]?.label ?? "Overview";
  }

  function bestPart(result: PagefindResult) {
    const parts = (result.sub_results ?? []).filter((part) => part.url !== result.url && part.title !== result.meta.title);
    return parts.sort((a, b) => (b.locations?.length ?? 0) - (a.locations?.length ?? 0))[0] ?? null;
  }

  function resultItem(result: PagefindResult, index: number): HTMLLIElement {
    const part = bestPart(result);
    const title = result.meta.title ?? part?.title ?? result.url;
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = part?.url ?? result.url;
    link.id = `site-search-result-${index}`;
    link.className = "search-result";
    const head = document.createElement("span");
    head.className = "result-head";
    const name = document.createElement("span");
    name.className = "result-title";
    name.textContent = title;
    head.append(name);
    if (part && part.title && part.title !== title) {
      const section = document.createElement("span");
      section.className = "result-part";
      section.textContent = part.title;
      head.append(section);
    }
    const where = document.createElement("span");
    where.className = "result-where";
    where.textContent = sectionOf(result.url);
    link.append(where, head);
    const snippet = snippetOf(part?.excerpt ?? result.excerpt, result.meta.description);
    if (snippet) {
      const excerpt = document.createElement("span");
      excerpt.className = "result-excerpt";
      if ("html" in snippet) excerpt.innerHTML = snippet.html;
      else excerpt.textContent = snippet.text;
      link.append(excerpt);
    }
    item.append(link);
    return item;
  }

  function relevant(result: PagefindResult, words: string[]): boolean {
    const text = [result.excerpt, ...(result.sub_results ?? []).map((part) => part.excerpt)].join(" ");
    const marks = [...text.matchAll(/<mark>([^<]*)<\/mark>/g)].map((match) => match[1].toLowerCase());
    const title = (result.meta.title ?? "").toLowerCase();
    return words.some((word) => title.includes(word) || marks.some((mark) => mark.startsWith(word.slice(0, 3))));
  }

  async function run(term: string) {
    if (!list || !status) return;
    const ticket = ++latest;
    const query = term.trim();
    if (!query) {
      list.replaceChildren();
      list.hidden = true;
      status.textContent = idle;
      return;
    }
    const pagefind = await load();
    if (ticket !== latest) return;
    if (!pagefind) {
      list.hidden = true;
      status.textContent = "Search needs the index that pnpm build makes. This build has none.";
      return;
    }
    const found = await pagefind.search(query);
    const loaded = await Promise.all((found?.results ?? []).slice(0, CHECKED).map((result) => result.data()));
    if (ticket !== latest) return;
    const words = query.toLowerCase().split(/[^\p{L}\p{N}_]+/u).filter(Boolean);
    const results = loaded.filter((result) => relevant(result, words));
    list.replaceChildren(...results.slice(0, LIMIT).map(resultItem));
    list.hidden = results.length === 0;
    const total = results.length === CHECKED ? (found?.results.length ?? CHECKED) : results.length;
    status.textContent =
      total === 0 ? `No page matches “${query}”.` : total > LIMIT ? `${total} pages match. The best ${LIMIT} are below.` : `${total} ${total === 1 ? "page matches" : "pages match"}.`;
  }

  function links(): HTMLAnchorElement[] {
    return list ? [...list.querySelectorAll<HTMLAnchorElement>("a.search-result")] : [];
  }

  dialog.querySelector("[data-search-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    links()[0]?.click();
  });
  input.addEventListener("input", () => void run(input.value));
  dialog.addEventListener("keydown", (event) => {
    const all = links();
    const at = all.indexOf(document.activeElement as HTMLAnchorElement);
    if (event.key === "Escape") {
      event.preventDefault();
      dialog.close();
    } else if (event.key === "ArrowDown" && all.length) {
      event.preventDefault();
      all[Math.min(at + 1, all.length - 1)].focus();
    } else if (event.key === "ArrowUp" && at !== -1) {
      event.preventDefault();
      if (at === 0) input.focus();
      else all[at - 1].focus();
    } else if (at !== -1 && event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey) {
      input.focus();
    }
  });
  function open() {
    if (!dialog || !input) return;
    if (!dialog.open) dialog.showModal();
    input.focus();
    input.select();
    void load();
  }

  for (const button of document.querySelectorAll<HTMLElement>("[data-search-open]")) {
    button.addEventListener("click", open);
    button.addEventListener("pointerenter", () => void load(), { once: true });
  }
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (dialog.open) dialog.close();
      else open();
    }
  });
  dialog.querySelector("[data-search-close]")?.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}
