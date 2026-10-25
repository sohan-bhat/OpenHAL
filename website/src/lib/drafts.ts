export function showDrafts(): boolean {
  return import.meta.env.DEV || process.env.OPENHAL_SHOW_DRAFTS === "1";
}
