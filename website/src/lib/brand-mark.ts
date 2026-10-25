// The OpenHAL mark. A dark legend plate with a control track and the limit line, flag up.
// The header, the favicon set and the Open Graph images all draw it from this one source.

export const MARK_COLORS = {
  bezel: "#2b3035",
  onBezel: "#e7e9e6",
  limit: "#ee6b62",
  caution: "#f2b705",
};

/** The mark as SVG markup, in a 32 by 32 box. `title` adds an accessible name. */
export function markSvg(options: { size?: number; title?: string; className?: string } = {}): string {
  const { size = 32, title, className } = options;
  const { bezel, onBezel, limit, caution } = MARK_COLORS;
  const label = title ? `<title>${title}</title>` : "";
  const aria = title ? `role="img" aria-label="${title}"` : `aria-hidden="true" focusable="false"`;
  const cls = className ? ` class="${className}"` : "";
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="${size}" height="${size}" ${aria}${cls}>${label}` +
    `<rect width="32" height="32" rx="3" fill="${bezel}"/>` +
    `<rect x="5" y="19" width="22" height="2" fill="${onBezel}" opacity="0.55"/>` +
    `<rect x="5" y="18" width="12" height="4" fill="${onBezel}"/>` +
    `<rect x="21" y="9" width="2.5" height="17" fill="${limit}"/>` +
    `<path d="M21 6h7v5h-7z" fill="${caution}"/>` +
    `</svg>`
  );
}
