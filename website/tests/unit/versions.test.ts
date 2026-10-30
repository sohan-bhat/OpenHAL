import { describe, expect, it } from "vitest";
import { compareVersions, parseVersions, versionLabel, versionOfFolder } from "../../src/lib/spec-meta.mjs";
import { versionMenu, versionRows } from "../../src/lib/versions";

const versions = [
  { version: "0.2", status: "draft", latest: false },
  { version: "0.1", status: "", latest: true },
];
const pages = [
  { version: "0.2", slug: "" },
  { version: "0.2", slug: "basic/messages" },
  { version: "0.2", slug: "routines" },
  { version: "0.1", slug: "" },
  { version: "0.1", slug: "basic/messages" },
];

describe("spec versions", () => {
  it("compare as numbers, so 0.10 is newer than 0.9", () => {
    expect(["0.9", "0.10", "1.0", "0.1"].sort(compareVersions)).toEqual(["0.1", "0.9", "0.10", "1.0"]);
  });

  it("read v0.1 as a folder and show it with its v", () => {
    expect(versionOfFolder("v0.1")).toBe("0.1");
    expect(versionOfFolder("v0.10")).toBe("0.10");
    for (const name of ["0.1", "2026-10-24", "v1", "vx.1", "examples"]) expect(versionOfFolder(name), name).toBeNull();
    expect(versionLabel("0.1")).toBe("v0.1");
  });

  it("list versions.json newest first, add folders it leaves out and drop dates", () => {
    const parsed = parseVersions({ latest: "0.9", versions: [{ version: "0.9", status: "final" }, { version: "2026-10-24", status: "draft" }] }, ["v0.10", "v0.9", "2026-10-24", "examples"]);
    expect(parsed.latest).toBe("0.9");
    expect(parsed.versions).toEqual([
      { version: "0.10", status: "", latest: false },
      { version: "0.9", status: "final", latest: true },
    ]);
  });
});

describe("the header's version picker", () => {
  it("shows a spec page's own version and links to the same section in each other version", () => {
    const { current, label, rows } = versionRows("/spec/v0.2/basic/messages/", versions, "0.1", pages);
    expect(current).toBe("0.2");
    expect(label).toBe("v0.2");
    expect(rows).toEqual([
      { version: "0.2", label: "v0.2", href: "/spec/v0.2/basic/messages/", note: "draft", current: true },
      { version: "0.1", label: "v0.1", href: "/spec/v0.1/basic/messages/", note: "latest", current: false },
    ]);
  });

  it("links to a version's first page when that version has no such section", () => {
    const { rows } = versionRows("/spec/v0.2/routines/", versions, "0.1", pages);
    expect(rows.map((row) => row.href)).toEqual(["/spec/v0.2/routines/", "/spec/v0.1/"]);
  });

  it("shows the latest version everywhere else and links to each version's spec", () => {
    for (const path of ["/", "/docs/quickstart/", "/spec/playground/", "/spec/errors/", "/drivers/", "/spec/v9.9/"]) {
      const { current, rows } = versionRows(path, versions, "0.1", pages);
      expect(current, path).toBe("0.1");
      expect(
        rows.map((row) => [row.href, row.current]),
        path,
      ).toEqual([
        ["/spec/v0.2/", false],
        ["/spec/v0.1/", true],
      ]);
    }
  });

  it("names each version's status in words", () => {
    const { rows } = versionRows("/", [{ version: "0.1", status: "draft", latest: true }], "0.1", []);
    expect(rows[0].note).toBe("latest draft");
  });

  it("is a plain label while one version exists and a menu once there are two", () => {
    expect(versionMenu(versionRows("/", [{ version: "0.1", status: "draft", latest: true }], "0.1", []).rows)).toBe(false);
    expect(versionMenu(versionRows("/", versions, "0.1", pages).rows)).toBe(true);
  });
});
