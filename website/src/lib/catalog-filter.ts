/** The choices a catalog page's filters hold, keyed by the field's name in the URL, such as q or hazard. */
export type Choices = Record<string, string>;

/** The field that matches words anywhere in a row, rather than one exact value. */
export const SEARCH = "q";

/** A row as the filters see it: its words and its value for each select. */
export interface Row {
  text: string;
  values: Record<string, string | undefined>;
}

/** The choices a query string carries for the given fields, leaving out empty ones and unknown fields. */
export function readChoices(search: string, fields: readonly string[]): Choices {
  const params = new URLSearchParams(search);
  const choices: Choices = {};
  for (const field of fields) {
    const value = params.get(field)?.trim();
    if (value) choices[field] = value;
  }
  return choices;
}

/** The query string for the choices, in the fields' order, or an empty string when nothing is chosen. */
export function writeChoices(choices: Choices, fields: readonly string[]): string {
  const params = new URLSearchParams();
  for (const field of fields) {
    const value = choices[field]?.trim();
    if (value) params.set(field, value);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

/** True when any field holds a choice. */
export function isFiltered(choices: Choices): boolean {
  return Object.values(choices).some((value) => value.trim() !== "");
}

/** True when a row holds every word of the search and the chosen value of every select. */
export function matches(row: Row, choices: Choices): boolean {
  const words = (choices[SEARCH] ?? "").toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.every((word) => row.text.includes(word))) return false;
  return Object.entries(choices).every(([field, value]) => field === SEARCH || !value || row.values[field] === value);
}

/** The sentence under the filters, such as "34 drivers." or "3 of 34 drivers.". */
export function countLine(shown: number, total: number, noun: string, filtered: boolean): string {
  return filtered ? `${shown} of ${total} ${noun}.` : `${total} ${noun}.`;
}

function rowOf(element: HTMLElement, fields: readonly string[]): Row {
  const values: Row["values"] = {};
  for (const field of fields) if (field !== SEARCH) values[field] = element.dataset[field];
  return { text: element.dataset.text ?? "", values };
}

/** The fields a catalog page offers, read from its count line's data-fields attribute. */
export function pageFields(root: ParentNode = document): string[] {
  return (root.querySelector<HTMLElement>("[data-shown]")?.dataset.fields ?? SEARCH).split(/\s+/).filter(Boolean);
}

/**
 * Shows the rows of the page's catalog table that match the choices and hides the rest, hides a
 * group with no row left, and updates the count line and the empty note. Reference rows show and
 * hide like the others but stay out of the count.
 */
export function applyChoices(choices: Choices, root: ParentNode = document): void {
  const fields = pageFields(root);
  const rows = [...root.querySelectorAll<HTMLElement>("[data-filter-row]")];
  let shown = 0;
  let total = 0;
  for (const element of rows) {
    element.hidden = !matches(rowOf(element, fields), choices);
    if (element.hasAttribute("data-reference")) continue;
    total += 1;
    if (!element.hidden) shown += 1;
  }
  for (const group of root.querySelectorAll<HTMLElement>("[data-filter-group]")) group.hidden = !group.querySelector("[data-filter-row]:not([hidden])");
  const line = root.querySelector<HTMLElement>("[data-shown]");
  if (line) line.textContent = countLine(shown, total, line.dataset.noun ?? "", isFiltered(choices));
  const empty = root.querySelector<HTMLElement>("[data-empty]");
  if (empty) empty.hidden = rows.some((element) => !element.hidden);
}

/** Puts the choices in the address bar, so a filtered view can be shared, without adding a history entry. */
export function keepInAddress(choices: Choices, fields: readonly string[]): void {
  const url = new URL(window.location.href);
  url.search = writeChoices(choices, fields);
  if (url.href !== window.location.href) window.history.replaceState(window.history.state, "", url);
}

/** Applies the choices a shared address carries as the page opens, before the filters' island loads. */
export function restoreFromAddress(): void {
  const choices = readChoices(window.location.search, pageFields());
  if (isFiltered(choices)) applyChoices(choices);
}
