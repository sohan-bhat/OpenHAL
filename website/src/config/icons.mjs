/**
 * The version on every icon link, raised whenever the mark changes so browsers drop a cached
 * favicon. Version 3 is the plain H again, after version 2's arrow. Version 4 sets the mark in IBM
 * Plex Sans.
 */
export const ICON_VERSION = 4;

/** An icon's address with the version that busts the browser's cache. */
export function iconHref(path) {
  return `${path}?v=${ICON_VERSION}`;
}
