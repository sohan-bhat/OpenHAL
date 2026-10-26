export interface ImageReading {
  mimeType: string;
  bytes: number;
  width: number | null;
  height: number | null;
  data?: string;
}

export const SHOWN_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"] as const;

const MAX_SIDE = 16384;
const BASE64 = /^[A-Za-z0-9+/]*={0,2}$/;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isImageReading(value: unknown): value is ImageReading {
  return isObject(value) && typeof value.mimeType === "string" && typeof value.bytes === "number";
}

function side(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value > 0 && value <= MAX_SIDE ? value : null;
}

export function imageSize(image: ImageReading): { width: number; height: number } | null {
  const width = side(image.width);
  const height = side(image.height);
  return width && height ? { width, height } : null;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1000) return `${bytes} bytes`;
  if (bytes < 1_000_000) return `${Math.round(bytes / 1000)} KB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

export function imageFacts(image: ImageReading): string[] {
  const size = imageSize(image);
  const facts = [image.mimeType];
  if (size) facts.push(`${size.width} × ${size.height}`);
  facts.push(formatBytes(image.bytes));
  return facts;
}

export function describeImage(image: ImageReading): string {
  return imageFacts(image).join(", ");
}

export function sameImage(a: ImageReading | null | undefined, b: ImageReading | null | undefined): boolean {
  if (!a || !b) return false;
  return a.mimeType === b.mimeType && a.bytes === b.bytes && a.width === b.width && a.height === b.height;
}

export function withoutData(image: ImageReading): ImageReading {
  return { mimeType: image.mimeType, bytes: image.bytes, width: image.width ?? null, height: image.height ?? null };
}

function decodedLength(data: string): number {
  const padding = data.endsWith("==") ? 2 : data.endsWith("=") ? 1 : 0;
  return (data.length / 4) * 3 - padding;
}

function startsAs(mimeType: string, head: Uint8Array): boolean {
  const ascii = (from: number, to: number) => String.fromCharCode(...head.slice(from, to));
  switch (mimeType) {
    case "image/jpeg":
      return head[0] === 0xff && head[1] === 0xd8 && head[2] === 0xff;
    case "image/png":
      return head[0] === 0x89 && ascii(1, 4) === "PNG";
    case "image/gif":
      return ascii(0, 4) === "GIF8";
    case "image/webp":
      return ascii(0, 4) === "RIFF" && ascii(8, 12) === "WEBP";
    default:
      return false;
  }
}

export type FrameCheck = { ok: true; src: string } | { ok: false; reason: string };

export function frameSource(image: ImageReading): FrameCheck {
  if (!(SHOWN_TYPES as readonly string[]).includes(image.mimeType)) {
    return { ok: false, reason: `The Inspector shows JPEG, PNG, GIF and WebP frames. This one is ${image.mimeType}.` };
  }
  const data = image.data;
  if (typeof data !== "string" || !data.length) return { ok: false, reason: "The hub sent the frame without its pixels." };
  if (data.length % 4 !== 0 || !BASE64.test(data)) return { ok: false, reason: "The frame's pixels are not valid base64." };
  if (decodedLength(data) !== image.bytes) {
    return { ok: false, reason: `The frame is ${decodedLength(data)} bytes, but the hub said ${image.bytes}.` };
  }
  let head: Uint8Array;
  try {
    head = Uint8Array.from(atob(data.slice(0, 16)), (char) => char.charCodeAt(0));
  } catch {
    return { ok: false, reason: "The frame's pixels are not valid base64." };
  }
  if (!startsAs(image.mimeType, head)) {
    return { ok: false, reason: `The frame's first bytes are not ${image.mimeType}.` };
  }
  return { ok: true, src: `data:${image.mimeType};base64,${data}` };
}

export class Elided {
  constructor(readonly characters: number) {}

  toString(): string {
    return "<base64 not shown>";
  }
}

export function stripImageData<T>(value: T, depth = 0): T {
  if (depth > 8 || value === null || typeof value !== "object") return value;
  if (Array.isArray(value)) {
    let changed = false;
    const next = value.map((item) => {
      const stripped = stripImageData(item, depth + 1);
      if (stripped !== item) changed = true;
      return stripped;
    });
    return (changed ? next : value) as T;
  }
  if (value instanceof Elided) return value;
  const record = value as Record<string, unknown>;
  let changed = false;
  const next: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(record)) {
    if (key === "data" && typeof item === "string" && typeof record.mimeType === "string") {
      next[key] = new Elided(item.length);
      changed = true;
      continue;
    }
    const stripped = stripImageData(item, depth + 1);
    if (stripped !== item) changed = true;
    next[key] = stripped;
  }
  return (changed ? next : value) as T;
}
