import { storyFacts, type StoryFacts } from "./story/facts";

export interface Shot {
  file: string;
  caption: string;
  crop: { x: number; y: number; w: number; h: number };
  alt: string;
}

/** The Inspector page's screenshots, each with the words that say what it shows, from the record. */
export function inspectorShots(facts: StoryFacts = storyFacts()): Shot[] {
  return [
    {
      file: "inspector-device",
      caption: "The printer",
      crop: { x: 316, y: 128, w: 984, h: 772 },
      alt: `The Inspector's device pane for the ${facts.printer.name}, with its readings, the latest frame from its webcam, bed_target limited to ${facts.bed.max} and extruder_target limited to ${facts.nozzle.max}`,
    },
    {
      file: "inspector-log",
      caption: "The message log",
      crop: { x: 316, y: 126, w: 1100, h: 774 },
      alt: `The Inspector's message log with the agent's requests to the printer, a ${facts.nozzle.value} nozzle answered by error ${facts.nozzle.refusal.code} ${facts.nozzle.refusal.name}, and the cancel answered ${facts.cancel.status} until a person decides`,
    },
    {
      file: "inspector-stopped",
      caption: "Stopped",
      crop: { x: 0, y: 119, w: 1040, h: 48 },
      alt: "The Inspector's stop banner, saying every command is refused with error -32014 STOPPED until a person lifts the stop with UNLOCK",
    },
  ];
}
