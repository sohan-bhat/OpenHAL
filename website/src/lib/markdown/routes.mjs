import { readVersions, slugOf } from "../spec-meta.mjs";

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
  { repo: "spec/SPEC.md", route: "/docs/device-file-format/", group: "Reference" },
  { repo: "spec/CHANGELOG.md", route: "/docs/device-file-changelog/", group: "Reference" },
  { repo: "spec/MHS-MAPPING.md", route: "/docs/mhs-mapping/", group: "Reference" },
  { repo: "spec/FIRMWARE-PROTOCOL.md", route: "/docs/firmware-protocol/", group: "Firmware" },
  { repo: "firmware/arduino/OpenHAL/README.md", route: "/docs/arduino-library/", group: "Firmware" },
  { repo: "docs/interfaces/PYTHON.md", route: "/sdks/python/", group: "SDKs" },
  { repo: "docs/drivers/COVERAGE.md", route: "/drivers/coverage/", group: "Drivers" },
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
  if (spec) {
    const slug = slugOf(spec[2]);
    return slug ? `/spec/${spec[1]}/${slug}/` : `/spec/${spec[1]}/`;
  }
  if (path === "spec/versions.json") {
    const { latest } = readVersions();
    return latest ? `/spec/${latest}/` : null;
  }
  return null;
}

export function groupFor(repoPath) {
  const fixed = FIXED_ROUTES.find((item) => item.repo === repoPath);
  if (fixed) return fixed.group;
  if (repoPath.startsWith("docs/drivers/")) return "Drivers";
  return "Reference";
}
