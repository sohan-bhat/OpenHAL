<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import InfoMark from "./InfoMark.svelte";
  import TraceList from "./TraceList.svelte";
  import {
    Kernel,
    agent,
    deviceId,
    deviceRefs,
    effectiveHazard,
    human,
    label,
    loadDeviceFile,
    unconfirmed,
    type Command,
    type DeviceFile,
    type Principal,
  } from "../../lib/kernel";
  import { formatG } from "../../lib/kernel/pyformat";
  import { parseDeviceYaml } from "../../lib/kernel/yaml";
  import { CliError, actionArgs, splitPairs, writeValue } from "../../lib/playground/cli";
  import { decisionWire, displayUnit, errorEntry, requestFor, responseFor } from "../../lib/playground/rpc";
  import { afterAction } from "../../lib/playground/simulate";
  import type { Exchange } from "../../lib/playground/types";
  import { deviceProblems, type Checked } from "../../lib/playground/validate";
  import { rpcError } from "../../lib/protocol";
  import type { TraceEntry } from "../../lib/trace";

  interface Example {
    name: string;
    path: string;
    text: string;
  }

  interface Suggestion {
    device: string;
    target: string;
    text: string;
    readings?: Record<string, unknown>;
  }

  interface Quick {
    label: string;
    command: Command;
  }

  interface Props {
    examples: Example[];
    initial: string;
    suggestion?: Suggestion | null;
    quick?: Quick[];
    watch?: string[];
  }

  let { examples, initial, suggestion = null, quick = [], watch = [] }: Props = $props();
  const RUNNING_S = 30;
  let skew = 0;
  const clockNow = () => performance.now() / 1000 + skew;

  const CLIENTS: Array<{ key: string; label: string; client: string; principal: Principal }> = [
    { key: "agent-medium", label: "Agent, control_medium token", client: "claude", principal: agent("claude", "control_medium") },
    { key: "agent-low", label: "Agent, control_low token", client: "claude", principal: agent("claude", "control_low") },
    { key: "agent-read", label: "Agent, read token", client: "claude", principal: agent("claude", "read") },
    { key: "human", label: "Person, human token", client: "you", principal: human("you") },
  ];
  const TTL_S = 300;

  const start = examples.find((item) => item.name === initial) ?? examples[0];
  let exampleName = $state(start.name);
  let text = $state(start.text);
  let checked = $state.raw<Checked>(deviceProblems(start.text));
  let kernel = $state.raw<Kernel | null>(null);
  let companions = $state.raw<Array<{ id: string; path: string }>>([]);
  let version = $state(0);
  let clientKey = $state("agent-medium");
  let targetDevice = $state("");
  let target = $state("");
  let requestText = $state("");
  let exchanges = $state<Exchange[]>([]);
  let unlockText = $state("");
  let unlockError = $state("");
  let readingDrafts = $state<Record<string, string>>({});
  let counter = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let clock: ReturnType<typeof setInterval> | undefined;
  let builtText: string | null = null;
  let library: Map<string, { file: DeviceFile; path: string }> | null = null;

  const file = $derived(checked.file);
  const id = $derived(file ? deviceId(file) : "");
  const client = $derived(CLIENTS.find((item) => item.key === clientKey)!);
  const missing = $derived(file ? unconfirmed(file) : []);
  const targetMethod = $derived(kernel && kernel.devices.get(targetDevice)?.file.actions[target] ? "hal/action" : "hal/write");

  function exampleFiles(): Map<string, { file: DeviceFile; path: string }> {
    const found = new Map<string, { file: DeviceFile; path: string }>();
    for (const item of examples) {
      try {
        const loaded = loadDeviceFile(parseDeviceYaml(item.text));
        const key = deviceId(loaded);
        if (!found.has(key) || item.text.includes("confirmed:")) found.set(key, { file: loaded, path: item.path });
      } catch {
        continue;
      }
    }
    return found;
  }

  function simulated(device: DeviceFile): Record<string, unknown> {
    const values: Record<string, unknown> = {};
    for (const [name, spec] of Object.entries(device.read)) {
      if (spec.type === "number" && spec.range) values[name] = Math.round(((spec.range[0] + spec.range[1]) / 2) * 100) / 100;
    }
    for (const [name, spec] of Object.entries(device.write)) {
      if (deviceId(device) === "desk-fan" && name === "fan_speed" && spec.type === "number") values[name] = 20;
    }
    if (suggestion?.readings && suggestion.device === deviceId(device)) Object.assign(values, suggestion.readings);
    return values;
  }

  function build(next: DeviceFile | null): void {
    if (!next) {
      kernel = null;
      companions = [];
      return;
    }
    skew = 0;
    const fresh = new Kernel(clockNow, { confirmTtlS: TTL_S });
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
    skew = RUNNING_S;
    for (const [device, runtime] of fresh.devices) {
      for (const [channel, spec] of Object.entries(runtime.file.read)) {
        if (spec.type !== "image") fresh.noteReading(device, channel, runtime.values[channel], spec.unit);
      }
    }
    kernel = fresh;
    companions = extra;
    targetDevice = mine;
    const writes = Object.keys(next.write);
    const actions = Object.keys(next.actions);
    const suggested = suggestion && suggestion.device === mine && (writes.includes(suggestion.target) || actions.includes(suggestion.target)) ? suggestion : null;
    if (!writes.includes(target) && !actions.includes(target)) target = suggested?.target ?? writes[0] ?? actions[0] ?? "";
    if (!requestText && suggested && suggested.target === target) requestText = suggested.text;
    else if (!requestText && next.write[target]?.type === "number" && next.write[target].max !== null) {
      requestText = `${formatG(next.write[target].max! * 1.5)} ${displayUnit(next.write[target].unit)}`;
    }
    readingDrafts = {};
    version += 1;
  }

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

  rebuild(start.text);

  onMount(() => {
    const asked = new URL(window.location.href).searchParams.get("example");
    const chosen = examples.find((item) => item.name === asked);
    if (chosen && chosen.name !== exampleName) {
      exampleName = chosen.name;
      text = chosen.text;
      rebuild(text);
    }
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
  });

  function chooseExample(name: string): void {
    const item = examples.find((example) => example.name === name);
    if (!item) return;
    text = item.text;
    exchanges = [];
    const url = new URL(window.location.href);
    url.searchParams.set("example", name);
    history.replaceState(null, "", url);
  }

  function log(who: "agent" | "person", name: string, entries: TraceEntry[]): void {
    counter += 1;
    exchanges = [{ key: counter, who, client: name, entries }, ...exchanges].slice(0, 30);
  }

  function fileOf(device: string): DeviceFile | undefined {
    return kernel?.devices.get(device)?.file;
  }

  function send(dry = false): void {
    if (!kernel) return;
    const runtime = kernel.devices.get(targetDevice);
    if (!runtime) return;
    const who = client.principal.kind === "human" ? "person" : "agent";
    const isWrite = target in runtime.file.write;
    const words = requestText.trim();
    let command: Command;
    try {
      command = isWrite
        ? { kind: "write", device: targetDevice, channel: target, ...writeValue(runtime.file, target, words) }
        : { kind: "action", device: targetDevice, action: target, args: actionArgs(runtime.file, target, words ? splitPairs(words) : []) };
    } catch (error) {
      if (!(error instanceof CliError)) throw error;
      log(who, client.client, [
        { kind: "request", method: isWrite ? "hal/write" : "hal/action", params: { device: targetDevice, [isWrite ? "channel" : "action"]: target, value: words } },
        errorEntry(rpcError("INVALID_PARAMS", { problems: [error.message] })),
      ]);
      return;
    }
    if (dry) {
      const [decision] = kernel.dryRun([command], client.principal, true);
      const params = (requestFor(command) as { params: Record<string, unknown> }).params;
      log(who, client.client, [
        { kind: "request", method: "hal/dryRun", params: { commands: [{ kind: command.kind, ...params }] } },
        { kind: "result", result: { decisions: [decisionWire(decision, command, fileOf(command.device), label(client.principal))] } },
      ]);
    } else {
      const decision = kernel.execute(command, client.principal, null, true);
      settle(command, decision.status);
      log(who, client.client, [requestFor(command), responseFor(decision, command, fileOf(command.device), TTL_S, label(client.principal))]);
    }
    version += 1;
  }

  function settle(command: Command, status: string): void {
    if (!kernel || command.kind !== "action" || status !== "done") return;
    const runtime = kernel.devices.get(command.device);
    if (!runtime) return;
    for (const [channel, value] of Object.entries(afterAction(runtime.file, command.action))) {
      runtime.values[channel] = value;
      kernel.noteReading(command.device, channel, value, runtime.file.read[channel].unit);
    }
  }

  function sendQuick(item: Quick): void {
    if (!kernel || !kernel.devices.has(item.command.device)) return;
    const agentClient = CLIENTS[0];
    const decision = kernel.execute(item.command, agentClient.principal, null, true);
    settle(item.command, decision.status);
    log("agent", agentClient.client, [requestFor(item.command), responseFor(decision, item.command, fileOf(item.command.device), TTL_S, label(agentClient.principal))]);
    version += 1;
  }

  function people(unit: string | null): string {
    const shown = displayUnit(unit);
    return shown === "degC" ? "°C" : shown === "degF" ? "°F" : (shown ?? "");
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
    log("person", "you", [
      { kind: "request", method: "hal/stop", params: { reason: "stop pressed in the playground" } },
      { kind: "result", result: { devices: report.devices.map((item) => ({ device: item.device, status: item.status, detail: item.detail })) } },
    ]);
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
    log("person", "you", [
      { kind: "request", method: "hal/unlock", params: { phrase: unlockText.trim() } },
      { kind: "result", result: { ok: true } },
    ]);
    version += 1;
  }

  function decide(requestId: string, approve: boolean): void {
    if (!kernel) return;
    const request = kernel.requests.get(requestId)!;
    if (approve) {
      const decision = kernel.confirm(requestId, human("you"));
      settle(request.command, decision.status);
      log("person", "you", [
        { kind: "request", method: "hal/confirmations/approve", params: { requestId } },
        { kind: "result", result: decisionWire(decision, request.command, fileOf(request.command.device), label(request.principal)) },
      ]);
    } else {
      kernel.reject(requestId, human("you"));
      log("person", "you", [
        { kind: "request", method: "hal/confirmations/reject", params: { requestId } },
        {
          kind: "result",
          result: {
            requestId,
            status: "rejected",
            command: { kind: request.command.kind, ...(requestFor(request.command) as { params: Record<string, unknown> }).params },
            requestedBy: label(request.principal),
            decidedBy: "human:you",
          },
        },
      ]);
    }
    version += 1;
  }

  function valueOf(device: string, channel: string): unknown {
    void version;
    return kernel?.latestValue(device, channel) ?? null;
  }

  function show(value: unknown): string {
    if (value === null || value === undefined) return "unknown";
    if (typeof value === "number") return formatG(value);
    return String(value);
  }

  function tierWord(tier: string, high: boolean): string {
    if (high || tier === "confirm-each-time") return "each time";
    if (tier === "confirm") return "once";
    return "none";
  }

  const ready = $derived.by(() => {
    void version;
    return quick.filter((item) => kernel?.devices.has(item.command.device));
  });
  const watched = $derived.by(() => {
    void version;
    const device = ready[0]?.command.device;
    const runtime = device ? kernel?.devices.get(device) : undefined;
    if (!device || !runtime) return [] as Array<{ device: string; name: string; unit: string }>;
    return watch
      .filter((name) => name in runtime.file.write || name in runtime.file.read)
      .map((name) => ({ device, name, unit: people(runtime.file.write[name]?.unit ?? runtime.file.read[name]?.unit ?? null) }));
  });
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
      if (spec.type === "number") return `A number with a unit, for example ${formatG(spec.max ?? 0)} ${displayUnit(spec.unit)}`;
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

<div class="frame">
  {#if ready.length}
    <section class="try" aria-labelledby="pg-try-title">
      <h2 id="pg-try-title">Try a request from the story<InfoMark topic="this demo" text="This demo runs in your browser, so a TypeScript port of the safety kernel checks each request here and sends nothing to hardware." /></h2>
      <div class="try-grid">
        <ul class="quick">
          {#each ready as item (item.label)}
            <li><button type="button" class="button quiet quick-button" onclick={() => sendQuick(item)}>{item.label}</button></li>
          {/each}
        </ul>
        <aside class="printer" aria-labelledby="pg-printer-title">
          <h3 id="pg-printer-title" class="small-head">
            {file ? file.device.name : "Device"}
          </h3>
          <dl class="readout">
            {#each watched as item (item.name)}
              <div>
                <dt class="mono">{item.name}</dt>
                <dd class="mono">{show(valueOf(item.device, item.name))}{#if item.unit}&nbsp;{item.unit}{/if}</dd>
              </div>
            {/each}
            {#if file}
              <div>
                <dt>Hazard<InfoMark topic="hazard" text="The hazard class states how much harm the device can do, so a medium hazard device needs a control_medium token and the device's riskiest actions wait for a person." href="/docs/safety/" /></dt>
                <dd class="mono">{effectiveHazard(file)}</dd>
              </div>
              <div>
                <dt>Limits<InfoMark topic="confirmed limits" text="A person read this device file and confirmed the file's limits. The kernel checks every command against the confirmed limits." href="/docs/concepts/" /></dt>
                <dd>{#if missing.length}<span class="status unverified">unconfirmed</span>{:else}<span class="status ok">confirmed</span>{/if}</dd>
              </div>
            {/if}
          </dl>
          {#if pending.length}
            <div class="waiting">
              <p class="waiting-head">Waiting for a person<InfoMark topic="pending" text="Because a request such as a cancel that can't be undone needs a person, the hub returned pending, and the request waits here until a person approves or rejects the request." /></p>
              <ul>
                {#each pending as request (request.requestId)}
                  <li>
                    <span class="mono">{request.command.kind === "write" ? `${request.command.channel} ${String(request.command.value)}` : request.command.action}</span>
                    <span class="decide">
                      <button type="button" class="button person" onclick={() => decide(request.requestId, true)}>Approve</button>
                      <button type="button" class="button quiet" onclick={() => decide(request.requestId, false)}>Reject</button>
                    </span>
                  </li>
                {/each}
              </ul>
            </div>
          {/if}
          <div class="stop-area" class:is-stopped={stopped}>
            {#if stopped}
              <form class="stopped-row" onsubmit={unlock}>
                <p class="status blocked">stopped</p>
                <label class="visually-hidden" for="pg-unlock">Type unlock to lift the stop</label>
                <input id="pg-unlock" class="mono" placeholder="type unlock" bind:value={unlockText} autocomplete="off" />
                <button type="submit" class="button person">Unlock</button>
                {#if unlockError}<p class="unlock-error" aria-live="polite">{unlockError}</p>{/if}
              </form>
            {:else}
              <button type="button" class="stop" onclick={stopAll} disabled={!kernel}>Stop</button>
              <p class="muted">Any client may send a stop, but lifting the stop takes a person's token.</p>
            {/if}
          </div>
        </aside>
        <div class="answers">
          <h3 class="small-head">The hub's responses</h3>
          <TraceList {exchanges} />
        </div>
      </div>
    </section>
  {/if}

  <details class="build" open={!ready.length}>
    <summary>Build your own request</summary>
    <div class="build-body">
    <div class="playground">
      <section class="panel editor" aria-labelledby="pg-editor-title">
        <div class="panel-head">
          <h2 id="pg-editor-title">Device file</h2>
          <label class="example">
            <span class="legend">Start from</span>
            <select bind:value={exampleName} onchange={() => chooseExample(exampleName)}>
              {#each examples as item (item.name)}
                <option value={item.name}>{item.path}</option>
              {/each}
            </select>
          </label>
        </div>
        <label class="visually-hidden" for="pg-text">Device file YAML</label>
        <textarea id="pg-text" bind:value={text} spellcheck="false" autocomplete="off" autocapitalize="off" rows="24" aria-describedby="pg-problems"></textarea>
        <div id="pg-problems" class="problems" aria-live="polite">
          {#if checked.problems.length}
            <p class="status blocked">invalid</p>
            <ul>
              {#each checked.problems as problem, index (index)}
                <li>
                  <code>{problem.where}</code>{#if problem.line}<span class="muted"> line {problem.line}</span>{/if}
                  <span>{problem.message}</span>
                  <span class="legend">{problem.source === "schema" ? "JSON Schema" : problem.source === "yaml" ? "YAML" : "Specification"}</span>
                </li>
              {/each}
            </ul>
          {:else if missing.length}
            <p class="status unverified">valid, limits unconfirmed</p>
            <p class="muted">Changes are refused with UNVERIFIED_LIMITS until a person confirms {missing.join(", ")}.</p>
          {:else}
            <p class="status ok">valid</p>
          {/if}
        </div>
      </section>

      <div class="side">
        <section class="panel" aria-labelledby="pg-request-title">
          <div class="panel-head">
            <h2 id="pg-request-title">Send a request</h2>
          </div>
          {#if kernel}
            <form class="request" onsubmit={(event) => { event.preventDefault(); send(); }}>
              <div class="fields">
                <div class="field">
                  <span class="legend as-label"><label for="pg-as">As</label><InfoMark topic="tokens" text="Each client signs in with a token, and an agent's token sets which hazard classes the agent may control. Approving a request or lifting a stop takes a person's token." href="/docs/concepts/" /></span>
                  <select id="pg-as" bind:value={clientKey}>
                    {#each CLIENTS as item (item.key)}
                      <option value={item.key}>{item.label}</option>
                    {/each}
                  </select>
                </div>
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
              <label class="field">
                <span class="legend">Value</span>
                <input class="mono" bind:value={requestText} autocomplete="off" spellcheck="false" aria-describedby="pg-hint" />
              </label>
              <p id="pg-hint" class="muted">{hint}</p>
              <div class="buttons">
                <button type="submit" class="button" disabled={!target}>Send {targetMethod}</button>
                <button type="button" class="button quiet" disabled={!target} onclick={() => send(true)}>Dry run</button>
              </div>
            </form>
          {/if}
          {#if !ready.length}
            <div class="stop-area" class:is-stopped={stopped}>
              {#if stopped}
                <form class="stopped-row" onsubmit={unlock}>
                  <p class="status blocked">stopped</p>
                  <label class="visually-hidden" for="pg-unlock-build">Type unlock to lift the stop</label>
                  <input id="pg-unlock-build" class="mono" placeholder="type unlock" bind:value={unlockText} autocomplete="off" />
                  <button type="submit" class="button person">Unlock</button>
                  {#if unlockError}<p class="unlock-error" aria-live="polite">{unlockError}</p>{/if}
                </form>
              {:else}
                <button type="button" class="stop" onclick={stopAll} disabled={!kernel}>Stop</button>
                <p class="muted">Any client may send a stop, but lifting the stop takes a person's token.</p>
              {/if}
            </div>
            {#if pending.length}
              <div class="waiting">
                <p class="waiting-head">Waiting for a person</p>
                <ul>
                  {#each pending as request (request.requestId)}
                    <li>
                      <span class="mono">{request.command.kind === "write" ? `${request.command.channel} ${String(request.command.value)}` : request.command.action}</span>
                      <span class="decide">
                        <button type="button" class="button person" onclick={() => decide(request.requestId, true)}>Approve</button>
                        <button type="button" class="button quiet" onclick={() => decide(request.requestId, false)}>Reject</button>
                      </span>
                    </li>
                  {/each}
                </ul>
              </div>
            {/if}
          {/if}
        </section>

        <section class="panel" aria-labelledby="pg-device-title">
          <div class="panel-head">
            <h2 id="pg-device-title">Simulated device</h2>
          </div>
          {#if file && kernel}
            <dl class="facts">
              <div><dt class="legend">Id</dt><dd class="mono">{id}</dd></div>
              <div><dt class="legend">Driver</dt><dd class="mono">{file.connect.driver}</dd></div>
              {#if !ready.length}
                <div><dt class="legend">Hazard</dt><dd class="mono">{effectiveHazard(file)}</dd></div>
                <div><dt class="legend">Limits</dt><dd>{#if missing.length}<span class="status unverified">unconfirmed</span>{:else}<span class="status ok">confirmed</span>{/if}</dd></div>
              {/if}
            </dl>
            {#if Object.keys(file.write).length}
              <div class="table-wrap stack">
                <table>
                  <caption class="legend">Channels the device can change</caption>
                  <thead>
                    <tr><th scope="col">Channel</th><th scope="col">Value</th><th scope="col">Min</th><th scope="col">Max</th><th scope="col">Rate per s</th><th scope="col">Confirm</th></tr>
                  </thead>
                  <tbody>
                    {#each Object.entries(file.write) as [name, spec] (name)}
                      <tr>
                        <td data-label="Channel" class="mono">{name}</td>
                        <td data-label="Value" class="mono">{show(valueOf(id, name))}{#if spec.unit}&nbsp;{displayUnit(spec.unit)}{/if}</td>
                        <td data-label="Min" class="mono">{spec.min === null ? (spec.type === "enum" ? spec.values.join(", ") : spec.type) : formatG(spec.min)}</td>
                        <td data-label="Max" class="mono">{spec.max === null ? "" : formatG(spec.max)}</td>
                        <td data-label="Rate per s" class="mono">{spec.max_change_per_s === null ? "" : formatG(spec.max_change_per_s)}</td>
                        <td data-label="Confirm">{tierWord(spec.confirm, effectiveHazard(file) === "high")}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {/if}
            {#if Object.keys(file.read).length}
              <div class="table-wrap stack">
                <table>
                  <caption class="legend">Read channels</caption>
                  <thead>
                    <tr><th scope="col">Channel</th><th scope="col">Value</th><th scope="col">Simulate a reading</th></tr>
                  </thead>
                  <tbody>
                    {#each Object.entries(file.read) as [name, spec] (name)}
                      <tr>
                        <td data-label="Channel" class="mono">{name}</td>
                        <td data-label="Value" class="mono">{spec.type === "image" ? "frames" : show(valueOf(id, name))}{#if spec.unit}&nbsp;{displayUnit(spec.unit)}{/if}</td>
                        <td data-label="Simulate">
                          {#if spec.type !== "image"}
                            <form class="sim" onsubmit={(event) => { event.preventDefault(); setReading(id, name); }}>
                              <label class="visually-hidden" for={`pg-read-${name}`}>Simulated reading for {name}</label>
                              <input id={`pg-read-${name}`} class="mono" bind:value={readingDrafts[`${id}.${name}`]} />
                              <button type="submit" class="button quiet small">Set</button>
                            </form>
                          {/if}
                        </td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {/if}
            {#if companions.length}
              <p class="muted note">
                This file's interlocks name
                {#each companions as other, index (other.id)}{index ? ", " : ""}<code>{other.id}</code>{/each}, so the Playground loads those devices too.
              </p>
            {/if}
          {:else}
            <p class="muted">Fix the device file to load its simulated device.</p>
          {/if}
        </section>

        {#if !ready.length}
          <section class="panel" aria-labelledby="pg-log-title">
            <div class="panel-head">
              <h2 id="pg-log-title">Message log</h2>
            </div>
            <TraceList {exchanges} />
          </section>
        {/if}
      </div>
    </div>
    </div>
  </details>
</div>

<style>
  .frame {
    container: playground / inline-size;
    display: grid;
    gap: var(--s-6);
  }

  .try {
    display: grid;
    gap: var(--s-4);
  }

  .try h2 {
    font-size: var(--t-h3);
  }

  .try-grid {
    display: grid;
    gap: var(--s-5);
    align-items: start;
  }

  .quick {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-2);
  }

  .quick-button {
    min-height: 44px;
  }

  .answers {
    display: grid;
    gap: var(--s-2);
    min-width: 0;
  }

  .small-head {
    font-size: var(--t-body);
    font-weight: 700;
  }

  .printer {
    display: grid;
    gap: var(--s-3);
    padding: var(--s-4);
    background: var(--surface);
    border: var(--rule);
    border-radius: var(--radius);
  }

  .readout {
    display: grid;
    gap: var(--s-2);
    margin: 0;
  }

  .readout div {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: var(--s-3);
  }

  .readout dt {
    color: var(--text-2);
  }

  .readout dd {
    margin: 0;
    font-weight: 700;
  }

  .build {
    border-top: var(--rule);
    padding-top: var(--s-4);
  }

  .build > summary {
    cursor: pointer;
    font-weight: 700;
    font-size: var(--t-h3);
    width: max-content;
    max-width: 100%;
  }

  .build-body {
    display: flow-root;
  }

  .build-body > .playground {
    margin-top: var(--s-4);
  }

  .as-label {
    display: inline-flex;
    align-items: center;
  }

  .printer .stop-area {
    margin-top: var(--s-2);
  }

  .playground {
    display: grid;
    gap: var(--s-5);
    align-items: start;
  }

  .panel {
    border: var(--rule);
    border-radius: var(--radius);
    padding: var(--s-4);
    min-width: 0;
    container-type: inline-size;
  }

  .panel-head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--s-2) var(--s-4);
    margin-bottom: var(--s-3);
  }

  h2 {
    font-size: var(--t-h3);
  }

  .editor .panel-head {
    display: grid;
    justify-content: stretch;
  }

  .example {
    display: grid;
    gap: var(--s-1);
    min-width: 0;
  }

  .example select {
    width: 100%;
    min-width: 0;
  }

  textarea {
    display: block;
    width: 100%;
    min-height: 420px;
    padding: var(--s-3);
    background: var(--surface);
    font-family: var(--font-mono);
    font-size: 14px;
    line-height: 1.6;
    resize: vertical;
    tab-size: 2;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    overflow-x: hidden;
    overflow-y: auto;
  }

  .problems {
    margin-top: var(--s-3);
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
  }

  .side {
    display: grid;
    gap: var(--s-5);
    min-width: 0;
  }

  .facts {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--s-2) var(--s-4);
    margin: 0 0 var(--s-4);
  }

  .facts dd {
    margin: 0;
  }

  caption {
    text-align: left;
    padding-bottom: var(--s-1);
  }

  .table-wrap + .table-wrap {
    margin-top: var(--s-4);
  }

  .sim {
    display: flex;
    gap: var(--s-1);
  }

  .sim input {
    width: 7em;
    min-height: 32px;
  }

  .button.small {
    min-height: 32px;
    padding: 0 var(--s-3);
  }

  .note {
    margin-top: var(--s-3);
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

  .waiting {
    margin-top: var(--s-4);
    padding-top: var(--s-3);
    border-top: var(--rule);
  }

  .waiting-head {
    font-weight: 700;
  }

  .waiting ul {
    list-style: none;
    margin: var(--s-2) 0 0;
    padding: 0;
    display: grid;
    gap: var(--s-2);
  }

  .waiting li {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--s-2) var(--s-3);
  }

  .decide {
    display: flex;
    gap: var(--s-2);
    margin-left: auto;
  }

  .button.person {
    --oh-line: var(--text);
    background: var(--text);
    color: var(--bg);
  }

  .stop-area {
    margin-top: var(--s-5);
    padding-top: var(--s-4);
    border-top: var(--rule);
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--s-3) var(--s-4);
  }

  .stop {
    min-height: 56px;
    min-width: 160px;
    padding: 0 var(--s-6);
    border: 2px solid var(--blocked);
    border-radius: var(--radius);
    background: var(--blocked);
    color: var(--bg);
    font: inherit;
    font-size: var(--t-h3);
    font-weight: 800;
    letter-spacing: 0.02em;
    cursor: pointer;
  }

  .stop:focus-visible {
    outline: 3px solid var(--text);
    outline-offset: 3px;
  }

  .stopped-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--s-2) var(--s-3);
  }

  .stopped-row input {
    width: 10em;
  }

  .unlock-error {
    width: 100%;
    color: var(--text);
  }

  @container (min-width: 440px) {
    .fields {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .fields .field:first-child {
      grid-column: 1 / -1;
    }
  }

  @container (min-width: 760px) {
    .fields {
      grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr);
    }

    .fields .field:first-child {
      grid-column: auto;
    }
  }

  @container (min-width: 600px) {
    .facts {
      grid-template-columns: repeat(4, auto);
      justify-content: start;
      column-gap: var(--s-6);
    }
  }

  @container playground (min-width: 760px) {
    .try-grid {
      grid-template-columns: minmax(0, 1fr) 300px;
      grid-template-rows: auto 1fr;
      grid-template-areas: "quick printer" "answers printer";
    }

    .quick {
      grid-area: quick;
    }

    .printer {
      grid-area: printer;
    }

    .answers {
      grid-area: answers;
    }
  }

  @container playground (min-width: 900px) {
    .playground {
      grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
    }

    .editor {
      position: sticky;
      top: 76px;
    }

    textarea {
      min-height: calc(100dvh - 330px);
    }
  }
</style>
