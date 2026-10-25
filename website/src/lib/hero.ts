import deskFanText from "../../../spec/examples/desk-fan-confirmed.hal.yaml?raw";
import { HERO_CHANNEL, HERO_DEVICE, HERO_FIRST_REQUEST, HERO_START_TEMPERATURE } from "./hero-shared";
import { Kernel, agent, loadDeviceFile, type Decision, type DeviceFile } from "./kernel";
import { parseDeviceYaml } from "./kernel/yaml";

export function heroRaw(): unknown {
  return JSON.parse(JSON.stringify(parseDeviceYaml(deskFanText), (_key, value) => (typeof value === "bigint" ? Number(value) : value)));
}

export function heroFile(): DeviceFile {
  return loadDeviceFile(parseDeviceYaml(deskFanText));
}

export function heroFirstDecision(): Decision {
  let now = 1000;
  const kernel = new Kernel(() => now);
  kernel.register(heroFile(), { temperature: HERO_START_TEMPERATURE });
  kernel.connect(HERO_DEVICE);
  now += 10;
  return kernel.execute({ kind: "write", device: HERO_DEVICE, channel: HERO_CHANNEL, value: HERO_FIRST_REQUEST }, agent("claude", "control_low"));
}
