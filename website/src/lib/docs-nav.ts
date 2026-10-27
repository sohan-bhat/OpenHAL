import { getCollection } from "astro:content";
import type { SideGroup } from "./nav-types";
import { FIXED_ROUTES } from "./markdown/routes.mjs";

const DOC_GROUPS = ["Get started", "Tutorials", "Reference", "Firmware"];

const SHORT: Record<string, string> = {
  "OpenHAL device file specification, version 0.1": "Device file format",
  "Command line reference": "Command line",
  "MCP server": "MCP server",
  "Spec changelog": "Device file changelog",
  "Mapping to the Model Hardware Standard": "MHS mapping",
  "OpenHAL firmware protocol, version 1": "Firmware protocol",
  "Writing a driver": "Driver contract",
};

export const DOC_SUMMARIES: Record<string, string> = {
  "/docs/quickstart/": "Run the print babysitter demo, then a hub you control.",
  "/docs/install/": "Install from a clone or as a tool, run the hub as a service, or set up a Raspberry Pi.",
  "/docs/concepts/": "The hub, device files, the safety kernel, drivers, grants and errors, in one page.",
  "/docs/faq/": "Short answers on safety, agents, limits, firmware and privacy.",
  "/docs/tutorials/connect-claude/": "Give Claude an agent token, and Claude reaches the hub through openhal mcp.",
  "/docs/tutorials/add-a-device/": "Create a device file, validate the file, confirm the limits and share the file.",
  "/docs/tutorials/build-a-driver/": "Build a driver for a simulated bench lamp and pass the conformance suite.",
  "/docs/tutorials/create-a-routine/": "Automate a device with triggers and steps that the kernel checks.",
  "/docs/library/": "How the hub matches a device to a library file and how a person confirms the file.",
  "/docs/conformance/": "The checks every driver passes before the driver ships.",
  "/docs/safety/": "What the hub guarantees, how the kernel enforces each guarantee, and what OpenHAL does not cover.",
  "/docs/architecture/": "One hub process, one deterministic kernel, and the thin clients around the hub.",
  "/docs/cli/": "Every openhal command, its options and its exit codes.",
  "/docs/mcp/": "The tools and prompts the MCP server gives an agent.",
  "/docs/writing-a-driver/": "The package, class, tests and catalog entry a new driver needs.",
  "/docs/mhs-mapping/": "How each OpenHAL concept maps to what is public about MHS.",
  "/docs/firmware-protocol/": "The wire protocol a board running the OpenHAL Arduino library speaks.",
  "/docs/arduino-library/": "Make a sketch describe itself so the hub builds its device file.",
};

export function docTitle(entry: { id: string; body?: string; data: Record<string, unknown> }): string {
  if (typeof entry.data.title === "string") return entry.data.title;
  const match = /^# (.+)$/m.exec(entry.body ?? "");
  return match ? match[1].replace(/`/g, "").trim() : entry.id;
}

export function navTitle(title: string): string {
  return SHORT[title] ?? title;
}

/** Pages outside docs/ that the Docs section lists, since the main navigation leaves them out. */
export const TOOLS: SideGroup = {
  name: "SDKs and Inspector",
  items: [
    { title: "SDKs", href: "/sdks/", summary: "The Python SDK for the hub protocol, with its API reference." },
    { title: "Inspector", href: "/inspector/", summary: "The hub's dashboard, with every device and every message, and STOP." },
  ],
};

export async function docsSidebar(): Promise<SideGroup[]> {
  const entries = new Map((await getCollection("docs")).map((entry) => [entry.id, entry]));
  const groups = DOC_GROUPS.map((name) => ({
    name,
    items: FIXED_ROUTES.filter((item) => item.group === name && entries.has(item.repo)).map((item) => ({
      title: navTitle(docTitle(entries.get(item.repo)!)),
      href: item.route,
      summary: DOC_SUMMARIES[item.route],
    })),
  })).filter((group) => group.items.length > 0);
  const reference = groups.findIndex((group) => group.name === "Reference");
  groups.splice(reference < 0 ? groups.length : reference + 1, 0, TOOLS);
  return groups;
}
