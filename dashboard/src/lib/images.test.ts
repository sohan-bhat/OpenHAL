import { describe, expect, it } from "vitest";
import { askedAgo, askOf } from "./asks";
import { camerasFor, imageChannels } from "./devices";
import { Elided, describeImage, frameSource, imageSize, sameImage, stripImageData, withoutData, type ImageReading } from "./images";
import { mergeEntries } from "./logstore";
import type { LogEntry } from "./trace";
import type { ConfirmationRequest, DeviceView } from "./types";
import { identifiersOf, reasonSegments } from "./units";

function jpeg(size: number): ImageReading {
  const bytes = new Uint8Array(size);
  bytes.set([0xff, 0xd8, 0xff, 0xe0]);
  return { mimeType: "image/jpeg", bytes: size, width: 640, height: 480, data: Buffer.from(bytes).toString("base64") };
}

const png = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]).toString("base64");

describe("camera frames", () => {
  it("shows a JPEG whose bytes match what the hub reported", () => {
    const check = frameSource(jpeg(30));
    expect(check.ok).toBe(true);
    if (check.ok) expect(check.src.startsWith("data:image/jpeg;base64,/9j/")).toBe(true);
  });

  it("refuses a frame it can't check", () => {
    const frame = jpeg(30);
    expect(frameSource({ ...frame, mimeType: "image/svg+xml" })).toMatchObject({ ok: false });
    expect(frameSource({ ...frame, mimeType: "image/png" })).toEqual({ ok: false, reason: "The frame's first bytes are not image/png." });
    expect(frameSource({ ...frame, bytes: 31 })).toEqual({ ok: false, reason: "The frame is 30 bytes, but the hub reported 31." });
    expect(frameSource({ ...frame, data: `${frame.data!.slice(0, -4)}");` })).toMatchObject({ ok: false });
    expect(frameSource({ ...frame, data: undefined })).toEqual({ ok: false, reason: "The hub sent the frame without its pixels." });
    expect(frameSource({ mimeType: "image/png", bytes: 12, width: 1, height: 1, data: png }).ok).toBe(true);
  });

  it("describes a frame by its format, size and bytes", () => {
    expect(describeImage({ mimeType: "image/jpeg", bytes: 19409, width: 640, height: 480 })).toBe("image/jpeg, 640 × 480, 19 KB");
    expect(describeImage({ mimeType: "image/jpeg", bytes: 23567, width: 640, height: 480 })).toBe("image/jpeg, 640 × 480, 24 KB");
    expect(describeImage({ mimeType: "image/png", bytes: 2_400_000, width: 1920, height: 1080 })).toBe("image/png, 1920 × 1080, 2.4 MB");
    expect(describeImage({ mimeType: "image/jpeg", bytes: 10, width: null, height: null })).toBe("image/jpeg, 10 bytes");
    expect(imageSize({ mimeType: "image/jpeg", bytes: 10, width: -1, height: 480 })).toBeNull();
    expect(withoutData(jpeg(30))).toEqual({ mimeType: "image/jpeg", bytes: 30, width: 640, height: 480 });
    expect(sameImage(withoutData(jpeg(30)), jpeg(30))).toBe(true);
    expect(sameImage(jpeg(30), jpeg(31))).toBe(false);
  });

  it("drops the pixels from logged messages and keeps everything else", () => {
    const message = {
      jsonrpc: "2.0",
      id: 2,
      result: { readings: [{ device: "printer-cam", channel: "frame", value: jpeg(30) }, { device: "printer", channel: "state", value: "paused" }] },
    };
    const stripped = stripImageData(message);
    const frame = stripped.result.readings[0]!.value as unknown as Record<string, unknown>;
    expect(frame.data).toBeInstanceOf(Elided);
    expect(frame.bytes).toBe(30);
    expect(stripped.result.readings[1]).toBe(message.result.readings[1]);
    const error = { jsonrpc: "2.0", id: 3, error: { code: -32010, message: "no", data: { name: "LIMIT_EXCEEDED" } } };
    expect(stripImageData(error)).toBe(error);
    const entry: LogEntry = { seq: 1, at: 1, direction: "out", client: "print-watcher", principal: "agent:print-watcher", message };
    expect(JSON.stringify(mergeEntries([], [entry]))).not.toContain("/9j/");
  });
});

const printer = {
  id: "printer",
  name: "Klipper 3D printer",
  hazard: "medium",
  path: "/home/owner/.openhal/devices/printer.hal.yaml",
  read: { state: { type: "enum", unit: null, every_s: 1, stream: null, range: null, values: ["printing", "paused"], value: "paused", known: true } },
  write: {
    extruder_target: {
      type: "number",
      unit: "degC",
      min: 0,
      max: 260,
      step: null,
      max_change_per_s: 50,
      values: null,
      confirm: "confirm",
      suggested: null,
      value: 215,
      known: true,
    },
  },
  actions: {
    cancel: {
      description: "Cancel the print. It can't be resumed afterwards.",
      args: {},
      require: [],
      effects: [],
      confirm: "confirm-each-time",
    },
  },
} as unknown as DeviceView;

const camera = {
  id: "printer-cam",
  name: "Printer camera",
  read: { frame: { type: "image", unit: null, every_s: null, stream: false, range: null, values: null, value: null, known: false } },
} as unknown as DeviceView;

function request(command: ConfirmationRequest["command"]): ConfirmationRequest {
  return {
    id: "fc100aa740c6f81b",
    status: "pending",
    command,
    requested_by: "agent:print-watcher",
    created_at: 1000,
    expires_at: 1300,
    expires_in_s: 287,
    dry_run: {
      status: "needs_confirmation",
      code: "needs_confirmation",
      message: "Waiting for a human to approve action:cancel on printer.",
      device: "printer",
      target: "action:cancel",
      value: {},
      unit: null,
      limit: null,
      request_id: null,
    },
    decided_by: null,
    result: null,
  };
}

describe("the person's question", () => {
  it("shows what the agent requested, what it does and why the request is held", () => {
    const ask = askOf(request({ kind: "action", device: "printer", action: "cancel", args: {} }), printer);
    expect(ask).toMatchObject({
      actor: "The agent",
      name: "print-watcher",
      verb: "run",
      target: "cancel",
      value: null,
      device: "Klipper 3D printer",
      does: "Cancel the print. It can't be resumed afterwards.",
      file: "printer.hal.yaml",
    });
    expect(ask.why).toBe("printer.hal.yaml requires a person to confirm cancel each time. Nothing reaches the device until you approve.");
  });

  it("names the value and limit of a write", () => {
    const ask = askOf(request({ kind: "write", device: "printer", channel: "extruder_target", value: 240, unit: "degC" }), printer);
    expect(ask).toMatchObject({ verb: "set", target: "extruder_target", value: "240 °C", limit: "0 °C to 260 °C" });
    expect(ask.why.startsWith("printer.hal.yaml requires a person to confirm extruder_target.")).toBe(true);
  });

  it("falls back to the kernel's words when the device isn't loaded", () => {
    const ask = askOf(request({ kind: "action", device: "printer", action: "cancel", args: {} }), undefined);
    expect(ask.device).toBe("printer");
    expect(ask.why.startsWith("Waiting for a human to approve action:cancel on printer.")).toBe(true);
    expect(askedAgo(13.4)).toBe("13 s ago");
    expect(askedAgo(130)).toBe("2 min ago");
  });

  it("finds the device's own camera first, then the hub's other cameras", () => {
    expect(imageChannels(camera)).toEqual(["frame"]);
    expect(imageChannels(printer)).toEqual([]);
    const views = { printer, "printer-cam": camera };
    expect(camerasFor("printer", views)).toEqual([{ device: "printer-cam", channel: "frame", name: "Printer camera" }]);
    expect(camerasFor("printer-cam", views)[0]!.device).toBe("printer-cam");
  });

  it("sets an id in mono, but not the same word used as prose", () => {
    const code = (text: string) =>
      reasonSegments(text, identifiersOf("printer", "write:extruder_target"))
        .filter((segment) => segment.kind === "code")
        .map((segment) => segment.text);
    expect(code("Blocked by an interlock on printer. Clear the printer error before heating. Right now state != error doesn't hold.")).toEqual([
      "printer",
      "state != error",
    ]);
  });
});
