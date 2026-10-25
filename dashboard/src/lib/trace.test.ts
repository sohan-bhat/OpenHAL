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

  it("draws a request as a right arrow with its method", () => {
    const write = rows.find((row) => row.seq === 4)!;
    expect(write.arrow).toBe("right");
    expect(write.kind).toBe("request");
    expect(write.head).toBe("hal/write");
    expect(write.tone).toBe("method");
    expect(stringifyCompact(write.payload)).toBe('{ "device": "desk-fan", "channel": "fan_speed", "value": "150 %" }');
  });

  it("names a blocked write with the registry code and name and its reason", () => {
    const error = rows.find((row) => row.seq === 5)!;
    expect(error.arrow).toBe("left");
    expect(error.head).toBe("error -32010 LIMIT_EXCEEDED");
    expect(error.errorName).toBe("LIMIT_EXCEEDED");
    expect(error.reason).toBe(
      "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)",
    );
    expect(error.method).toBe("hal/write");
    expect(error.devices).toEqual(["desk-fan"]);
    expect(error.hasPayload).toBe(false);
  });

  it("pairs responses with requests to give the request its outcome", () => {
    expect(rows.find((row) => row.seq === 4)!.outcome).toBe("error");
    expect(rows.find((row) => row.seq === 7)!.outcome).toBe("granted");
    expect(rows.find((row) => row.seq === 9)!.outcome).toBe("pending");
    expect(rows.find((row) => row.seq === 8)!.method).toBe("hal/write");
  });

  it("marks a pending result as needing confirmation, not as granted", () => {
    const pending = rows.find((row) => row.seq === 10)!;
    expect(pending.head).toBe("result");
    expect(pending.tone).toBe("pending");
    expect(pending.devices).toEqual(["curing-heater"]);
  });

  it("draws notifications with dashed arrows", () => {
    expect(rows.find((row) => row.seq === 3)!.arrow).toBe("right-dashed");
    const value = rows.find((row) => row.seq === 11)!;
    expect(value.arrow).toBe("left-dashed");
    expect(value.kind).toBe("notification");
    const blocked = rows.find((row) => row.seq === 6)!;
    expect(blocked.outcome).toBe("error");
    expect(blocked.errorName).toBe("LIMIT_EXCEEDED");
  });

  it("keeps text that is not JSON-RPC as an invalid row", () => {
    const invalid = rows.find((row) => row.seq === 12)!;
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
        message: { jsonrpc: "2.0", id: 1, method: "hal/initialize", params: { clientInfo: { name: "bench-agent" } } },
      },
      { seq: 2, at: 1792900000.6, direction: "out", client: "bench-agent", principal: "agent:bench-agent", message: { jsonrpc: "2.0", id: 1, result: {} } },
    ]);
    expect(rows[0]!.client).toBe("bench-agent");
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
    expect(filterRows(rows, { ...NO_FILTERS, client: "lab-script" }).map((row) => row.seq)).toEqual([12]);
    expect(filterRows(rows, { ...NO_FILTERS, device: "curing-heater" }).map((row) => row.seq)).toEqual([9, 10]);
    expect(filterRows(rows, { ...NO_FILTERS, method: "hal/write" }).map((row) => row.seq)).toEqual([4, 5, 7, 8]);
    expect(filterRows(rows, { ...NO_FILTERS, outcome: "error" }).map((row) => row.seq)).toEqual([4, 5, 6, 12]);
  });

  it("lists the options found in the log", () => {
    const options = filterOptions(rows);
    expect(options.clients).toEqual(["bench-agent", "inspector", "lab-script"]);
    expect(options.devices).toEqual(["curing-heater", "desk-fan"]);
    expect(options.methods).toContain("hal/write");
    expect(options.methods).toContain("hal/blocked");
  });
});

describe("formatting", () => {
  it("renders the plain text trace from the design document", () => {
    const rows = buildTrace(entries).filter((row) => [4, 5, 7, 8].includes(row.seq));
    expect(plainTrace(rows)).toBe(
      [
        '-> hal/write    { "device": "desk-fan", "channel": "fan_speed", "value": "150 %" }',
        "<- error -32010 LIMIT_EXCEEDED",
        "               fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)",
        "",
        '-> hal/write    { "device": "desk-fan", "channel": "fan_speed", "value": "60 %" }',
        '<- result       { "status": "done", "device": "desk-fan", "channel": "fan_speed", "value": 60, "unit": "%" }',
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
    expect(principalInfo("agent:bench-agent")).toEqual({ kind: "agent", name: "bench-agent", label: "agent:bench-agent" });
    expect(principalInfo({ kind: "human", name: "sohan" }).label).toBe("human:sohan");
    expect(principalInfo(null).kind).toBe("unknown");
  });

  it("formats times to the millisecond", () => {
    const date = new Date(2026, 9, 24, 14, 2, 1, 4);
    expect(formatTime(date)).toBe("14:02:01.004");
  });
});
