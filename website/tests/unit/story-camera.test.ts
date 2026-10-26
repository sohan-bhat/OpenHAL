import { describe, expect, it } from "vitest";
import { cameraAt, framing, glide, transform, union, type Box, type Framed } from "../../src/lib/story/camera";
import { PLACED, SHOTS, TOTAL, at, shot } from "../../src/lib/story/script";

const FRAME: Box = { x: 48, y: 160, w: 1344, h: 640 };
const close = (a: number, b: number) => expect(Math.abs(a - b)).toBeLessThan(1e-6);

describe("the story camera", () => {
  it("frames a target centered and padded, no closer than max", () => {
    const target = { x: 100, y: 200, w: 400, h: 100 };
    const { from, to } = framing(target, FRAME, { pad: 20, max: 2 });
    expect(from).toBe(to);
    expect(from.z).toBe(2);
    const t = transform(from, FRAME);
    close(t.x + 300 * t.z, FRAME.x + FRAME.w / 2);
    close(t.y + 250 * t.z, FRAME.y + FRAME.h / 2);
    expect(framing(target, FRAME, { pad: 20 }).from.z).toBe((1344 - 40) / 400);
  });

  it("sits a top shot on the frame's top edge", () => {
    const target = { x: 0, y: 0, w: 1300, h: 300 };
    const { from } = framing(target, FRAME, { pad: 24, top: true });
    close(transform(from, FRAME).y, FRAME.y + 24);
  });

  it("scans a target too tall to read from its top to its bottom", () => {
    const phone: Box = { x: 16, y: 120, w: 358, h: 600 };
    const target = { x: 0, y: 0, w: 320, h: 1000 };
    const { from, to } = framing(target, phone, { pad: 16, min: 1 });
    expect(from.z).toBe(1);
    close(transform(from, phone).y, phone.y + 16);
    close(transform(to, phone).y + 1000, phone.y + phone.h - 16);
  });

  it("glides exactly from shot to shot and pulls back on a long move", () => {
    const a = { x: 200, y: 300, z: 1.5 };
    const b = { x: 1700, y: 300, z: 1.5 };
    for (const [e, cam] of [[0, a], [1, b]] as const) {
      const g = glide(a, b, e, FRAME);
      close(g.x, cam.x);
      close(g.y, cam.y);
      close(g.z, cam.z);
    }
    expect(glide(a, b, 0.5, FRAME).z).toBeLessThan(1.5);
    close(glide(a, { x: 260, y: 300, z: 1.2 }, 0.5, FRAME).z, Math.sqrt(1.5 * 1.2));
  });

  it("holds through each dwell and moves only in glides", () => {
    const shots: Framed[] = [
      { glideFrom: 0, dwellFrom: 0, end: 10, from: { x: 0, y: 0, z: 1 }, to: { x: 0, y: 0, z: 1 } },
      { glideFrom: 10, dwellFrom: 30, end: 50, from: { x: 500, y: 0, z: 2 }, to: { x: 500, y: 0, z: 2 } },
    ];
    expect(cameraAt(5, shots, FRAME)).toEqual(shots[0].from);
    expect(cameraAt(40, shots, FRAME)).toEqual(shots[1].from);
    expect(cameraAt(99, shots, FRAME)).toEqual(shots[1].to);
    const mid = cameraAt(20, shots, FRAME);
    expect(mid.x).toBeGreaterThan(0);
    expect(mid.x).toBeLessThan(500);
  });

  it("unions boxes", () => {
    expect(union([{ x: 0, y: 10, w: 100, h: 50 }, { x: 200, y: 0, w: 50, h: 100 }])).toEqual({ x: 0, y: 0, w: 250, h: 100 });
  });
});

describe("the shot list", () => {
  it("is continuous and its length is the sum of its shots", () => {
    expect(PLACED[0].glideFrom).toBe(0);
    for (let index = 1; index < PLACED.length; index++) expect(PLACED[index].glideFrom).toBe(PLACED[index - 1].end);
    expect(TOTAL).toBe(SHOTS.reduce((sum, item) => sum + item.glide + item.dwell, 0));
    expect(at("end", shot("end").dwell)).toBe(TOTAL);
  });

  it("travels the real path, starting and ending on the whole scene", () => {
    expect(SHOTS[0].target).toBe("scene");
    expect(SHOTS[SHOTS.length - 1].target).toBe("scene");
    expect(shot("watch").target).toEqual(["client"]);
    expect(shot("look").target).toEqual(["camera"]);
    expect(shot("warm").target).toEqual(["client", "hub", "kernel"]);
    expect(shot("heat").target).toEqual(["kernel", "driver", "printer"]);
    expect(shot("loose").target).toEqual(["camera"]);
    expect(shot("cancel").target).toEqual(["client", "hub", "kernel"]);
  });
});
