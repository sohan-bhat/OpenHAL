import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { FLOW_NODES, diagramLabels, flowNodes, readFlow } from "../../src/lib/flow";

const root = fileURLToPath(new URL("../../../", import.meta.url));

function visibleTexts(svg: string): string[] {
  return [...svg.matchAll(/<text[^>]*>([\s\S]*?)<\/text>/g)].map((match) => {
    const parts = [...match[1].matchAll(/<tspan[^>]*>([\s\S]*?)<\/tspan>/g)].map((part) => part[1]);
    return (parts.length ? parts.join(" ") : match[1]).replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
  });
}

describe("the flow diagram's part buttons", () => {
  const flow = readFlow(root);

  it("finds a label in the diagram for every part", () => {
    expect(flow).not.toBeNull();
    for (const variant of [flow!.wide.light, flow!.wide.dark, flow!.narrow?.light, flow!.narrow?.dark].filter(Boolean) as string[]) {
      expect([...diagramLabels(variant).keys()].sort()).toEqual(FLOW_NODES.map((node) => node.key).sort());
    }
  });

  it("use the diagram's own words", () => {
    const texts = visibleTexts(flow!.wide.light);
    for (const node of flowNodes(flow!.wide.light)) expect(texts).toContain(node.label);
  });

  it("read the same in every variant", () => {
    const wide = flowNodes(flow!.wide.light).map((node) => node.label);
    for (const variant of [flow!.wide.dark, flow!.narrow?.light, flow!.narrow?.dark].filter(Boolean) as string[]) {
      expect(flowNodes(variant).map((node) => node.label)).toEqual(wide);
    }
  });
});
