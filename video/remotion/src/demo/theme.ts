import {loadFont} from '@remotion/fonts';
import {Easing, staticFile} from 'remotion';

export const COLOR = {
  bg: '#111210',
  surface: '#212220',
  highlight: '#2d2b26',
  border: '#383a36',
  text: '#eceeec',
  text2: '#afb5ad',
  neutral: '#cbb99f',
  accent: '#ff8dcc',
  accentFill: '#ff8dcc',
  onAccent: '#111210',
  ok: '#72b88e',
  confirm: '#7db2f0',
  blocked: '#d57a72',
  claude: '#d77757',
  windowTitle: '#8f948d',
} as const;

export const SANS = 'IBM Plex Sans';
export const MONO = 'IBM Plex Mono';

export const fontsLoaded = Promise.all([
  loadFont({family: MONO, url: staticFile('fonts/ibm-plex-mono-latin-400-normal.woff2'), weight: '400'}),
  loadFont({family: MONO, url: staticFile('fonts/ibm-plex-mono-latin-600-normal.woff2'), weight: '600'}),
  loadFont({family: MONO, url: staticFile('fonts/ibm-plex-mono-latin-700-normal.woff2'), weight: '700'}),
  loadFont({family: MONO, url: staticFile('fonts/ibm-plex-mono-latin-400-italic.woff2'), weight: '400', style: 'italic'}),
  loadFont({family: SANS, url: staticFile('fonts/ibm-plex-sans-latin-wght-normal.woff2'), weight: '100 700'}),
]);

export const FPS = 30;
export const WIDTH = 1280;
export const HEIGHT = 720;

export const EASE = {
  out: Easing.bezier(0.2, 0, 0, 1),
  inOut: Easing.bezier(0.65, 0, 0.35, 1),
  glide: Easing.bezier(0.33, 0, 0.15, 1),
} as const;

export const TIME = {
  appear: 12,
  countUp: 24,
  verdictDelay: 15,
  stagger: 9,
  minLabel: 45,
} as const;

export const clamp01 = (t: number) => Math.min(1, Math.max(0, t));

export const progress = (frame: number, start: number, length: number, easing: (t: number) => number = EASE.out) =>
  easing(clamp01((frame - start) / length));
