/**
 * Screens tall enough that a pinned stage may play, with motion allowed. The height is under the
 * shortest stage of any layout with the header, so a stage never turns off while a phone hides its
 * toolbars. The inline scripts and the runtime still check that the stage fits.
 */
export const CAMERA = "(prefers-reduced-motion: no-preference) and (min-height: 600px)";
