<script lang="ts">
  import { onDestroy } from "svelte";
  import Json from "../components/Json.svelte";
  import StatusMark from "../components/StatusMark.svelte";
  import TraceArrow from "../components/TraceArrow.svelte";
  import { api } from "../lib/api";
  import { describeDecision } from "../lib/devices";
  import { inspector } from "../lib/state.svelte";
  import { decisionStatus } from "../lib/status";
  import type { Command, ConfirmationRequest, Decision } from "../lib/types";

  let recent = $state<ConfirmationRequest[]>([]);
  let fetchedAt = $state(Date.now());
  let now = $state(Date.now());
  let reasons = $state<Record<string, string>>({});
  let busy = $state<Record<string, boolean>>({});
  let errors = $state<Record<string, string>>({});
  let outcomes = $state<Record<string, { by: "approved" | "rejected"; decision: Decision | null }>>({});

  const timer = setInterval(() => (now = Date.now()), 1000);
  onDestroy(() => clearInterval(timer));

  const pending = $derived(inspector.confirmations.filter((request) => request.status === "pending"));
  const decided = $derived(recent.filter((request) => request.status !== "pending").slice(0, 20));

  $effect(() => {
    void inspector.auditTick;
    void load();
  });

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
      <p class="empty">Nothing waits for a person. A command with confirmation tier <code>confirm</code> appears here.</p>
    {:else}
      <ol class="requests">
        {#each pending as request (request.id)}
          {@const dry = describeDecision(request.dry_run)}
          <li class="request appear" aria-labelledby="req-{request.id}">
            <div class="asked agent-rule">
              <p class="who">
                <span class="label">requested by</span>
                <span class="mono client">{request.requested_by}</span>
                <span class="mono muted">request {request.id}</span>
              </p>
              <p id="req-{request.id}" class="trace">
                <TraceArrow arrow="right" />
                <span class="mono method">{method(request.command)}</span>
                <Json value={params(request.command)} />
              </p>
              <div class="dry">
                <span class="label">dry run</span>
                <StatusMark
                  tone={dry.tone === "granted" ? "ok" : dry.tone === "pending" ? "confirm" : "blocked"}
                  label={dry.word}
                />
                {#if dry.head && dry.tone !== "granted"}<span class="mono code {dry.tone}">{dry.head}</span>{/if}
                <span class="mono">{request.dry_run.message}</span>
              </div>
              <p class="expires">
                <span class="label">expires in</span>
                <span class="mono countdown">{String(remaining(request)).padStart(3, " ")} s</span>
              </p>
            </div>
            <form class="decide human-surface" onsubmit={(event) => event.preventDefault()}>
              <span class="label">your decision</span>
              <div class="buttons">
                <button type="button" class="button primary" disabled={busy[request.id]} onclick={() => approve(request)}>
                  Approve
                </button>
              </div>
              <div class="buttons">
                <label class="field reason">
                  <span>Reason to reject, optional</span>
                  <input type="text" bind:value={reasons[request.id]} maxlength="200" />
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
              <span class="mono">{outcome.decision?.message}</span>
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
    border: var(--rule);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .asked {
    display: grid;
    gap: var(--s-2);
    padding: var(--s-3) var(--s-4);
    margin: var(--s-2) 0 var(--s-2) var(--s-2);
  }

  .who,
  .dry,
  .expires {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-3);
  }

  .client {
    font-weight: 700;
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
    .request {
      grid-template-columns: 1fr;
    }

    .decide {
      border-left: 0;
      border-top: 2px solid var(--text);
    }
  }
</style>
