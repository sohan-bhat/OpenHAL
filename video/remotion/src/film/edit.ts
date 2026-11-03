import {loadFont} from '@remotion/fonts';
import {staticFile} from 'remotion';
import editData from '../../../scenes/shots/film/edit.json';
import planData from '../../../scenes/film.json';

export type Aspect = 'landscape' | 'vertical';

export type LabelStyle = 'call' | 'blocked' | 'pending' | 'approved' | 'stop';

export type Label = {
  text: string;
  style: LabelStyle;
  from: number;
  to: number;
  shot: string;
  place: Record<Aspect, [number, number]>;
};

export type Item = {
  kind: 'shot' | 'black' | 'card';
  id: string;
  start: number;
  frames: number;
  storyboard?: number;
  wordmark?: number;
  tagline?: string;
  command?: string;
  url?: string;
  fine_print?: string;
};

export type Edit = {
  fps: number;
  frames: number;
  resolution: Record<Aspect, [number, number]>;
  items: Item[];
  labels: Label[];
};

export type Still = {storyboard: number; shot: string; frame: number};

export const film = editData as unknown as Edit;
export const stills = (planData as unknown as {stills: Still[]}).stills;

export const card = (): Item => {
  const item = film.items.find((i) => i.kind === 'card');
  if (!item) {
    throw new Error('The edit has no end card');
  }
  return item;
};

export const COLORS = {
  bg: '#111210',
  text: '#eceeec',
  text2: '#afb5ad',
  muted: '#8a9087',
  accent: '#ff8dcc',
  ok: '#72b88e',
  confirm: '#7db2f0',
  blocked: '#d57a72',
};

export const MONO = 'IBM Plex Mono';
export const SANS = 'IBM Plex Sans';

loadFont({family: MONO, url: staticFile('fonts/ibm-plex-mono-latin-400-normal.woff2'), weight: '400'});
loadFont({family: MONO, url: staticFile('fonts/ibm-plex-mono-latin-600-normal.woff2'), weight: '600'});
loadFont({family: SANS, url: staticFile('fonts/ibm-plex-sans-latin-wght-normal.woff2'), weight: '100 700'});

export const easeOut = (t: number): number => 1 - Math.pow(1 - Math.min(Math.max(t, 0), 1), 3);
