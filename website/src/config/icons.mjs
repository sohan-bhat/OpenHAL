/**
 * The version on every icon link, raised whenever the mark changes so browsers drop a cached
 * favicon. Version 2 is the mark whose H's crossbar is an arrow.
 */
export const ICON_VERSION = 2;

/** An icon's address with the version that busts the browser's cache. */
export function iconHref(path) {
  return `${path}?v=${ICON_VERSION}`;
}
