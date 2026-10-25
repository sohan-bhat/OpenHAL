import { existsSync } from "node:fs";
import { join } from "node:path";
import { sourceUrl } from "../../config/repo.mjs";
import { REPO_ROOT, readVersions, slugOf } from "../spec-meta.mjs";

export const FIXED_ROUTES = [
  { repo: "docs/guide/quickstart.md", route: "/docs/quickstart/", group: "Get started" },
  { repo: "docs/guide/concepts.md", route: "/docs/concepts/", group: "Get started" },
  { repo: "docs/guide/tutorials/connect-claude.md", route: "/docs/tutorials/connect-claude/", group: "Tutorials" },
  { repo: "docs/guide/tutorials/add-a-device.md", route: "/docs/tutorials/add-a-device/", group: "Tutorials" },
  { repo: "docs/guide/tutorials/write-a-driver.md", route: "/docs/tutorials/write-a-driver/", group: "Tutorials" },
  { repo: "docs/guide/tutorials/write-a-routine.md", route: "/docs/tutorials/write-a-routine/", group: "Tutorials" },
  { repo: "docs/guide/faq.md", route: "/docs/faq/", group: "Get started" },
  { repo: "docs/guide/conformance.md", route: "/docs/conformance/", group: "Reference" },
  { repo: "docs/SAFETY.md", route: "/docs/safety/", group: "Reference" },
  { repo: "docs/ARCHITECTURE.md", route: "/docs/architecture/", group: "Reference" },
  { repo: "docs/interfaces/CLI.md", route: "/docs/cli/", group: "Reference" },
  { repo: "docs/interfaces/MCP.md", route: "/docs/mcp/", group: "Reference" },
  { repo: "docs/drivers/WRITING-A-DRIVER.md", route: "/docs/writing-a-driver/", group: "Reference" },
  { repo: "spec/MHS-MAPPING.md", route: "/docs/mhs-mapping/", group: "Reference" },
  { repo: "spec/FIRMWARE-PROTOCOL.md", route: "/docs/firmware-protocol/", group: "Firmware" },
  { repo: "firmware/arduino/OpenHAL/README.md", route: "/docs/arduino-library/", group: "Firmware" },
  { repo: "docs/interfaces/PYTHON.md", route: "/sdks/python/", group: "SDKs" },
  { repo: "docs/drivers/COVERAGE.md", route: "/drivers/coverage/", group: "Drivers" },
  { repo: "spec/VERSIONING.md", route: "/spec/versioning/", group: "Specification" },
  { repo: "spec/ERRORS.md", route: "/spec/errors/", group: "Specification" },
  { repo: "spec/CONFORMANCE.md", route: "/spec/conformance/", group: "Specification" },
  { repo: "spec/GLOSSARY.md", route: "/spec/glossary/", group: "Specification" },
];

export const DOC_PATTERNS = [...FIXED_ROUTES.map((item) => item.repo), "docs/drivers/*.md"];

export const SPEC_PATTERN = "spec/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]/**/*.md";

export function routeFor(repoPath) {
  const path = repoPath.replace(/^\.?\//, "").split("#")[0];
  const fixed = FIXED_ROUTES.find((item) => item.repo === path);
  if (fixed) return fixed.route;
  const driver = /^docs\/drivers\/([a-z0-9-]+)\.md$/.exec(path);
  if (driver) return `/drivers/${driver[1]}/`;
  const spec = /^spec\/(\d{4}-\d{2}-\d{2})\/(.+\.md)$/.exec(path);
  if (spec && existsSync(join(REPO_ROOT, path))) {
    const slug = slugOf(spec[2]);
    return slug ? `/spec/${spec[1]}/${slug}/` : `/spec/${spec[1]}/`;
  }
  const pointer = SPEC_POINTERS[path];
  if (pointer !== undefined) {
    const { latest } = readVersions();
    if (latest) return `/spec/${latest}/${pointer}`;
  }
  return null;
}

const SPEC_POINTERS = {
  "spec/versions.json": "",
  "spec/SPEC.md": "device-files/",
  "spec/CHANGELOG.md": "changelog/",
};

export function linkFor(repoPath) {
  const route = routeFor(repoPath);
  if (route) return route;
  const path = repoPath.replace(/^\.?\//, "").split("#")[0];
  if (path && !path.startsWith("..") && existsSync(join(REPO_ROOT, path))) return sourceUrl(path);
  return null;
}

export function groupFor(repoPath) {
  const fixed = FIXED_ROUTES.find((item) => item.repo === repoPath);
  if (fixed) return fixed.group;
  if (repoPath.startsWith("docs/drivers/")) return "Drivers";
  return "Reference";
}
