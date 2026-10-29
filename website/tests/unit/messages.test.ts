import { describe, expect, it } from "vitest";
import { loadScenario } from "../../src/lib/scenario";
import { auditLog, compactJson, messages } from "../../src/lib/story/messages";

const record = loadScenario().record as Record<string, any>;

describe("the example page's messages", () => {
  it("keeps short objects on one line and breaks long ones, as valid JSON", () => {
    expect(compactJson({ status: "done", value: 70 })).toBe('{ "status": "done", "value": 70 }');
    const request = { method: "hal/action", params: { device: "printer", action: "pause" } };
    expect(compactJson(request)).toBe('{\n  "method": "hal/action",\n  "params": { "device": "printer", "action": "pause" }\n}');
    const large = { result: { device: "printer-cam", channel: "frame", value: { mimeType: "image/jpeg", bytes: 19409, width: 640, height: 480 }, unit: null, suspect: false } };
    const text = compactJson(large);
    expect(text.split("\n").length).toBeGreaterThan(3);
    expect(JSON.parse(text)).toEqual(large);
    for (const line of text.split("\n")) expect(line.length).toBeLessThanOrEqual(64);
  });

  it("lists every request of the run with the hub's answer, in order, as the record holds them", () => {
    const sent = messages();
    expect(sent.map((message) => message.id)).toEqual(record.exchanges.map((exchange: { id: string }) => exchange.id));
    for (const [index, message] of sent.entries()) {
      const exchange = record.exchanges[index];
      expect(JSON.parse(message.request)).toEqual({ method: exchange.request.method, params: exchange.request.params });
      expect(JSON.parse(message.response)).toEqual(exchange.error ? { error: exchange.error } : { result: exchange.result });
      expect(message.note).toMatch(/^[A-Z].*\.$/);
      expect(message.by).toBe(exchange.by);
    }
    expect(sent.map((message) => message.method)).toEqual(["hal/read", "hal/write", "hal/write", "hal/read", "hal/action", "hal/action", "hal/confirmations/approve"]);
    expect(sent.filter((message) => message.refused).map((message) => message.id)).toEqual(["nozzle-too-hot"]);
  });

  it("ends on the audit log, newest first, with its counts", () => {
    const audit = auditLog();
    expect(audit.command).toBe("uv run openhal log -n 8");
    expect(audit.entries.map((entry) => entry.seq)).toEqual([13, 12, 11, 10, 9, 8, 7, 6]);
    expect(audit.entries.map((entry) => entry.status)).toEqual(record.audit.entries.map((entry: { status: string }) => entry.status));
    expect(audit.counts).toBe(`${record.audit.counts.requests} requests, ${record.audit.counts.refused} refused, ${record.audit.counts.confirmed_by_a_person} confirmed by a person.`);
  });
});
