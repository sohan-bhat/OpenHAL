import captures from "../data/inspector-captures.json";
import { storyFacts, type StoryFacts } from "./story/facts";

export interface Shot {
  file: string;
  caption: string;
  crop: { x: number; y: number; w: number; h: number };
  alt: string;
}

const listed = (captures as { shots?: Shot[] }).shots;

/**
 * The Inspector page's screenshots, each with the words that say what it shows. The capture
 * script's own list in inspector-captures.json wins when it has one, since the script knows what
 * each image holds. Otherwise the page shows the device, the message log and the stop, described
 * with the record's numbers.
 */
export function inspectorShots(facts: StoryFacts = storyFacts(), shots: Shot[] | undefined = listed): Shot[] {
  if (shots?.length) return shots;
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
      alt: `The Inspector's message log with the agent's requests to the printer, the request for a nozzle temperature of ${facts.nozzle.value} refused with error ${facts.nozzle.refusal.code} ${facts.nozzle.refusal.name}, and the cancel left ${facts.cancel.status} until a person approves or rejects the cancel`,
    },
    {
      file: "inspector-stopped",
      caption: "Stopped",
      crop: { x: 0, y: 119, w: 1040, h: 48 },
      alt: "The Inspector's stop banner, saying every command is refused with error -32014 STOPPED until a person lifts the stop with UNLOCK",
    },
  ];
}
