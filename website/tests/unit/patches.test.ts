import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import pkg from "../../package.json";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

describe("patched dependencies", () => {
  it("name the version the site installs, so an upgrade has to bring each patch along", () => {
    const patched = Object.keys(pkg.pnpm.patchedDependencies);
    expect(patched.length).toBeGreaterThan(0);
    for (const key of patched) {
      const at = key.lastIndexOf("@");
      const name = key.slice(0, at) as keyof typeof pkg.dependencies;
      expect(pkg.dependencies[name], key).toBe(key.slice(at + 1));
    }
  });

  it("let cmdk name the active row again when the search palette sets it, so no stale row is announced", () => {
    for (const file of ["index.mjs", "index.js"]) {
      const source = read(`../../node_modules/cmdk/dist/${file}`);
      const effect = /\(\(\)=>\{if\((\w+)!==void 0\)\{let (\w+)=\1\.trim\(\);(\w+)\.current\.value=\2,(\w+)\(7,\(\)=>\{var \w+;\3\.current\.selectedItemId=/;
      expect(effect.test(source), file).toBe(true);
    }
  });
});
