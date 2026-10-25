export const FIXED_ROUTES = [
  { repo: "docs/guide/quickstart.md", route: "/docs/quickstart/", group: "Guides" },
  { repo: "docs/guide/concepts.md", route: "/docs/concepts/", group: "Guides" },
  { repo: "docs/guide/contributing-a-device-file.md", route: "/docs/contributing-a-device-file/", group: "Guides" },
  { repo: "docs/guide/conformance.md", route: "/docs/conformance/", group: "Guides" },
  { repo: "docs/guide/driver-writer.md", route: "/docs/driver-writer/", group: "Guides", optional: true },
  { repo: "docs/guide/faq.md", route: "/docs/faq/", group: "Guides" },
  { repo: "docs/SAFETY.md", route: "/docs/safety/", group: "Reference" },
  { repo: "docs/ARCHITECTURE.md", route: "/docs/architecture/", group: "Reference" },
  { repo: "docs/interfaces/CLI.md", route: "/docs/cli/", group: "Interfaces" },
  { repo: "docs/interfaces/MCP.md", route: "/docs/mcp/", group: "Interfaces" },
  { repo: "docs/interfaces/PYTHON.md", route: "/docs/python/", group: "Interfaces" },
  { repo: "spec/FIRMWARE-PROTOCOL.md", route: "/docs/firmware-protocol/", group: "Firmware" },
  { repo: "firmware/arduino/OpenHAL/README.md", route: "/docs/arduino-library/", group: "Firmware" },
  { repo: "spec/SPEC.md", route: "/spec/", group: "Spec" },
  { repo: "spec/CHANGELOG.md", route: "/spec/changelog/", group: "Spec" },
  { repo: "spec/MHS-MAPPING.md", route: "/spec/mhs-mapping/", group: "Spec" },
];

export const DOC_PATTERNS = [
  ...FIXED_ROUTES.map((item) => item.repo),
  "docs/drivers/*.md",
  "spec/versions/*/SPEC.md",
];

export function routeFor(repoPath) {
  const path = repoPath.replace(/^\.?\//, "");
  const fixed = FIXED_ROUTES.find((item) => item.repo === path);
  if (fixed) return fixed.route;
  const driver = /^docs\/drivers\/([^/]+)\.md$/.exec(path);
  if (driver) return `/docs/drivers/${driver[1].toLowerCase()}/`;
  const version = /^spec\/versions\/([^/]+)\/SPEC\.md$/.exec(path);
  if (version) return `/spec/${version[1]}/`;
  return null;
}

export function groupFor(repoPath) {
  const fixed = FIXED_ROUTES.find((item) => item.repo === repoPath);
  if (fixed) return fixed.group;
  if (repoPath.startsWith("docs/drivers/")) return "Drivers";
  if (repoPath.startsWith("spec/versions/")) return "Spec versions";
  return "Reference";
}
