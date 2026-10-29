const KEY = "openhal-recent-searches";
const KEEP = 5;

/** The searches a person opened a result from in this browser, newest first. */
export function readRecent(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string").slice(0, KEEP) : [];
  } catch {
    return [];
  }
}

/** Remembers a search at the top of the list, once, keeping the newest five. */
export function remember(query: string): string[] {
  const clean = query.trim().replace(/\s+/g, " ");
  if (!clean) return readRecent();
  const next = [clean, ...readRecent().filter((item) => item.toLowerCase() !== clean.toLowerCase())].slice(0, KEEP);
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {}
  return next;
}

/** Forgets every remembered search. */
export function forget(): string[] {
  try {
    localStorage.removeItem(KEY);
  } catch {}
  return [];
}
