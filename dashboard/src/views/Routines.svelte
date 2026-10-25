<script lang="ts">
  import Prose from "../components/Prose.svelte";
  import StatusMark from "../components/StatusMark.svelte";
  import { api } from "../lib/api";
  import { formatDateTime } from "../lib/units";
  import { fromKernelCode } from "../lib/protocol";
  import { href, router } from "../lib/router.svelte";
  import { inspector } from "../lib/state.svelte";
  import { decisionStatus } from "../lib/status";
  import { principalInfo } from "../lib/trace";
  import type { Routine, RoutineDryRun, RoutineSummary } from "../lib/types";

  let routines = $state<RoutineSummary[]>([]);
  let loaded = $state(false);
  let detail = $state<Routine | null>(null);
  let dryRun = $state<RoutineDryRun | null>(null);
  let busy = $state(false);
  let message = $state<{ tone: "ok" | "blocked"; text: string } | null>(null);

  const selected = $derived(router.route.id ?? routines[0]?.id ?? null);

  $effect(() => {
    void inspector.routineTick;
    void loadList();
  });

  $effect(() => {
    const id = selected;
    void inspector.routineTick;
    dryRun = null;
    message = null;
    if (id) void loadDetail(id);
  });

  const settleList = inspector.hold();
  const settleDetail = inspector.hold();

  async function loadList() {
    try {
      routines = await api.routines();
    } catch {
      routines = [];
    }
    loaded = true;
    settleList();
    if (!router.route.id && !routines.length) settleDetail();
  }

  async function loadDetail(id: string) {
    try {
      detail = await api.routine(id);
      dryRun = detail.last_dry_run;
    } catch {
      detail = null;
    }
    settleDetail();
  }

  async function act(kind: "dry" | "enable" | "disable" | "run") {
    if (!detail) return;
    busy = true;
    message = null;
    const id = detail.id;
    try {
      if (kind === "dry") dryRun = await api.routineDryRun(id);
      if (kind === "enable") await api.routineEnable(id);
      if (kind === "disable") await api.routineDisable(id);
      if (kind === "run") {
        const run = await api.routineRun(id);
        message = { tone: run.status === "ok" ? "ok" : "blocked", text: `Run ${run.run_id} ${run.status}. ${run.message}`.trim() };
      }
    } catch (error) {
      message = { tone: "blocked", text: error instanceof Error ? error.message : "The hub refused." };
    }
    busy = false;
    await Promise.all([loadList(), loadDetail(id)]);
  }


  function decisionLine(decision: Record<string, unknown>): { status: string; text: string; code: string | null; step: string } {
    return {
      status: String(decision.status ?? ""),
      text: String(decision.message ?? ""),
      code: typeof decision.code === "string" ? decision.code : null,
      step: String(decision.step ?? decision.path ?? decision.target ?? ""),
    };
  }
</script>

<div class="view">
  <header class="section">
    <h1>Routines</h1>
    <p class="muted">
      Stored routines run as their own Principal through the Safety Kernel. A new routine starts disabled. Only a person
      enables it.
    </p>
  </header>

  {#if loaded && !routines.length}
    <p class="empty">No routines. Add one with <code>openhal routine new keep-cool --file keep-cool.routine.yaml</code>.</p>
  {:else}
    <div class="layout">
      <nav class="list" aria-label="Routines">
        <ul>
          {#each routines as routine (routine.id)}
            {@const drafted = principalInfo(routine.drafted_by)}
            <li>
              <a href={href("routines", routine.id)} aria-current={selected === routine.id ? "page" : undefined}>
                <span class="mono name">{routine.id}</span>
                <StatusMark tone={routine.enabled ? "ok" : "neutral"} label={routine.enabled ? "enabled" : "disabled"} />
                <span class="muted small">{routine.max_hazard} hazard, {routine.kind}</span>
                {#if routine.drafted_by}
                  <span class="small drafted" class:agent={drafted.kind === "agent"}>drafted by <span class="mono">{routine.drafted_by}</span></span>
                {/if}
              </a>
            </li>
          {/each}
        </ul>
      </nav>

      {#if detail}
        <article class="detail" aria-labelledby="routine-title">
          <div class="section-head">
            <h2 id="routine-title" class="mono">{detail.id}</h2>
            <StatusMark tone={detail.enabled ? "ok" : "neutral"} label={detail.enabled ? "enabled" : "disabled"} />
          </div>
          <dl class="facts">
            <div><dt class="label">devices</dt><dd class="mono">{detail.devices.join(", ") || "none"}</dd></div>
            <div><dt class="label">max hazard</dt><dd>{detail.max_hazard}</dd></div>
            <div><dt class="label">triggers</dt><dd class="mono">{detail.triggers.join(", ") || "manual"}</dd></div>
            <div><dt class="label">sha-256</dt><dd class="mono">{detail.sha256.slice(0, 16)}</dd></div>
            {#if detail.enabled_by}<div><dt class="label">enabled by</dt><dd class="mono">{detail.enabled_by}</dd></div>{/if}
            {#if detail.disabled_reason}<div><dt class="label">disabled because</dt><dd>{detail.disabled_reason}</dd></div>{/if}
          </dl>

          <div class="buttons">
            <button class="button" type="button" disabled={busy} onclick={() => act("dry")}>Dry run</button>
            {#if detail.enabled}
              <button class="button" type="button" disabled={busy} onclick={() => act("disable")}>Disable</button>
            {:else}
              <button class="button primary" type="button" disabled={busy} onclick={() => act("enable")}>Enable</button>
            {/if}
            <button class="button" type="button" disabled={busy} onclick={() => act("run")}>Run now</button>
          </div>
          {#if message}
            <p class="result {message.tone}" role="status">{message.text}</p>
          {/if}

          {#if dryRun}
            <section class="block" aria-labelledby="dry-title">
              <div class="section-head">
                <h3 id="dry-title">Dry run</h3>
                <StatusMark tone={dryRun.ok ? "ok" : "blocked"} label={dryRun.ok ? "every command allowed" : "not every command allowed"} />
              </div>
              <ol class="decisions">
                {#each dryRun.decisions as raw, index (index)}
                  {@const decision = decisionLine(raw)}
                  {@const mark = decisionStatus(decision.status)}
                  {@const registry = fromKernelCode(decision.code)}
                  <li>
                    <StatusMark tone={mark.tone} label={mark.label} />
                    {#if decision.step}<span class="mono muted">{decision.step}</span>{/if}
                    {#if registry && decision.status !== "allowed"}
                      <span class="mono code {mark.tone}">{registry.code} {registry.name}</span>
                    {/if}
                    <span class="mono"><Prose text={decision.text} /></span>
                  </li>
                {/each}
              </ol>
              {#each dryRun.problems as problem, index (index)}<p class="problem">{problem}</p>{/each}
            </section>
          {/if}

          <section class="block" aria-labelledby="source-title">
            <h3 id="source-title">Source</h3>
            <pre class="source"><code>{detail.source_raw}</code></pre>
          </section>

          <section class="block" aria-labelledby="history-title">
            <h3 id="history-title">Run history</h3>
            {#if !detail.history.length}
              <p class="empty">This routine has not run yet.</p>
            {:else}
              <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
              <div class="table-scroll" tabindex="0" role="region" aria-label="Run history table">
                <table class="grid">
                <thead><tr><th scope="col">Run</th><th scope="col">Trigger</th><th scope="col">Started</th><th scope="col">Status</th><th scope="col">Message</th></tr></thead>
                <tbody>
                  {#each detail.history as run (run.run_id)}
                    {@const mark = decisionStatus(run.status)}
                    <tr>
                      <td class="mono">{run.run_id}</td>
                      <td class="mono">{run.trigger ?? ""}</td>
                      <td class="mono">{formatDateTime(run.started_at)}</td>
                      <td><StatusMark tone={mark.tone} label={mark.label} /></td>
                      <td>{run.message}</td>
                    </tr>
                  {/each}
                </tbody>
                </table>
              </div>
            {/if}
          </section>
        </article>
      {/if}
    </div>
  {/if}
</div>

<style>
  .view {
    display: grid;
    max-width: 1100px;
  }

  .layout {
    display: grid;
    grid-template-columns: 240px minmax(0, 1fr);
    gap: var(--s-5);
    padding-top: var(--s-4);
    border-top: var(--rule);
  }

  .list ul {
    display: grid;
    gap: var(--s-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .list a {
    display: grid;
    gap: var(--s-1);
    padding: var(--s-3);
    border: var(--rule);
    border-radius: var(--radius);
    color: var(--text);
    text-decoration: none;
  }

  .list a[aria-current="page"] {
    border-color: var(--accent);
    border-left-width: 3px;
    padding-left: calc(var(--s-3) - 2px);
    background: var(--surface);
  }

  .name {
    font-weight: 700;
    color: var(--accent);
  }

  .small {
    font-size: var(--t-label);
  }

  .drafted.agent {
    padding-left: var(--s-2);
    border-left: 2px dashed var(--text-2);
  }

  .detail {
    display: grid;
    gap: var(--s-4);
    align-content: start;
  }

  .facts {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
    gap: var(--s-3) var(--s-4);
    margin: 0;
  }

  .facts div {
    display: grid;
    gap: 2px;
  }

  dd {
    margin: 0;
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-2);
  }

  .result {
    padding: var(--s-2) var(--s-3);
    background: var(--surface);
    border-left: 3px solid var(--ok);
  }

  .result.blocked {
    border-left-color: var(--blocked);
  }

  .block {
    display: grid;
    gap: var(--s-3);
    padding-top: var(--s-4);
    border-top: var(--rule);
  }

  .decisions {
    display: grid;
    gap: var(--s-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .decisions li {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-3);
  }

  .code {
    font-weight: 700;
  }

  .code.blocked {
    color: var(--blocked);
  }

  .code.confirm {
    color: var(--confirm);
  }

  .source {
    padding: var(--s-3) var(--s-4);
    border: var(--rule);
    border-radius: var(--radius);
    background: var(--surface);
  }

  @media (max-width: 767px) {
    .layout {
      grid-template-columns: 1fr;
    }
  }
</style>
