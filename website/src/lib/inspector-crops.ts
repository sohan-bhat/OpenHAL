import { existsSync } from "node:fs";
import { join } from "node:path";
import sharp from "sharp";
import captures from "../data/inspector-captures.json";
import { inspectorShots, type Shot } from "./inspector-shots";

export type Theme = "light" | "dark";

export interface CropImage {
  name: string;
  source: string;
  crop: Shot["crop"];
  width: number;
  format: "avif" | "webp";
  type: string;
}

export const THEMES: Theme[] = ["light", "dark"];
export const FORMATS = [
  { format: "avif", type: "image/avif" },
  { format: "webp", type: "image/webp" },
] as const;

/** The narrowest the Inspector page draws a crop, as a share of its recorded width. */
export const NARROWEST = 0.85;

const CAPTURES = join(process.cwd(), "public", "captures");

/** The full capture a shot is cropped from, as the capture script recorded it. */
export const capturePath = (file: string, theme: Theme) => `/captures/${file}-${theme}.webp`;

/** The shots whose captures exist in both themes. */
export function presentShots(shots: Shot[] = inspectorShots()): Shot[] {
  return shots.filter((shot) => THEMES.every((theme) => existsSync(join(CAPTURES, `${shot.file}-${theme}.webp`))));
}

/**
 * The widths a crop is served at. The page draws a crop between 85 % and all of its recorded
 * width, and the captures are recorded at one pixel per CSS pixel, so nothing wider helps.
 */
export function cropWidths(crop: Shot["crop"]): number[] {
  const narrow = Math.round(crop.w * NARROWEST);
  return narrow < crop.w ? [narrow, crop.w] : [crop.w];
}

export const cropPath = (file: string, theme: Theme, width: number, format: string) => `/captures/${file}-${theme}-${width}.${format}`;

export function cropSrcset(shot: Shot, theme: Theme, format: string): string {
  return cropWidths(shot.crop)
    .map((width) => `${cropPath(shot.file, theme, width, format)} ${width}w`)
    .join(", ");
}

/** The width the page draws a crop at, as the sizes attribute says it, from the frame's CSS. */
export function cropSizes(crop: Shot["crop"]): string {
  const low = Math.round(crop.w * NARROWEST);
  return `(min-width: 1024px) clamp(${low}px, min(100vw, 1360px) - 320px, ${crop.w}px), clamp(${low}px, 100vw - 32px, ${crop.w}px)`;
}

/** Every cropped image the site serves, in every theme, width and format. */
export function cropImages(shots: Shot[] = presentShots()): CropImage[] {
  return shots.flatMap((shot) =>
    THEMES.flatMap((theme) =>
      cropWidths(shot.crop).flatMap((width) =>
        FORMATS.map(({ format, type }) => ({
          name: cropPath(shot.file, theme, width, format).replace(/^\/captures\//, ""),
          source: join(CAPTURES, `${shot.file}-${theme}.webp`),
          crop: shot.crop,
          width,
          format,
          type,
        })),
      ),
    ),
  );
}

/** One cropped image, cut from its capture at the measured crop and scaled to its width. */
export async function renderCrop(image: CropImage): Promise<Uint8Array<ArrayBuffer>> {
  const region = { left: image.crop.x, top: image.crop.y, width: image.crop.w, height: image.crop.h };
  const cut = sharp(image.source).extract(region);
  const sized = image.width === image.crop.w ? cut : cut.resize({ width: image.width });
  const encoded = image.format === "avif" ? sized.avif({ quality: 60, effort: 4 }) : sized.webp({ quality: 85, effort: 4 });
  return Uint8Array.from(await encoded.toBuffer());
}

export const captureSize = { width: captures.width, height: captures.height };
