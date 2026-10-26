import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import api from "../../src/content/generated/python-api.json";
import { formatSignature, inlineCode, methodGuide, placeOf } from "../../src/lib/python-api";

const guide = methodGuide(readFileSync(fileURLToPath(new URL("../../../docs/interfaces/PYTHON.md", import.meta.url)), "utf8"));
const client = api.groups.flatMap((group) => group.items).find((item) => item.name === "Client") as { methods: Array<{ name: string }> };

describe("the Python reference", () => {
  it("puts every Client method in a group from the Python guide, besides close", () => {
    const loose = client.methods.filter((method) => !guide.places.has(method.name)).map((method) => method.name);
    expect(loose).toEqual(["close"]);
    expect(placeOf(guide, "read").group).toBe("Reading and control");
    expect(placeOf(guide, "approve").route).toContain("POST /v1/confirmations/{id}/approve");
    expect(placeOf(guide, "call").group).toBe("Any route");
  });

  it("breaks long signatures one parameter per line and leaves short ones alone", () => {
    expect(formatSignature("status() -> HubStatus")).toBe("status() -> HubStatus");
    expect(formatSignature("audit(*, device: str | None = None, status: str | None = None, limit: int = 200) -> list[AuditEntry]")).toBe(
      "audit(\n    *,\n    device: str | None = None,\n    status: str | None = None,\n    limit: int = 200,\n) -> list[AuditEntry]",
    );
    expect(formatSignature("read(device: str, channel: str | None = None, items: Mapping[str, Any] = {}) -> Reading").split("\n")).toHaveLength(5);
  });

  it("shows backticks in docstrings as code", () => {
    expect(inlineCode("With `check` it calls `/v1/whoami` <first>.")).toBe("With <code>check</code> it calls <code>/v1/whoami</code> &lt;first&gt;.");
  });
});
