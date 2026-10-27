import { describe, expect, it } from "vitest";
import fixture from "./fixtures/log.json";
import {
  buildTrace,
  filterOptions,
  filterRows,
  formatTime,
  NO_FILTERS,
  plainTrace,
  principalInfo,
  stringifyCompact,
  tokenizeJson,
  type LogEntry,
} from "./trace";

const entries = fixture as LogEntry[];

describe("buildTrace", () => {
  const rows = buildTrace(entries);

  it("gives hal/initialize the principal its answer names, so agents keep their dashed rule", () => {
    const hello = rows.find((row) => row.seq === 1)!;
    expect(hello.head).toBe("hal/initialize");
    expect(hello.client).toBe("print-watcher");
    expect(hello.principal.kind).toBe("agent");
    expect(hello.principal.label).toBe("agent:print-watcher");
  });

  it("draws a request as a right arrow with its method", () => {
    const request = rows.find((row) => row.seq === 11)!;
    expect(request.arrow).toBe("right");
    expect(request.kind).toBe("request");
    expect(request.head).toBe("hal/write");
    expect(request.tone).toBe("method");
    expect(stringifyCompact(request.payload)).toBe('{ "device": "printer", "channel": "extruder_target", "value": 300, "unit": "degC" }');
  });

  it("names a blocked command with the registry code and name and its reason", () => {
    const error = rows.find((row) => row.seq === 13)!;
    expect(error.arrow).toBe("left");
    expect(error.head).toBe("error -32010 LIMIT_EXCEEDED");
    expect(error.errorName).toBe("LIMIT_EXCEEDED");
    expect(error.reason).toBe(
      "extruder_target 300 degC exceeds the limit of 260 degC (printer.hal.yaml, confirmed by owner 2026-10-24)",
    );
    expect(error.method).toBe("hal/write");
    expect(error.devices).toEqual(["printer"]);
    expect(error.hasPayload).toBe(false);
  });

  it("pairs responses with requests to give the request its outcome", () => {
    expect(rows.find((row) => row.seq === 11)!.outcome).toBe("error");
    expect(rows.find((row) => row.seq === 21)!.outcome).toBe("error");
    expect(rows.find((row) => row.seq === 9)!.outcome).toBe("granted");
    expect(rows.find((row) => row.seq === 16)!.outcome).toBe("granted");
    expect(rows.find((row) => row.seq === 18)!.outcome).toBe("pending");
    expect(rows.find((row) => row.seq === 17)!.method).toBe("hal/action");
    expect(rows.find((row) => row.seq === 23)!.head).toBe("error -32012 INTERLOCK_BLOCKED");
    expect(rows.find((row) => row.seq === 23)!.reason).toBe("Clear the printer error before heating.");
  });

  it("marks a pending result as needing confirmation, not as granted", () => {
    const pending = rows.find((row) => row.seq === 20)!;
    expect(pending.head).toBe("result");
    expect(pending.tone).toBe("pending");
    expect(pending.devices).toEqual(["printer"]);
    expect(rows.find((row) => row.seq === 19)!.outcome).toBe("pending");
  });

  it("draws notifications with dashed arrows", () => {
    expect(rows.find((row) => row.seq === 3)!.arrow).toBe("right-dashed");
    const value = rows.find((row) => row.seq === 8)!;
    expect(value.arrow).toBe("left-dashed");
    expect(value.kind).toBe("notification");
    const blocked = rows.find((row) => row.seq === 12)!;
    expect(blocked.outcome).toBe("error");
    expect(blocked.errorName).toBe("LIMIT_EXCEEDED");
    expect(blocked.summary).toEqual({ device: "printer", target: "write:extruder_target" });
  });

  it("shows a camera frame as its description and never its base64", () => {
    const frame = rows.find((row) => row.seq === 5)!;
    expect(frame.kind).toBe("result");
    expect(frame.summary).toEqual({
      device: "printer-cam",
      channel: "frame",
      value: { mimeType: "image/jpeg", bytes: 19409, width: 640, height: 480 },
    });
    const whole = stringifyCompact(frame.payload);
    expect(whole).toContain('"data": <base64 not shown>');
    expect(whole).not.toContain("/9j/");
    expect(rows.find((row) => row.seq === 15)!.summary).toMatchObject({ value: { bytes: 23567 } });
    expect(plainTrace(rows.filter((row) => [4, 5, 14, 15].includes(row.seq)))).not.toContain("/9j/");
    const raw = (entries[4]!.message as { result: { value: { data: string } } }).result.value.data;
    expect(raw.startsWith("/9j/")).toBe(true);
  });

  it("keeps text that is not JSON-RPC as an invalid row", () => {
    const invalid = rows.find((row) => row.seq === 24)!;
    expect(invalid.kind).toBe("invalid");
    expect(invalid.payload).toBe("{not json");
  });

  it("falls back to the registry when error data has no name", () => {
    const [, response] = buildTrace([
      { seq: 1, at: 0, direction: "in", client: "a", principal: "agent:a", message: { jsonrpc: "2.0", id: 1, method: "hal/read", params: {} } },
      { seq: 2, at: 0, direction: "out", client: "a", principal: "agent:a", message: { jsonrpc: "2.0", id: 1, error: { code: -32003, message: "no" } } },
    ]);
    expect(response!.head).toBe("error -32003 SCOPE_DENIED");
  });

  it("names a client by its clientInfo before the hub knows it, so initialize pairs with its result", () => {
    const rows = buildTrace([
      {
        seq: 1,
        at: 1792900000.5,
        direction: "in",
        client: null,
        principal: null,
        message: { jsonrpc: "2.0", id: 1, method: "hal/initialize", params: { clientInfo: { name: "print-watcher" } } },
      },
      { seq: 2, at: 1792900000.6, direction: "out", client: "print-watcher", principal: "agent:print-watcher", message: { jsonrpc: "2.0", id: 1, result: {} } },
    ]);
    expect(rows[0]!.client).toBe("print-watcher");
    expect(rows[0]!.outcome).toBe("granted");
    expect(rows[1]!.method).toBe("hal/initialize");
    expect(rows[1]!.startsExchange).toBe(false);
    expect(rows[0]!.at!.getTime()).toBe(1792900000500);
  });

  it("keeps rows in sequence order", () => {
    const shuffled = [...entries].reverse();
    expect(buildTrace(shuffled).map((row) => row.seq)).toEqual(entries.map((entry) => entry.seq));
  });
});

describe("filters", () => {
  const rows = buildTrace(entries);

  it("filters by client, device, method and outcome", () => {
    expect(filterRows(rows, NO_FILTERS)).toHaveLength(rows.length);
    expect(filterRows(rows, { ...NO_FILTERS, client: "lab-script" }).map((row) => row.seq)).toEqual([21, 22, 23, 24]);
    expect(filterRows(rows, { ...NO_FILTERS, device: "printer-cam" }).map((row) => row.seq)).toEqual([4, 5, 14, 15]);
    expect(filterRows(rows, { ...NO_FILTERS, method: "hal/action" }).map((row) => row.seq)).toEqual([16, 17, 18, 20]);
    expect(filterRows(rows, { ...NO_FILTERS, outcome: "error" }).map((row) => row.seq)).toEqual([11, 12, 13, 21, 22, 23, 24]);
  });

  it("lists the options found in the log", () => {
    const options = filterOptions(rows);
    expect(options.clients).toEqual(["lab-script", "print-watcher"]);
    expect(options.devices).toEqual(["printer", "printer-cam"]);
    expect(options.methods).toContain("hal/action");
    expect(options.methods).toContain("hal/blocked");
  });
});

describe("formatting", () => {
  it("renders the plain text trace from the design document", () => {
    const rows = buildTrace(entries).filter((row) => [9, 10, 11, 13, 18, 20].includes(row.seq));
    expect(plainTrace(rows)).toBe(
      [
        '-> hal/write    { "device": "printer", "channel": "bed_target", "value": 70, "unit": "degC" }',
        '<- result       { "status": "done", "device": "printer", "channel": "bed_target", "value": 70, "unit": "degC" }',
        "",
        '-> hal/write    { "device": "printer", "channel": "extruder_target", "value": 300, "unit": "degC" }',
        "<- error -32010 LIMIT_EXCEEDED",
        "               extruder_target 300 degC exceeds the limit of 260 degC (printer.hal.yaml, confirmed by owner 2026-10-24)",
        "",
        '-> hal/action   { "device": "printer", "action": "cancel" }',
        '<- result       { "status": "pending", "requestId": "fc100aa740c6f81b", "expiresInS": 300 }',
      ].join("\n"),
    );
  });

  it("tokenizes JSON for the syntax theme", () => {
    const tokens = tokenizeJson({ value: 60, ok: true, unit: "%", none: null, list: [1] });
    const types = tokens.map((token) => token.type);
    expect(types).toContain("key");
    expect(types).toContain("number");
    expect(types).toContain("boolean");
    expect(types).toContain("null");
    expect(tokens.map((token) => token.text).join("")).toBe('{ "value": 60, "ok": true, "unit": "%", "none": null, "list": [1] }');
  });

  it("truncates very long payloads", () => {
    const tokens = tokenizeJson({ text: "x".repeat(100) }, 40);
    expect(tokens[tokens.length - 1]!.type).toBe("more");
  });

  it("reads principals as labels or objects", () => {
    expect(principalInfo("agent:print-watcher")).toEqual({ kind: "agent", name: "print-watcher", label: "agent:print-watcher" });
    expect(principalInfo({ kind: "human", name: "owner" }).label).toBe("human:owner");
    expect(principalInfo(null).kind).toBe("unknown");
  });

  it("formats times to the millisecond", () => {
    const date = new Date(2026, 9, 24, 14, 2, 1, 4);
    expect(formatTime(date)).toBe("14:02:01.004");
  });
});
