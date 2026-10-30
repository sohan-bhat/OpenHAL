import { api } from "./api";
import { frameSource, isImageReading, sameImage, withoutData, type ImageReading } from "./images";
import { inspector } from "./state.svelte";
import { dataBlock } from "./units";

export interface Frame {
  image: ImageReading | null;
  src: string | null;
  at: number | null;
  reading: boolean;
  problem: string | null;
  detail: string | null;
}

const EMPTY: Frame = { image: null, src: null, at: null, reading: false, problem: null, detail: null };
const AUTO_GAP_MS = 10_000;

export function frameKey(device: string, channel: string): string {
  return `${device}/${channel}`;
}

class Frames {
  all = $state.raw<Record<string, Frame>>({});
  private autoAt = new Map<string, number>();

  get(device: string, channel: string): Frame | undefined {
    return this.all[frameKey(device, channel)];
  }

  private set(key: string, frame: Frame): void {
    this.all = { ...this.all, [key]: frame };
  }

  async read(device: string, channel: string): Promise<void> {
    const key = frameKey(device, channel);
    const before = this.all[key] ?? EMPTY;
    if (before.reading) return;
    this.set(key, { ...before, reading: true });
    let next: Frame;
    try {
      const result = await api.read(device, channel);
      if (!result.ok) {
        next = {
          ...before,
          reading: false,
          problem: "The hub could not read the frame.",
          detail: dataBlock(result.error)?.text ?? null,
        };
      } else if (!isImageReading(result.value)) {
        next = { ...before, reading: false, problem: `${channel} did not return an image.`, detail: null };
      } else {
        const image = withoutData(result.value);
        const check = frameSource(result.value);
        const at = typeof result.at === "number" ? result.at : null;
        next = check.ok
          ? { image, src: check.src, at, reading: false, problem: null, detail: null }
          : { image, src: null, at, reading: false, problem: check.reason, detail: null };
        inspector.noteReading(device, channel, image);
      }
    } catch (error) {
      next = { ...before, reading: false, problem: error instanceof Error ? error.message : "Reading the frame failed.", detail: null };
    }
    this.set(key, next);
  }

  ensure(device: string, channel: string, latest: ImageReading | null): void {
    const key = frameKey(device, channel);
    const frame = this.all[key];
    if (frame?.reading) return;
    const now = Date.now();
    const newer = !!latest && !!frame?.image && !sameImage(latest, frame.image);
    if (frame && !(newer && now - (this.autoAt.get(key) ?? 0) > AUTO_GAP_MS)) return;
    this.autoAt.set(key, now);
    void this.read(device, channel);
  }
}

export const frames = new Frames();

export function latestImage(value: unknown, known: boolean): ImageReading | null {
  return known && isImageReading(value) ? withoutData(value) : null;
}
