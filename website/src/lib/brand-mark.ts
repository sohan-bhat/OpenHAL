export const MARK_ACCENT = { light: "#1d5fb4", dark: "#7db2f0" };

function shapes(color: string): string {
  const line = (x1: number, y1: number, x2: number, y2: number) =>
    `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="2" stroke-linecap="round"/>`;
  return `${line(11, 2, 11, 14)}${line(2, 5, 8.5, 5)}${line(8.5, 11, 5, 11)}<polygon points="1.2,11 5.4,7.8 5.4,14.2" fill="${color}"/>`;
}

export function markSvg(options: { size?: number; title?: string; className?: string; color?: string } = {}): string {
  const { size = 16, title, className, color = "currentColor" } = options;
  const label = title ? `<title>${title}</title>` : "";
  const aria = title ? `role="img" aria-label="${title}"` : `aria-hidden="true" focusable="false"`;
  const cls = className ? ` class="${className}"` : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="${size}" height="${size}" ${aria}${cls}>${label}${shapes(color)}</svg>`;
}

export function faviconSvg(): string {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">` +
    `<style>g{color:${MARK_ACCENT.light}}@media (prefers-color-scheme: dark){g{color:${MARK_ACCENT.dark}}}</style>` +
    `<g>${shapes("currentColor")}</g></svg>`
  );
}
