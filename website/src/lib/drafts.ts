// Draft blog posts are built only in development, or when OPENHAL_SHOW_DRAFTS=1.

export function showDrafts(): boolean {
  return import.meta.env.DEV || process.env.OPENHAL_SHOW_DRAFTS === "1";
}
