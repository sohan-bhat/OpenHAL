<script lang="ts">
  import CameraFrame from "../components/CameraFrame.svelte";
  import Reason from "../components/Reason.svelte";
  import { onDestroy } from "svelte";
  import Json from "../components/Json.svelte";
  import StatusMark from "../components/StatusMark.svelte";
  import TraceArrow from "../components/TraceArrow.svelte";
  import { api } from "../lib/api";
  import { askedAgo, askOf } from "../lib/asks";
  import { camerasFor, describeDecision, isSimulated, type Camera } from "../lib/devices";
  import { latestImage } from "../lib/frames.svelte";
  import { inspector } from "../lib/state.svelte";
  import { decisionStatus } from "../lib/status";
  import { identifiersOf } from "../lib/units";
  import type { Command, ConfirmationRequest, Decision } from "../lib/types";

  let recent = $state<ConfirmationRequest[]>([]);
  let fetchedAt = $state(Date.now());
  let now = $state(Date.now());
  let reasons = $state<Record<string, string>>({});
  let busy = $state<Record<string, boolean>>({});
  let errors = $state<Record<string, string>>({});
  let outcomes = $state<Record<string, { by: "approved" | "rejected"; decision: Decision | null }>>({});
  let chosen = $state<Record<string, string>>({});

  const timer = setInterval(() => (now = Date.now()), 1000);
  onDestroy(() => clearInterval(timer));

  const pending = $derived(inspector.confirmations.filter((request) => request.status === "pending"));
  const decided = $derived(recent.filter((request) => request.status !== "pending").slice(0, 20));

  let watching = false;
  $effect(() => {
    void inspector.auditTick;
    if (watching) void load();
    watching = true;
  });

  const settle = inspector.hold();
  void Promise.race([
    Promise.all([load(), inspector.loadViews()]),
    new Promise((resolve) => setTimeout(resolve, 1500)),
  ]).then(() => settle());

  async function load() {
    try {
      recent = await api.confirmations(true);
      fetchedAt = Date.now();
    } catch {
      return;
    }
  }

  $effect(() => {
    void inspector.confirmations;
    fetchedAt = Date.now();
  });

  $effect(() => {
    if (pending.length && inspector.devices.length) void inspector.loadViews();
  });

  const STORE = "openhal.inspector.camera.";
  const cameraKey = (camera: Camera) => `${camera.device}/${camera.channel}`;

  function stored(device: string): string | null {
    try {
      return localStorage.getItem(STORE + device);
    } catch {
      return null;
    }
  }

  function keep(device: string, key: string): void {
    chosen = { ...chosen, [device]: key };
    try {
      if (key) localStorage.setItem(STORE + device, key);
      else localStorage.removeItem(STORE + device);
    } catch {
      return;
    }
  }

  function cameraFor(device: string, cameras: Camera[]): Camera | undefined {
    const picked = device in chosen ? chosen[device] : stored(device);
    if (picked !== null && picked !== undefined) return cameras.find((camera) => cameraKey(camera) === picked);
    return cameras.find((camera) => camera.device === device);
  }

  function latestOf(camera: Camera) {
    const spec = inspector.views[camera.device]?.read[camera.channel];
    return spec ? latestImage(spec.value, spec.known) : null;
  }

  function asked(request: ConfirmationRequest): string {
    return askedAgo(request.expires_at - request.created_at - remaining(request));
  }

  function remaining(request: ConfirmationRequest): number {
    return Math.max(0, Math.round(request.expires_in_s - (now - fetchedAt) / 1000));
  }

  function method(command: Command): string {
    return command.kind === "action" ? "hal/action" : "hal/write";
  }

  function params(command: Command): Record<string, unknown> {
    const { kind: _kind, ...rest } = command;
    return rest;
  }

  async function approve(request: ConfirmationRequest) {
    busy = { ...busy, [request.id]: true };
    try {
      const decision = await api.approve(request.id);
      outcomes = { ...outcomes, [request.id]: { by: "approved", decision } };
    } catch (error) {
      errors = { ...errors, [request.id]: error instanceof Error ? error.message : "Approving failed." };
    }
    busy = { ...busy, [request.id]: false };
    await Promise.all([inspector.refreshConfirmations(), load()]);
  }

  async function reject(request: ConfirmationRequest) {
    busy = { ...busy, [request.id]: true };
    try {
      await api.reject(request.id, reasons[request.id] ?? "");
      outcomes = { ...outcomes, [request.id]: { by: "rejected", decision: null } };
    } catch (error) {
      errors = { ...errors, [request.id]: error instanceof Error ? error.message : "Rejecting failed." };
    }
    busy = { ...busy, [request.id]: false };
    await Promise.all([inspector.refreshConfirmations(), load()]);
  }
</script>

<div class="view">
  <header class="section">
    <h1>Confirmations</h1>
    <p class="muted">
      Commands an agent or routine sent that need a person. Approving runs every Safety Kernel check again against the
      current state before anything reaches the device.
    </p>
  </header>

  <section class="section" aria-labelledby="pending-title">
    <h2 id="pending-title">Pending <span class="muted mono">{pending.length}</span></h2>
    {#if !pending.length}
      <p class="empty">No command is held for a person. A command with confirmation tier <code>confirm</code> appears here.</p>
    {:else}
      <ol class="requests">
        {#each pending as request (request.id)}
          {@const dry = describeDecision(request.dry_run)}
          {@const ask = askOf(request, inspector.views[request.command.device])}
          {@const device = request.command.device}
          {@const cameras = camerasFor(device, inspector.views)}
          {@const camera = cameraFor(device, cameras)}
          {@const pickable = cameras.length > 1 || !cameras.some((option) => option.device === device)}
          <li class="request appear" class:with-camera={cameras.length > 0} aria-labelledby="req-{request.id}">
            <div class="asked agent-rule">
              <h3 id="req-{request.id}" class="ask">
                {ask.actor} <span class="mono nobreak">{ask.name}</span> sends a request to {ask.verb} <span class="mono nobreak">{ask.target}</span>{#if ask.value}{ask.verb === "set" ? " to " : " with "}<span class="mono nobreak">{ask.value}</span>{/if} on {ask.device}.
              </h3>
              <p class="who">
                <span class="mono muted nobreak">{request.requested_by}</span>
                <span class="muted">requested {asked(request)}</span>
                <span class="mono muted">request <span class="nobreak">{request.id}</span></span>
              </p>
              <p class="trace">
                <TraceArrow arrow="right" />
                <span class="mono method">{method(request.command)}</span>
                <Json value={params(request.command)} />
              </p>
              <dl class="facts">
                {#if ask.does}
                  <div><dt class="label">what {ask.target} does</dt><dd>{ask.does}</dd></div>
                {/if}
                {#if ask.limit}
                  <div><dt class="label">limit</dt><dd class="mono">{ask.limit}</dd></div>
                {/if}
                <div>
                  <dt class="label">why the request is held</dt>
                  <dd><Reason text={ask.why} code={[ask.file ?? "", ask.target].filter(Boolean)} /></dd>
                </div>
                {#if dry.tone !== "pending"}
                  <div>
                    <dt class="label">dry run</dt>
                    <dd class="dry">
                      <StatusMark tone={dry.tone === "granted" ? "ok" : "blocked"} label={dry.word} />
                      {#if dry.head && dry.tone !== "granted"}<span class="mono code {dry.tone}">{dry.head}</span>{/if}
                      <span><Reason text={request.dry_run.message} code={identifiersOf(request.dry_run.device, request.dry_run.target)} /></span>
                    </dd>
                  </div>
                {/if}
              </dl>
            </div>
            {#snippet picker()}
              <label class="field pick">
                <span>{camera ? "Camera" : "Show a camera"}</span>
                <select
                  value={camera ? cameraKey(camera) : ""}
                  aria-describedby={camera ? undefined : `pick-${request.id}`}
                  onchange={(event) => keep(device, event.currentTarget.value)}
                >
                  <option value="">None</option>
                  {#each cameras as option (cameraKey(option))}
                    <option value={cameraKey(option)}>{option.name}, {option.channel}</option>
                  {/each}
                </select>
              </label>
            {/snippet}
            {#if cameras.length}
              <div class="camera">
                {#if camera}
                  <CameraFrame
                    device={camera.device}
                    channel={camera.channel}
                    label="{camera.name}, {camera.channel}"
                    latest={latestOf(camera)}
                    width={480}
                    demo={isSimulated(inspector.views[camera.device] ?? {})}
                  >
                    {#snippet heading()}
                      {#if pickable}
                        {@render picker()}
                      {:else}
                        <p class="camera-name">
                          <span class="label">camera</span>
                          <span>{camera.name}</span>
                          <span class="mono muted nobreak">{camera.device}.{camera.channel}</span>
                        </p>
                      {/if}
                    {/snippet}
                  </CameraFrame>
                {:else}
                  {@render picker()}
                  <p class="muted small" id="pick-{request.id}">Pick the camera pointed at {ask.device}. This browser keeps the choice.</p>
                {/if}
              </div>
            {/if}
            <form class="decide human-surface" onsubmit={(event) => event.preventDefault()}>
              <span class="label">your decision</span>
              <p class="expires">
                Expires in <span class="mono countdown">{String(remaining(request)).padStart(3, " ")} s</span>
              </p>
              <div class="buttons">
                <button type="button" class="button primary" disabled={busy[request.id]} onclick={() => approve(request)}>
                  Approve and {ask.verb} {ask.target}
                </button>
              </div>
              <p class="muted small">The Safety Kernel checks every limit again before the command runs.</p>
              <div class="buttons">
                <label class="field reason">
                  <span>Reason to reject, optional</span>
                  <input type="text" bind:value={reasons[request.id]} maxlength="200" autocomplete="off" />
                </label>
                <button type="button" class="button" disabled={busy[request.id]} onclick={() => reject(request)}>Reject</button>
              </div>
              {#if errors[request.id]}<p class="problem" role="alert">{errors[request.id]}</p>{/if}
            </form>
          </li>
        {/each}
      </ol>
    {/if}
  </section>

  {#if Object.keys(outcomes).length}
    <section class="section" aria-labelledby="yours-title" aria-live="polite">
      <h2 id="yours-title">Your decisions</h2>
      <ul class="decisions">
        {#each Object.entries(outcomes) as [id, outcome] (id)}
          {@const result = outcome.decision ? describeDecision(outcome.decision) : null}
          <li class="human-surface decision">
            <span class="mono">request {id}</span>
            <StatusMark tone={outcome.by === "approved" ? "ok" : "neutral"} label={outcome.by} />
            {#if result}
              <span class="label">result</span>
              <StatusMark tone={result.tone === "granted" ? "ok" : "blocked"} label={result.word} />
              {#if result.head && result.tone !== "granted"}<span class="mono code blocked">{result.head}</span>{/if}
              {#if outcome.decision}<span><Reason text={outcome.decision.message} code={identifiersOf(outcome.decision.device, outcome.decision.target)} /></span>{/if}
            {/if}
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  <section class="section" aria-labelledby="decided-title">
    <h2 id="decided-title">Decided recently</h2>
    {#if !decided.length}
      <p class="empty">No decided requests yet.</p>
    {:else}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div class="table-scroll" tabindex="0" role="region" aria-label="Decided requests table">
        <table class="grid">
        <thead>
          <tr><th scope="col">Request</th><th scope="col">Command</th><th scope="col">Requested by</th><th scope="col">Status</th><th scope="col">Decided by</th></tr>
        </thead>
        <tbody>
          {#each decided as request (request.id)}
            {@const status = decisionStatus(request.status)}
            <tr>
              <td class="mono">{request.id}</td>
              <td><span class="mono method">{method(request.command)}</span> <Json value={params(request.command)} /></td>
              <td class="mono">{request.requested_by}</td>
              <td><StatusMark tone={status.tone} label={status.label} /></td>
              <td class="mono">{request.decided_by ?? "expired"}</td>
            </tr>
          {/each}
        </tbody>
        </table>
      </div>
    {/if}
  </section>
</div>

<style>
  .view {
    display: grid;
    max-width: 1040px;
  }

  header p {
    max-width: 72ch;
  }

  .requests {
    display: grid;
    gap: var(--s-4);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .request {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(260px, 340px);
    grid-template-areas: "asked decide";
    border: var(--rule);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .request.with-camera {
    grid-template-rows: auto 1fr;
    grid-template-areas:
      "asked decide"
      "camera decide";
  }

  .asked {
    grid-area: asked;
    display: grid;
    gap: var(--s-2);
    padding: var(--s-3) var(--s-4);
    margin: var(--s-2) 0 var(--s-2) var(--s-2);
  }

  .ask {
    font-size: 18px;
    line-height: 1.4;
  }

  .ask .mono {
    font-size: 0.92em;
  }

  .facts {
    display: grid;
    gap: var(--s-2);
    margin: var(--s-1) 0 0;
  }

  .facts div {
    display: grid;
    grid-template-columns: 9.5em minmax(0, 1fr);
    gap: var(--s-3);
    align-items: baseline;
  }

  .facts dd {
    margin: 0;
  }

  .camera {
    grid-area: camera;
    display: grid;
    align-content: start;
    gap: var(--s-2);
    padding: var(--s-2) var(--s-4) var(--s-4) calc(var(--s-2) + 2px + var(--s-4));
  }

  .camera-name {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-2);
  }

  .pick {
    width: min(100%, 320px);
  }

  .pick select {
    width: 100%;
  }

  .who,
  .dry {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-3);
  }

  .small {
    font-size: var(--t-label);
  }

  .trace {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-2) var(--s-3);
  }

  .method {
    color: var(--syn-method);
    font-weight: 700;
  }

  .code.blocked,
  .code.failed {
    color: var(--blocked);
    font-weight: 700;
  }

  .code.pending {
    color: var(--confirm);
    font-weight: 700;
  }

  .countdown {
    font-variant-numeric: tabular-nums;
    white-space: pre;
  }

  .decide {
    grid-area: decide;
    display: grid;
    align-content: start;
    gap: var(--s-3);
    padding: var(--s-4);
    border-left: 2px solid var(--text);
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: var(--s-2);
  }

  .reason {
    flex: 1 1 160px;
  }

  .reason input {
    width: 100%;
  }

  .decisions {
    display: grid;
    gap: var(--s-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .decision {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-3);
    padding: var(--s-3) var(--s-4);
  }

  @media (max-width: 767px) {
    .request,
    .request.with-camera {
      grid-template-columns: 1fr;
      grid-template-rows: none;
      grid-template-areas: "asked" "camera" "decide";
    }

    .facts div {
      grid-template-columns: 1fr;
      gap: 2px;
    }

    .camera {
      padding-left: var(--s-4);
    }

    .decide {
      border-left: 0;
      border-top: 2px solid var(--text);
    }
  }
</style>
