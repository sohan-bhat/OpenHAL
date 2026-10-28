import { describe, expect, it } from "vitest";
import { versionRows } from "../../src/lib/versions";

const versions = [
  { version: "2026-12-01", status: "draft", latest: false },
  { version: "2026-10-24", status: "", latest: true },
];
const pages = [
  { version: "2026-12-01", slug: "" },
  { version: "2026-12-01", slug: "basic/messages" },
  { version: "2026-12-01", slug: "routines" },
  { version: "2026-10-24", slug: "" },
  { version: "2026-10-24", slug: "basic/messages" },
];

describe("the header's version picker", () => {
  it("shows a spec page's own version and links to the same section in each other version", () => {
    const { current, rows } = versionRows("/spec/2026-12-01/basic/messages/", versions, "2026-10-24", pages);
    expect(current).toBe("2026-12-01");
    expect(rows).toEqual([
      { version: "2026-12-01", href: "/spec/2026-12-01/basic/messages/", note: "draft", current: true },
      { version: "2026-10-24", href: "/spec/2026-10-24/basic/messages/", note: "latest", current: false },
    ]);
  });

  it("links to a version's first page when that version has no such section", () => {
    const { rows } = versionRows("/spec/2026-12-01/routines/", versions, "2026-10-24", pages);
    expect(rows.map((row) => row.href)).toEqual(["/spec/2026-12-01/routines/", "/spec/2026-10-24/"]);
  });

  it("reads the latest alias as the latest version", () => {
    const { current, rows } = versionRows("/spec/latest/basic/messages/", versions, "2026-10-24", pages);
    expect(current).toBe("2026-10-24");
    expect(rows.find((row) => row.current)!.href).toBe("/spec/2026-10-24/basic/messages/");
  });

  it("shows the latest version everywhere else and links to each version's spec", () => {
    for (const path of ["/", "/docs/quickstart/", "/spec/playground/", "/spec/errors/", "/drivers/"]) {
      const { current, rows } = versionRows(path, versions, "2026-10-24", pages);
      expect(current, path).toBe("2026-10-24");
      expect(rows.map((row) => [row.href, row.current]), path).toEqual([
        ["/spec/2026-12-01/", false],
        ["/spec/2026-10-24/", true],
      ]);
    }
  });

  it("names each version's status in words", () => {
    const { rows } = versionRows("/", [{ version: "2026-10-24", status: "draft", latest: true }], "2026-10-24", []);
    expect(rows[0].note).toBe("latest draft");
  });
});
