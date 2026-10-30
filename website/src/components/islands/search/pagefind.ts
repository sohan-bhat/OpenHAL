import type { PagefindData } from "./hits";

interface Result {
  data(): Promise<PagefindData>;
}

interface Pagefind {
  options(options: Record<string, unknown>): Promise<void>;
  init(): Promise<void>;
  preload(term: string): Promise<void>;
  debouncedSearch(term: string, options?: Record<string, unknown>, timeout?: number): Promise<{ results: Result[] } | null>;
}

/** Where the search index lives. The deploy moves this address under the site's base with the rest. */
const BUNDLE = "/pagefind/pagefind.js";

/** The site's base, such as / or /OpenHAL/, read from where the index lives. */
export const BASE = BUNDLE.slice(0, BUNDLE.indexOf("pagefind/"));

let loading: Promise<Pagefind> | undefined;

/** Loads Pagefind's own search code and the index's entry, once, the first time anything asks. */
export function pagefind(): Promise<Pagefind> {
  loading ??= (async () => {
    const module = (await import(/* @vite-ignore */ BUNDLE)) as Pagefind;
    await module.options({ baseUrl: BASE, excerptLength: 22 });
    await module.init();
    return module;
  })().catch((error: unknown) => {
    loading = undefined;
    throw error;
  });
  return loading;
}

/**
 * Searches the index, waiting a moment while a person is still typing. Resolves to null when a
 * newer search replaced this one, and otherwise to the data of the best `limit` pages.
 */
export async function search(term: string, limit = 8): Promise<PagefindData[] | null> {
  const index = await pagefind();
  const found = await index.debouncedSearch(term, {}, 120);
  if (!found) return null;
  return Promise.all(found.results.slice(0, limit).map((result) => result.data()));
}
