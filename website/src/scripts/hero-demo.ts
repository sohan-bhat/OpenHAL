import { HERO_CHANNEL, HERO_DEVICE, HERO_START_TEMPERATURE, cliLine, trackPercent } from "../lib/hero-shared";
import { Kernel, UnitError, agent, convert, effectiveLimits, human, loadDeviceFile, parseQuantity, type Decision } from "../lib/kernel";

const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function setup(root: HTMLElement): void {
  const q = <T extends Element>(selector: string) => root.querySelector<T>(selector)!;
  const file = loadDeviceFile(JSON.parse(q<HTMLScriptElement>("[data-hero-file]").textContent ?? "{}"));
  const spec = file.write[HERO_CHANNEL];
  const kernel = new Kernel();
  kernel.register(file, { temperature: HERO_START_TEMPERATURE });
  kernel.connect(HERO_DEVICE);
  const claude = agent("claude", "control_low");
  const owner = human("you");

  const track = q<HTMLElement>("[data-track]");
  const thumb = q<HTMLElement>("[data-thumb]");
  const fill = q<HTMLElement>("[data-fill]");
  const rate = q<HTMLElement>("[data-rate]");
  const attempt = q<HTMLElement>("[data-attempt]");
  const maxLine = q<HTMLElement>("[data-limit-max]");
  const minLine = q<HTMLElement>("[data-limit-min]");
  const reason = q<HTMLElement>("[data-reason]");
  const fanReadout = q<HTMLElement>("[data-fan]");
  const tempReadout = q<HTMLElement>("[data-temp]");
  const lamp = q<HTMLElement>("[data-lamp]");
  const outputText = q<HTMLElement>("[data-output-text]");
  const consoleForm = q<HTMLFormElement>("[data-console]");
  const input = q<HTMLInputElement>("[data-value]");
  const stopbar = q<HTMLElement>("[data-stopbar]");
  const running = q<HTMLElement>("[data-running]");
  const stopped = q<HTMLFormElement>("[data-stopped]");
  const unlockInput = q<HTMLInputElement>("[data-unlock-input]");
  const unlockError = q<HTMLElement>("[data-unlock-error]");

  let attemptTimer = 0;
  let temperature = HERO_START_TEMPERATURE;
  let seed = 7;
  const noise = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed / 2147483647 - 0.5) * 0.1;
  };

  const fanValue = () => Number(kernel.latestValue(HERO_DEVICE, HERO_CHANNEL) ?? 0);

  function changed(element: HTMLElement, text: string): void {
    if (element.textContent === text) return;
    element.textContent = text;
    element.classList.remove("readout-changed");
    void element.offsetWidth;
    element.classList.add("readout-changed");
  }

  function drawRate(): void {
    const runtime = kernel.devices.get(HERO_DEVICE)!;
    const limits = effectiveLimits(spec);
    const sample = runtime.accepted.get(HERO_CHANNEL) ?? runtime.reads.get(HERO_CHANNEL);
    const elapsed = sample ? Math.min(3600, performance.now() / 1000 - sample.at) : 0;
    const allowed = (limits.rate ?? Infinity) * elapsed;
    const value = fanValue();
    const low = Math.max(limits.min, value - allowed);
    const high = Math.min(limits.max, value + allowed);
    rate.style.setProperty("--from", String(trackPercent(low)));
    rate.style.setProperty("--to", String(trackPercent(high)));
  }

  function drawValue(): void {
    const value = fanValue();
    thumb.style.setProperty("--at", String(trackPercent(value)));
    fill.style.setProperty("--to", String(trackPercent(value)));
    changed(fanReadout, String(Math.round(value * 10) / 10));
    track.setAttribute("aria-label", `${HERO_CHANNEL} track. Limits ${spec.min} % to ${spec.max} %. Now ${value} %.`);
  }

  function showAttempt(value: string, decision: Decision): void {
    window.clearTimeout(attemptTimer);
    let asked: number | null = null;
    try {
      asked = convert(parseQuantity(value), spec.unit ?? "percent");
    } catch (error) {
      if (!(error instanceof UnitError)) throw error;
    }
    const line = decision.code === "above_max" ? maxLine : decision.code === "below_min" ? minLine : null;
    if (asked === null || !["above_max", "below_min", "rate_limited"].includes(decision.code ?? "")) {
      attempt.hidden = true;
      return;
    }
    attempt.hidden = false;
    attempt.classList.toggle("off-scale", trackPercent(asked) >= 100);
    attempt.style.setProperty("--at", String(trackPercent(asked)));
    if (line) {
      line.classList.remove("pulse");
      void line.offsetWidth;
      line.classList.add("pulse");
    }
    if (!reduced()) attemptTimer = window.setTimeout(() => (attempt.hidden = true), 1000);
  }

  function show(value: string, decision: Decision): void {
    lamp.className = `lamp ${decision.status === "done" ? "ok" : decision.status === "blocked" ? "blocked" : "warning"}`;
    lamp.textContent = decision.status;
    outputText.textContent = cliLine(decision).slice(decision.status.length);
    reason.classList.remove("enter");
    if (decision.status === "blocked") {
      reason.textContent = decision.message;
      void reason.offsetWidth;
      reason.classList.add("enter");
      showAttempt(value, decision);
    } else {
      reason.textContent = "";
      attempt.hidden = true;
    }
    drawValue();
    drawRate();
  }

  function send(value: string): void {
    input.value = value;
    const decision = kernel.execute({ kind: "write", device: HERO_DEVICE, channel: HERO_CHANNEL, value: value.trim() }, claude);
    show(value, decision);
  }

  consoleForm.addEventListener("submit", (event) => {
    event.preventDefault();
    send(input.value);
  });
  root.querySelectorAll<HTMLButtonElement>("[data-preset]").forEach((button) => {
    button.addEventListener("click", () => send(button.dataset.preset ?? ""));
  });

  q<HTMLButtonElement>("[data-stop]").addEventListener("click", () => {
    kernel.stopAll(owner, "stop pressed on the website");
    stopbar.classList.add("is-stopped");
    running.hidden = true;
    stopped.hidden = false;
    unlockError.textContent = "";
    drawValue();
    drawRate();
    unlockInput.focus();
  });

  stopped.addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      kernel.unlock(owner, unlockInput.value);
    } catch (error) {
      unlockError.textContent = (error as Error).message;
      return;
    }
    unlockInput.value = "";
    stopbar.classList.remove("is-stopped");
    stopped.hidden = true;
    running.hidden = false;
    q<HTMLButtonElement>("[data-stop]").focus();
  });

  window.setInterval(() => {
    const target = HERO_START_TEMPERATURE - (7 * fanValue()) / 100;
    temperature += (target - temperature) * 0.25 + noise();
    kernel.noteReading(HERO_DEVICE, "temperature", Math.round(temperature * 100) / 100, "degC");
    changed(tempReadout, temperature.toFixed(1));
    kernel.tick();
    drawValue();
  }, 1000);
  window.setInterval(drawRate, 200);

  root.querySelectorAll<HTMLInputElement | HTMLButtonElement>("[disabled]").forEach((element) => (element.disabled = false));
  drawRate();
  if (!reduced()) window.setTimeout(() => (attempt.hidden = true), 1600);
}

document.querySelectorAll<HTMLElement>("[data-hero-demo]").forEach(setup);
