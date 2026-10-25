<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import LimitControl from "./LimitControl.svelte";
  import {
    Kernel,
    agent,
    convert,
    deviceId,
    deviceRefs,
    effectiveHazard,
    effectiveLimits,
    human,
    loadDeviceFile,
    parseQuantity,
    unconfirmed,
    type Command,
    type Decision,
    type DeviceFile,
    type Principal,
  } from "../../lib/kernel";
  import { formatG } from "../../lib/kernel/pyformat";
  import { parseDeviceYaml } from "../../lib/kernel/yaml";
  import { CliError, actionArgs, splitPairs, writeValue } from "../../lib/playground/cli";
  import { deviceProblems, type Checked } from "../../lib/playground/validate";

  interface Example {
    name: string;
    path: string;
    text: string;
  }

  interface Props {
    examples: Example[];
    initial: string;
  }

  let { examples, initial }: Props = $props();

  const PRINCIPALS: Array<{ key: string; label: string; principal: Principal }> = [
    { key: "agent-medium", label: "Agent, control_medium token", principal: agent("claude", "control_medium") },
    { key: "agent-low", label: "Agent, control_low token", principal: agent("claude", "control_low") },
    { key: "agent-read", label: "Agent, read token", principal: agent("claude", "read") },
    { key: "human", label: "Person, human token", principal: human("you") },
  ];

  const start = examples.find((item) => item.name === initial) ?? examples[0];
  let exampleName = $state(start.name);
  let text = $state(start.text);
  let checked = $state.raw<Checked>(deviceProblems(start.text));
  let kernel = $state.raw<Kernel | null>(null);
  let companions = $state.raw<Array<{ id: string; path: string }>>([]);
  let version = $state(0);
  let principalKey = $state("agent-medium");
  let targetDevice = $state("");
  let target = $state("");
  let requestText = $state("");
  let log = $state<Array<{ key: number; who: "agent" | "person"; line: string; status: string; code: string | null; message: string }>>([]);
  let attempt = $state.raw<{ device: string; channel: string; value: number; code: string; key: number } | null>(null);
  let unlockText = $state("");
  let unlockError = $state("");
  let readingDrafts = $state<Record<string, string>>({});
  let counter = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let attemptTimer: ReturnType<typeof setTimeout> | undefined;
  let clock: ReturnType<typeof setInterval> | undefined;

  const file = $derived(checked.file);
  const id = $derived(file ? deviceId(file) : "");
  const principal = $derived(PRINCIPALS.find((item) => item.key === principalKey)!.principal);
  const missing = $derived(file ? unconfirmed(file) : []);
  const reduced = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function exampleFiles(): Map<string, { file: DeviceFile; path: string }> {
    const found = new Map<string, { file: DeviceFile; path: string }>();
    for (const item of examples) {
      try {
        const loaded = loadDeviceFile(parseDeviceYaml(item.text));
        const key = deviceId(loaded);
        if (!found.has(key) || item.text.includes("confirmed:")) found.set(key, { file: loaded, path: item.path });
      } catch {
      }
    }
    return found;
  }
  let library: Map<string, { file: DeviceFile; path: string }> | null = null;

  function simulated(device: DeviceFile): Record<string, unknown> {
    const values: Record<string, unknown> = {};
    for (const [name, spec] of Object.entries(device.read)) {
      if (spec.type === "number" && spec.range) values[name] = Math.round(((spec.range[0] + spec.range[1]) / 2) * 100) / 100;
    }
    return values;
  }

  function build(next: DeviceFile | null): void {
    if (!next) {
      kernel = null;
      companions = [];
      return;
    }
    const fresh = new Kernel();
    const mine = deviceId(next);
    const extra: Array<{ id: string; path: string }> = [];
    for (const ref of deviceRefs(next)) {
      library ??= exampleFiles();
      const other = library.get(ref);
      if (other && ref !== mine) {
        fresh.register(other.file, simulated(other.file));
        extra.push({ id: ref, path: other.path });
      }
    }
    fresh.register(next, simulated(next));
    for (const device of fresh.devices.keys()) fresh.connect(device);
    kernel = fresh;
    companions = extra;
    targetDevice = mine;
    const writes = Object.keys(next.write);
    const actions = Object.keys(next.actions);
    if (!writes.includes(target) && !actions.includes(target)) target = writes[0] ?? actions[0] ?? "";
    readingDrafts = {};
    attempt = null;
    version += 1;
  }

  let builtText: string | null = null;

  function rebuild(current: string): void {
    if (current === builtText) return;
    builtText = current;
    checked = deviceProblems(current);
    build(checked.file);
  }

  $effect(() => {
    const current = text;
    clearTimeout(timer);
    timer = setTimeout(() => rebuild(current), 250);
  });

  onMount(() => {
    const asked = new URL(window.location.href).searchParams.get("example");
    const chosen = examples.find((item) => item.name === asked);
    if (chosen && chosen.name !== exampleName) {
      exampleName = chosen.name;
      text = chosen.text;
    }
    rebuild(text);
    clock = setInterval(() => {
      if (!kernel) return;
      for (const [device, runtime] of kernel.devices) {
        for (const channel of Object.keys(runtime.file.read)) {
          if (runtime.file.read[channel].type === "image") continue;
          kernel.noteReading(device, channel, runtime.values[channel], runtime.file.read[channel].unit);
        }
      }
      kernel.tick();
      version += 1;
    }, 1000);
  });

  onDestroy(() => {
    clearInterval(clock);
    clearTimeout(timer);
    clearTimeout(attemptTimer);
  });

  function chooseExample(name: string): void {
    const item = examples.find((example) => example.name === name);
    if (!item) return;
    text = item.text;
    log = [];
    const url = new URL(window.location.href);
    url.searchParams.set("example", name);
    history.replaceState(null, "", url);
  }

  function lampFor(status: string): string {
    if (status === "done" || status === "allowed") return "ok";
    if (status === "pending" || status === "needs_confirmation") return "warning";
    return "blocked";
  }

  function remember(line: string, decision: Pick<Decision, "status" | "code" | "message">, who: "agent" | "person" = "person"): void {
    counter += 1;
    log = [{ key: counter, who, line, status: decision.status, code: decision.code, message: decision.message }, ...log].slice(0, 30);
  }

  function showAttempt(device: string, channel: string, raw: unknown, decision: Decision): void {
    clearTimeout(attemptTimer);
    attempt = null;
    if (!kernel || !["above_max", "below_min", "rate_limited"].includes(decision.code ?? "")) return;
    const spec = kernel.devices.get(device)?.file.write[channel];
    if (!spec?.unit) return;
    try {
      counter += 1;
      attempt = { device, channel, value: convert(parseQuantity(raw), spec.unit), code: decision.code!, key: counter };
    } catch {
      return;
    }
    if (!reduced()) attemptTimer = setTimeout(() => (attempt = null), 1000);
  }

  function send(dry = false): void {
    if (!kernel) return;
    const runtime = kernel.devices.get(targetDevice);
    if (!runtime) return;
    const isWrite = target in runtime.file.write;
    const words = requestText.trim();
    const line = isWrite
      ? `openhal ${dry ? "dry-run" : "write"} ${targetDevice}.${target} ${words}`
      : `openhal ${dry ? "dry-run" : "action"} ${targetDevice}.${target}${words ? ` ${words}` : ""}`;
    let command: Command;
    try {
      command = isWrite
        ? { kind: "write", device: targetDevice, channel: target, value: writeValue(runtime.file, target, words) }
        : { kind: "action", device: targetDevice, action: target, args: actionArgs(runtime.file, target, words ? splitPairs(words) : []) };
    } catch (error) {
      if (!(error instanceof CliError)) throw error;
      remember(line, { status: "error", code: null, message: error.message }, principal.kind === "human" ? "person" : "agent");
      return;
    }
    const decision = dry ? kernel.dryRun([command], principal)[0] : kernel.execute(command, principal);
    remember(line, decision, principal.kind === "human" ? "person" : "agent");
    if (command.kind === "write" && decision.status === "blocked") showAttempt(targetDevice, target, command.value, decision);
    else attempt = null;
    version += 1;
  }

  function pick(device: string, channel: string, value: string | boolean): void {
    if (!kernel) return;
    targetDevice = device;
    target = channel;
    requestText = String(value);
    send();
  }

  function setReading(device: string, channel: string): void {
    if (!kernel) return;
    const runtime = kernel.devices.get(device)!;
    const spec = runtime.file.read[channel];
    const draft = (readingDrafts[`${device}.${channel}`] ?? "").trim();
    if (!draft) return;
    let value: unknown = draft;
    if (spec.type === "number") {
      const number = Number(draft);
      if (!Number.isFinite(number)) return;
      value = number;
    } else if (spec.type === "bool") {
      value = ["true", "on", "yes", "1"].includes(draft.toLowerCase());
    }
    runtime.values[channel] = value;
    kernel.noteReading(device, channel, value, spec.unit);
    version += 1;
  }

  function stopAll(): void {
    if (!kernel) return;
    const report = kernel.stopAll(human("you"), "stop pressed in the playground");
    remember("openhal stop", { status: "stopped", code: null, message: report.devices.map((item) => `${item.device} ${item.status}`).join(", ") });
    unlockText = "";
    unlockError = "";
    version += 1;
  }

  function unlock(event: SubmitEvent): void {
    event.preventDefault();
    if (!kernel) return;
    try {
      kernel.unlock(human("you"), unlockText);
    } catch (error) {
      unlockError = (error as Error).message;
      return;
    }
    remember("openhal unlock", { status: "done", code: null, message: "Writes are allowed again." });
    version += 1;
  }

  function decide(requestId: string, approve: boolean): void {
    if (!kernel) return;
    const request = kernel.requests.get(requestId)!;
    const line = `openhal confirm ${approve ? "approve" : "reject"} ${requestId}`;
    if (approve) remember(line, kernel.confirm(requestId, human("you")));
    else {
      kernel.reject(requestId, human("you"));
      remember(line, { status: "rejected", code: "rejected", message: `Rejected ${request.command.kind === "write" ? `write:${request.command.channel}` : `action:${request.command.action}`}.` });
    }
    version += 1;
  }

  function valueOf(device: string, channel: string): unknown {
    void version;
    return kernel?.latestValue(device, channel) ?? null;
  }

  function rateWindow(device: string, channel: string): { low: number; high: number } | null {
    void version;
    const runtime = kernel?.devices.get(device);
    const spec = runtime?.file.write[channel];
    if (!runtime || !spec || spec.type !== "number" || spec.max_change_per_s === null) return null;
    const limits = effectiveLimits(spec);
    const sample = runtime.accepted.get(channel) ?? runtime.reads.get(channel);
    if (!sample || typeof sample.value !== "number") return null;
    const allowed = (limits.rate ?? 0) * Math.min(3600, performance.now() / 1000 - sample.at);
    return { low: Math.max(limits.min, sample.value - allowed), high: Math.min(limits.max, sample.value + allowed) };
  }

  function show(value: unknown, unit: string | null): string {
    if (value === null || value === undefined) return "unknown";
    if (typeof value === "number") return `${formatG(value)}${unit ? ` ${unit === "percent" ? "%" : unit}` : ""}`;
    return String(value);
  }

  function tierWords(tier: string, high: boolean): string {
    if (high || tier === "confirm-each-time") return "Confirm each time";
    if (tier === "confirm") return "Confirm once";
    return "No confirmation";
  }

  const pending = $derived.by(() => {
    void version;
    return kernel?.pending() ?? [];
  });
  const stopped = $derived.by(() => {
    void version;
    return kernel?.stopped ?? false;
  });
  const targets = $derived.by(() => {
    void version;
    const runtime = kernel?.devices.get(targetDevice);
    if (!runtime) return [] as Array<{ name: string; kind: string }>;
    return [
      ...Object.keys(runtime.file.write).map((name) => ({ name, kind: "write" })),
      ...Object.keys(runtime.file.actions).map((name) => ({ name, kind: "action" })),
    ];
  });
  const hint = $derived.by(() => {
    void version;
    const runtime = kernel?.devices.get(targetDevice);
    if (!runtime) return "";
    const spec = runtime.file.write[target];
    if (spec) {
      if (spec.type === "number") return `A number with a unit, for example ${formatG(spec.max ?? 0)} ${spec.unit === "percent" ? "%" : spec.unit}`;
      if (spec.type === "bool") return "true or false";
      if (spec.type === "enum") return `One of ${spec.values.join(", ")}`;
      return `Text, at most ${spec.max_length} characters`;
    }
    const action = runtime.file.actions[target];
    if (action) {
      const names = Object.keys(action.args);
      return names.length ? `Arguments as key=value, for example ${names.map((name) => `${name}=…`).join(" ")}` : "No arguments";
    }
    return "";
  });
</script>

<div class="playground">
  <section class="module editor" aria-labelledby="pg-editor-legend">
    <h2 class="module-legend legend" id="pg-editor-legend"><span>Device file</span></h2>
    <div class="toolbar">
      <label class="legend" for="pg-example">Start from</label>
      <select id="pg-example" bind:value={exampleName} onchange={() => chooseExample(exampleName)}>
        {#each examples as item (item.name)}
          <option value={item.name}>{item.path}</option>
        {/each}
      </select>
    </div>
    <label class="visually-hidden" for="pg-text">Device file YAML</label>
    <textarea id="pg-text" bind:value={text} spellcheck="false" autocomplete="off" autocapitalize="off" rows="26" aria-describedby="pg-problems"></textarea>
    <div id="pg-problems" class="problems" aria-live="polite">
      {#if checked.problems.length}
        <p class="lamp blocked">Invalid</p>
        <ul>
          {#each checked.problems as problem, index (index)}
            <li>
              <code>{problem.where}</code>{#if problem.line}<span class="muted"> line {problem.line}</span>{/if}
              <span>{problem.message}</span>
              <span class="source legend">{problem.source === "schema" ? "JSON Schema" : problem.source === "yaml" ? "YAML" : "Spec"}</span>
            </li>
          {/each}
        </ul>
      {:else if missing.length}
        <p class="lamp warning">Valid, read-only</p>
        <p class="muted">Matches spec 0.1 and its schema. It loads read-only until a person confirms limits for {missing.join(", ")}.</p>
      {:else}
        <p class="lamp ok">Valid</p>
        <p class="muted">Matches spec 0.1 and its schema. Every limit is confirmed, so the device is writable.</p>
      {/if}
    </div>
  </section>

  <div class="side">
    <section class="module preview" aria-labelledby="pg-controls-legend">
      <h2 class="module-legend legend" id="pg-controls-legend"><span>Dashboard controls</span><span class="end">Preview</span></h2>
      {#if file && kernel}
        <dl class="ident">
          <div><dt class="legend">Id</dt><dd class="mono">{id}</dd></div>
          <div><dt class="legend">Driver</dt><dd class="mono">{file.connect.driver}</dd></div>
          <div><dt class="legend">Hazard</dt><dd class="mono">{effectiveHazard(file)}</dd></div>
          <div>
            <dt class="legend">Limits</dt>
            <dd>{#if missing.length}<span class="lamp unverified">Unconfirmed</span>{:else}<span class="lamp ok">Confirmed</span>{/if}</dd>
          </div>
        </dl>

        {#if Object.keys(file.read).length}
          <div class="reads">
            {#each Object.entries(file.read) as [name, spec] (name)}
              <div class="read">
                <p class="legend">Read · {name}</p>
                {#if spec.type === "image"}
                  <p class="muted small">Image frames, read on request.</p>
                {:else}
                  <p class="value mono">{show(valueOf(id, name), spec.unit)}</p>
                  <form class="sim" onsubmit={(event) => { event.preventDefault(); setReading(id, name); }}>
                    <label class="visually-hidden" for={`pg-read-${name}`}>Simulated reading for {name}</label>
                    <input id={`pg-read-${name}`} class="mono" placeholder="simulate" bind:value={readingDrafts[`${id}.${name}`]} />
                    <button type="submit" class="small-button">Set</button>
                  </form>
                {/if}
              </div>
            {/each}
          </div>
        {/if}

        {#each Object.entries(file.write) as [name, spec] (name)}
          <div class="channel">
            <div class="channel-head">
              <p class="legend">Write · {name}</p>
              <p class="mono now">{show(valueOf(id, name), spec.unit)}</p>
              <span class={`lamp ${spec.confirm !== "none" || effectiveHazard(file) === "high" ? "warning" : "ok"}`}>{tierWords(spec.confirm, effectiveHazard(file) === "high")}</span>
            </div>
            {#if spec.type === "number" && spec.min !== null && spec.max !== null}
              <LimitControl
                id={`pg-${name}`}
                {name}
                unit={spec.unit ?? ""}
                min={spec.min}
                max={spec.max}
                step={spec.step}
                value={typeof valueOf(id, name) === "number" ? (valueOf(id, name) as number) : null}
                rate={rateWindow(id, name)}
                attempt={attempt && attempt.device === id && attempt.channel === name ? attempt : null}
                onpick={(picked) => pick(id, name, `${picked} ${spec.unit}`)}
              />
              {#if spec.max_change_per_s !== null}
                <p class="muted small">At most {formatG(spec.max_change_per_s)} {spec.unit === "percent" ? "%" : spec.unit} per second. The bracket shows how far it may move right now.</p>
              {/if}
            {:else if spec.type === "bool"}
              <button
                type="button"
                class="switch"
                role="switch"
                aria-checked={valueOf(id, name) === true}
                onclick={() => pick(id, name, valueOf(id, name) === true ? "false" : "true")}
              >
                <span class="visually-hidden">{name}</span>
                <span class="track"><span class="knob"></span></span>
                <span class="mono">{valueOf(id, name) === true ? "true" : "false"}</span>
              </button>
            {:else if spec.type === "enum"}
              <label class="visually-hidden" for={`pg-${name}`}>{name}</label>
              <select id={`pg-${name}`} value={String(valueOf(id, name) ?? "")} onchange={(event) => pick(id, name, (event.currentTarget as HTMLSelectElement).value)}>
                {#each spec.values as option (option)}
                  <option value={option}>{option}</option>
                {/each}
              </select>
            {:else}
              <p class="muted small">Text, at most {spec.max_length} characters{spec.pattern ? `, matching ${spec.pattern}` : ""}.</p>
            {/if}
          </div>
        {/each}

        {#if Object.keys(file.actions).length}
          <div class="actions">
            <p class="legend">Actions</p>
            <ul>
              {#each Object.entries(file.actions) as [name, action] (name)}
                <li>
                  <code>{name}</code>
                  {#if Object.keys(action.args).length}<span class="muted small">{Object.keys(action.args).join(", ")}</span>{/if}
                  {#if action.require.length}<span class="muted small">needs {action.require.join(" and ")}</span>{/if}
                  <span class={`lamp ${action.confirm !== "none" || effectiveHazard(file) === "high" ? "warning" : "ok"}`}>{tierWords(action.confirm, effectiveHazard(file) === "high")}</span>
                </li>
              {/each}
            </ul>
          </div>
        {/if}
        {#if companions.length}
          <p class="muted small">
            Also loaded, because this file's interlocks name them.
            {#each companions as other, index (other.id)}{index ? ", " : ""}<code>{other.id}</code> from <code>{other.path}</code>{/each}.
          </p>
        {/if}
      {:else}
        <p class="muted">Fix the file and its controls appear here.</p>
      {/if}
    </section>

    <section class="module breaker" aria-labelledby="pg-break-legend">
      <h2 class="module-legend legend" id="pg-break-legend"><span>Try to break the limits</span><span class="end">In-browser demo</span></h2>
      {#if kernel}
        <form class="request" onsubmit={(event) => { event.preventDefault(); send(); }}>
          <div class="fields">
            <label class="field">
              <span class="legend">As</span>
              <select bind:value={principalKey}>
                {#each PRINCIPALS as item (item.key)}
                  <option value={item.key}>{item.label}</option>
                {/each}
              </select>
            </label>
            <label class="field">
              <span class="legend">Device</span>
              <select bind:value={targetDevice}>
                {#each [...kernel.devices.keys()] as device (device)}
                  <option value={device}>{device}</option>
                {/each}
              </select>
            </label>
            <label class="field">
              <span class="legend">Channel or action</span>
              <select bind:value={target}>
                {#each targets as item (item.name)}
                  <option value={item.name}>{item.kind === "write" ? item.name : `${item.name} (action)`}</option>
                {/each}
              </select>
            </label>
          </div>
          <label class="field wide">
            <span class="legend">Value</span>
            <input class="mono" bind:value={requestText} autocomplete="off" spellcheck="false" aria-describedby="pg-hint" />
          </label>
          <p id="pg-hint" class="muted small">{hint}</p>
          <div class="buttons">
            <button type="submit" class="button" disabled={!target}>Send</button>
            <button type="button" class="button secondary" disabled={!target} onclick={() => send(true)}>Dry run</button>
          </div>
        </form>

        {#if pending.length}
          <div class="pending">
            <p class="legend">Waiting for a person</p>
            <ul>
              {#each pending as request (request.requestId)}
                <li>
                  <span class="mono small">{request.requestId}</span>
                  <span>{request.command.kind === "write" ? `${request.command.channel} = ${String(request.command.value)}` : `${request.command.action}`}</span>
                  <button type="button" class="person-button" onclick={() => decide(request.requestId, true)}>Approve</button>
                  <button type="button" class="person-button" onclick={() => decide(request.requestId, false)}>Reject</button>
                </li>
              {/each}
            </ul>
          </div>
        {/if}

        <ol class="log" aria-label="Decisions, newest first" aria-live="polite">
          {#each log as entry (entry.key)}
            <li class={entry.who}>
              <p class="who legend">{entry.who === "person" ? "Person" : "Agent"}</p>
              <p class="mono line"><span aria-hidden="true">$ </span>{entry.line}</p>
              <p class="decision">
                <span class={`lamp ${lampFor(entry.status)}`}>{entry.status}</span>
                {#if entry.code && entry.status !== "done"}<code>{entry.code}</code>{/if}
                <span>{entry.message}</span>
              </p>
            </li>
          {/each}
        </ol>
      {:else}
        <p class="muted">A valid device file gets a simulated device here.</p>
      {/if}

      <div class="stopbar" class:is-stopped={stopped}>
        <div class="stripes" aria-hidden="true"></div>
        {#if stopped}
          <form class="stop-row" onsubmit={unlock}>
            <p class="plate"><span class="legend">Stopped</span> Every device is in its safe state.</p>
            <div class="plate unlock">
              <label class="visually-hidden" for="pg-unlock">Type unlock to lift the stop</label>
              <input id="pg-unlock" class="mono" placeholder="type unlock" bind:value={unlockText} autocomplete="off" />
              <button type="submit">Unlock</button>
            </div>
            {#if unlockError}<p class="plate error" aria-live="polite">{unlockError}</p>{/if}
          </form>
        {:else}
          <div class="stop-row">
            <p class="note">Stop puts every simulated device in its safe state.</p>
            <button type="button" class="stop" onclick={stopAll} disabled={!kernel}>Stop all</button>
          </div>
        {/if}
      </div>
    </section>
  </div>
</div>

<style>
  .playground {
    display: grid;
    gap: var(--s-6);
    align-items: start;
  }

  h2.module-legend {
    margin: 0;
    font-size: var(--t-0);
  }

  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--s-2) var(--s-3);
    margin-bottom: var(--s-3);
  }

  .toolbar .legend {
    color: var(--ink-2);
  }

  select,
  input,
  textarea {
    font: inherit;
    color: var(--ink);
    background: var(--panel);
    border: 1px solid var(--ink-2);
    border-radius: var(--radius);
  }

  select,
  input {
    min-height: 40px;
    padding: 0 var(--s-2);
    font-size: var(--t-2);
    max-width: 100%;
  }

  input::placeholder,
  textarea::placeholder {
    color: var(--ink-2);
  }

  textarea {
    display: block;
    width: 100%;
    min-height: 420px;
    padding: var(--s-3);
    font-family: var(--font-mono);
    font-size: var(--t-0);
    line-height: 20px;
    resize: vertical;
    tab-size: 2;
    white-space: pre;
    overflow: auto;
  }

  .problems {
    margin-top: var(--s-3);
    font-size: var(--t-2);
    line-height: var(--lh-2);
    display: grid;
    gap: var(--s-2);
  }

  .problems ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: var(--s-2);
  }

  .problems li {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-1) var(--s-2);
    padding-left: var(--s-3);
    border-left: 2px solid var(--ink);
  }

  .problems code {
    font-size: var(--t-0);
  }

  .problems .source {
    color: var(--ink-2);
  }

  .side {
    display: grid;
    gap: var(--s-6);
    min-width: 0;
  }

  .ident {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin: 0 0 var(--s-4);
    border: 1px solid var(--ink);
    border-radius: var(--radius);
  }

  .ident > div {
    padding: var(--s-1) var(--s-3);
    border-bottom: 1px solid var(--rule);
  }

  .ident > div:nth-child(odd) {
    border-right: 1px solid var(--rule);
  }

  .ident > div:nth-last-child(-n + 2) {
    border-bottom: 0;
  }

  .ident dt {
    color: var(--ink-2);
  }

  .ident dd {
    margin: 0;
    font-size: var(--t-0);
    line-height: var(--lh-1);
    overflow-wrap: anywhere;
  }

  .reads {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: var(--s-4);
    padding-bottom: var(--s-4);
    border-bottom: 1px solid var(--rule);
  }

  .read .legend,
  .channel .legend,
  .actions .legend,
  .pending .legend,
  .field .legend {
    color: var(--ink-2);
  }

  .value {
    font-size: var(--t-3);
    line-height: var(--lh-3);
  }

  .sim {
    display: flex;
    gap: var(--s-1);
    margin-top: var(--s-1);
  }

  .sim input {
    width: 7em;
    min-height: 32px;
    font-size: var(--t-0);
  }

  .small-button {
    min-height: 32px;
    padding: 0 var(--s-3);
    border: 1px solid var(--ink-2);
    border-radius: var(--radius);
    background: transparent;
    color: var(--ink);
    font-family: var(--font-label);
    font-size: var(--t-0);
    font-weight: 700;
    letter-spacing: var(--legend-tracking);
    text-transform: uppercase;
    cursor: pointer;
  }

  .small-button:hover {
    border-color: var(--signal);
    color: var(--signal);
  }

  .channel {
    padding: var(--s-4) 0;
    border-bottom: 1px solid var(--rule);
  }

  .channel-head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-2) var(--s-4);
    margin-bottom: var(--s-2);
  }

  .now {
    font-size: var(--t-3);
    line-height: var(--lh-3);
    margin-right: auto;
  }

  .small {
    font-size: var(--t-2);
    line-height: var(--lh-2);
  }

  .switch {
    display: inline-flex;
    align-items: center;
    gap: var(--s-3);
    min-height: 44px;
    padding: 0;
    border: 0;
    background: none;
    color: var(--ink);
    cursor: pointer;
  }

  .switch .track {
    position: relative;
    width: 48px;
    height: 24px;
    border: 2px solid var(--ink);
    border-radius: var(--radius);
  }

  .switch .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    background: var(--ink-3);
  }

  .switch[aria-checked="true"] .knob {
    left: auto;
    right: 2px;
    background: var(--ink);
  }

  .actions {
    padding-top: var(--s-4);
  }

  .actions ul,
  .pending ul,
  .log {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .actions li,
  .pending li {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-3);
    padding: var(--s-2) 0;
    border-top: 1px solid var(--rule);
  }

  .request {
    display: grid;
    gap: var(--s-3);
  }

  .fields {
    display: grid;
    gap: var(--s-3);
  }

  .field {
    display: grid;
    gap: var(--s-1);
    min-width: 0;
  }

  .field select,
  .field input {
    width: 100%;
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-2);
  }

  .button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .pending {
    margin-top: var(--s-4);
  }

  .log {
    margin-top: var(--s-4);
    max-height: 340px;
    overflow-y: auto;
  }

  .log li {
    padding: var(--s-2) var(--s-3);
    border-top: 1px solid var(--rule);
  }

  .log li.agent {
    border-left: 3px dashed var(--ink-2);
  }

  .log li.person {
    border-left: 6px solid var(--bezel);
    background: color-mix(in srgb, var(--bezel) 8%, var(--panel));
  }

  .who {
    color: var(--ink-2);
  }

  .person-button {
    min-height: 40px;
    padding: 0 var(--s-4);
    border: 2px solid var(--bezel);
    border-radius: var(--radius);
    background: var(--bezel);
    color: var(--on-bezel);
    font-family: var(--font-label);
    font-weight: 800;
    letter-spacing: var(--legend-tracking);
    text-transform: uppercase;
    cursor: pointer;
  }

  .person-button:focus-visible {
    outline: 3px solid var(--signal);
    outline-offset: 2px;
  }

  .line {
    font-size: var(--t-0);
    line-height: var(--lh-0);
    color: var(--ink-2);
    overflow-wrap: anywhere;
  }

  .decision {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-2);
    font-size: var(--t-2);
    line-height: var(--lh-2);
  }

  .decision code {
    font-size: var(--t-0);
  }

  .stopbar {
    position: relative;
    margin: var(--s-5) calc(-1 * var(--s-4)) calc(-1 * var(--s-4));
    background: var(--bezel);
    color: var(--on-bezel);
    overflow: hidden;
  }

  .stripes {
    position: absolute;
    inset: 0;
    background: var(--stripe);
    transform: translateX(-101%);
    transition: transform var(--motion-stop-wipe) var(--ease);
  }

  .is-stopped .stripes {
    transform: none;
  }

  .stop-row {
    position: relative;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--s-3);
    padding: var(--s-3) var(--s-4);
  }

  .note {
    color: var(--on-bezel);
    max-width: 34ch;
  }

  .stop {
    min-height: 56px;
    min-width: 180px;
    padding: 0 var(--s-6);
    border: 2px solid var(--on-bezel);
    border-radius: var(--radius);
    background: var(--blocked);
    color: var(--panel);
    font-family: var(--font-label);
    font-size: var(--t-3);
    font-weight: 800;
    letter-spacing: var(--legend-tracking);
    text-transform: uppercase;
    cursor: pointer;
  }

  .plate {
    padding: var(--s-2) var(--s-3);
    background: var(--bezel);
    color: var(--on-bezel);
    border-radius: var(--radius);
    font-size: var(--t-2);
  }

  .plate .legend {
    font-size: var(--t-2);
    font-weight: 800;
    margin-right: var(--s-2);
  }

  .unlock {
    display: flex;
    gap: var(--s-2);
  }

  .unlock input {
    width: 9em;
    background: var(--bezel);
    color: var(--on-bezel);
    border-color: var(--on-bezel);
  }

  .unlock input::placeholder {
    color: color-mix(in srgb, var(--on-bezel) 72%, var(--bezel));
  }

  .unlock button {
    min-height: 40px;
    padding: 0 var(--s-3);
    border: 0;
    border-radius: var(--radius);
    background: var(--on-bezel);
    color: var(--bezel);
    font-family: var(--font-label);
    font-weight: 800;
    letter-spacing: var(--legend-tracking);
    text-transform: uppercase;
    cursor: pointer;
  }

  .error {
    width: 100%;
  }

  .stop:focus-visible,
  .unlock button:focus-visible,
  .unlock input:focus-visible {
    outline: 3px solid var(--on-bezel);
    outline-offset: 2px;
  }

  @media (min-width: 600px) {
    .fields {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .ident {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }

    .ident > div {
      border-bottom: 0;
      border-right: 1px solid var(--rule);
    }

    .ident > div:last-child {
      border-right: 0;
    }
  }

  @media (min-width: 1024px) {
    .playground {
      grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
    }

    .editor {
      position: sticky;
      top: var(--s-5);
    }

    textarea {
      min-height: calc(100dvh - 300px);
    }
  }
</style>
