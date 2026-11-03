/**
 * The How it works chart, an illustration of OpenHAL's three outcomes on a robotic arm, made in
 * Claude Design and shipped as four static images in docs/assets, wide and narrow in each theme.
 * The labels here are the chart's own, word for word, for the chart's text alternative.
 */

/** The chart's four image files in docs/assets. */
export const CHART_FILES = ["how-it-works-wide-light.png", "how-it-works-wide-dark.png", "how-it-works-narrow-light.png", "how-it-works-narrow-dark.png"] as const;

/** Each shape's size in CSS pixels. The files are 2x exports of these sizes. */
export const CHART_SIZES = { wide: { width: 884, height: 544 }, narrow: { width: 416, height: 552 } } as const;

/** One path of the chart, its branch label, the values under the branch and the outcomes in order. */
export interface HowPath {
  label: string;
  values: string[];
  outcomes: string[];
}

export interface HowChart {
  agent: string;
  request: string;
  hub: string;
  checks: string;
  paths: HowPath[];
}

export const HOW_CHART: HowChart = {
  agent: "Agent",
  request: "request",
  hub: "OpenHAL hub",
  checks: "checks the device file",
  paths: [
    { label: "Under the limit", values: ["shoulder to 20°", "limit 30°"], outcomes: ["Arm moves"] },
    { label: "Over the limit", values: ["shoulder to 45°", "limit 30°"], outcomes: ["Blocked"] },
    { label: "Needs approval", values: ["turn motors on"], outcomes: ["You approve", "Arm moves"] },
  ],
};

/** The line before the paths, for screen readers. */
export const chartLead = (chart: HowChart = HOW_CHART): string => `${chart.agent} sends a ${chart.request}, and the ${chart.hub} ${chart.checks}.`;

/** One path as a sentence for screen readers, its label, its values and its outcomes in order. */
export const pathText = (path: HowPath): string => `${[path.label, ...path.values].join(", ")}. ${path.outcomes.join(", then ")}.`;
