<script lang="ts">
  import Json from "../components/Json.svelte";
  import StatusMark from "../components/StatusMark.svelte";
  import { api } from "../lib/api";
  import { diffLines, diffStats } from "../lib/diff";
  import { href, router } from "../lib/router.svelte";
  import { inspector } from "../lib/state.svelte";
  import type { Question, TestStep, UnknownDevice, WriterSession } from "../lib/types";
  import { dataBlock, unitSymbol } from "../lib/units";

  const STEPS: { status: WriterSession["status"]; label: string }[] = [
    { status: "detecting", label: "Detect" },
    { status: "drafting", label: "Draft" },
    { status: "interview", label: "Limits interview" },
    { status: "ready", label: "Review" },
    { status: "saved", label: "Saved" },
  ];

  let unknown = $state<UnknownDevice[]>([]);
  let unknownLoaded = $state(false);
  let session = $state<WriterSession | null>(null);
  let questions = $state<Question[]>([]);
  let answers = $state<Record<string, string>>({});
  let baseline = $state<string | null>(null);
  let plan = $state<{ steps: TestStep[]; problems: string[] } | null>(null);
  let proposal = $state("");
  let saveAs = $state("");
  let saved = $state<{ path: string; device_id: string; writable: boolean } | null>(null);
  let busy = $state(false);
  let error = $state<string | null>(null);
  let discoverNote = $state<string | null>(null);

  const sessionId = $derived(router.route.id);
  const stepIndex = $derived(session ? STEPS.findIndex((step) => step.status === session!.status) : -1);
  const diff = $derived(baseline && session?.draft_yaml && session.status !== "interview" ? diffLines(baseline, session.draft_yaml) : null);
  const stats = $derived(diff ? diffStats(diff) : null);
  const allAnswered = $derived(questions.length > 0 && questions.every((question) => (answers[question.id] ?? "").trim() !== ""));

  $effect(() => {
    void loadUnknown();
  });

  $effect(() => {
    const id = sessionId;
    saved = null;
    plan = null;
    error = null;
    if (id) void loadSession(id);
    else session = null;
  });

  async function loadUnknown() {
    try {
      unknown = await api.unknownDevices();
    } catch {
      unknown = [];
    }
    unknownLoaded = true;
  }

  async function loadSession(id: string) {
    try {
      session = await api.writerSession(id);
      await afterSession();
    } catch (failure) {
      error = failure instanceof Error ? failure.message : "The session did not load.";
    }
  }

  async function afterSession() {
    if (!session) return;
    if (session.status === "interview") {
      if (session.draft_yaml) baseline = session.draft_yaml;
      questions = (await api.writerInterview(session.id)).questions;
    } else {
      questions = [];
    }
    if (!saveAs) {
      const match = session.draft_yaml?.match(/^id:\s*([a-z0-9][a-z0-9_-]*)/m);
      saveAs = match?.[1] ?? "bench-board";
    }
    if (session.status === "ready" || session.status === "interview") {
      try {
        plan = await api.writerTestPlan(session.id);
      } catch {
        plan = null;
      }
    }
  }

  async function guard(work: () => Promise<void>) {
    busy = true;
    error = null;
    try {
      await work();
    } catch (failure) {
      error = failure instanceof Error ? failure.message : "The hub refused.";
    }
    busy = false;
  }

  function start(device: UnknownDevice) {
    void guard(async () => {
      const created = await api.writerStart({ unknown_id: device.id });
      baseline = null;
      answers = {};
      saveAs = "";
      router.go("writer", created.id);
    });
  }

  function discover() {
    void guard(async () => {
      const result = await api.discover();
      unknown = result.unknown;
      discoverNote = `${result.matched.length} matched a library file, ${result.unknown.length} unknown, ${result.errors.length} driver errors.`;
    });
  }

  function propose(event: SubmitEvent) {
    event.preventDefault();
    if (!session) return;
    const id = session.id;
    void guard(async () => {
      session = await api.writerPropose(id, proposal);
      await afterSession();
    });
  }

  function suggestedText(question: Question): string {
    const value = question.suggested;
    if (value === null || value === undefined) return "none";
    if (typeof value === "number" && question.unit) return `${value} ${unitSymbol(question.unit)}`;
    return String(value);
  }

  function submitAnswers(event: SubmitEvent) {
    event.preventDefault();
    if (!session) return;
    const id = session.id;
    void guard(async () => {
      session = await api.writerAnswers(id, { ...answers });
      await afterSession();
    });
  }

  function save(event: SubmitEvent) {
    event.preventDefault();
    if (!session) return;
    const id = session.id;
    void guard(async () => {
      saved = await api.writerFinish(id, saveAs.trim());
      session = await api.writerSession(id);
      await inspector.refreshDevices();
    });
  }

  function detectedText(value: unknown): string {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return Object.entries(value as Record<string, unknown>)
        .map(([key, item]) => `${key} ${typeof item === "object" ? JSON.stringify(item) : String(item)}`)
        .join(", ");
    }
    return Array.isArray(value) ? value.map((item) => JSON.stringify(item)).join(", ") : String(value);
  }
</script>

<div class="view">
  <header class="section">
    <h1>Driver writer</h1>
    <p class="muted">
      Turns an unknown device into a Device File. A draft never confirms a limit. Only your answers in the limits
      interview do.
    </p>
  </header>

  {#if !sessionId}
    <section class="section" aria-labelledby="unknown-title">
      <div class="section-head">
        <h2 id="unknown-title">Unknown devices</h2>
        <button class="button small" type="button" onclick={discover} disabled={busy}>Look for devices</button>
      </div>
      <p class="muted small">Looking for devices runs each installed driver's discovery. Drivers send only read-only identify commands.</p>
      {#if discoverNote}<p role="status">{discoverNote}</p>{/if}
      {#if unknownLoaded && !unknown.length}
        <p class="empty">No unknown devices from the last discovery. Run <code>openhal discover</code> or look for devices here.</p>
      {:else}
        <ul class="unknown">
          {#each unknown as device (device.id)}
            <li>
              <div class="facts">
                <span class="name">{device.label ?? device.address}</span>
                <span class="mono muted">{device.driver} at {device.address}</span>
                <span class="mono small">
                  {Object.entries(device.identifiers).map(([key, value]) => `${key} ${value}`).join(", ")}
                </span>
              </div>
              <button class="button primary" type="button" disabled={busy} onclick={() => start(device)}>
                Start the driver writer
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  {:else if session}
    <ol class="steps" aria-label="Progress">
      {#each STEPS as step, index (step.status)}
        <li class:done={index < stepIndex} class:current={index === stepIndex} aria-current={index === stepIndex ? "step" : undefined}>
          <span class="mono n">{index + 1}</span> {step.label}
        </li>
      {/each}
    </ol>

    <section class="section" aria-labelledby="detected-title">
      <div class="section-head">
        <h2 id="detected-title">Session <span class="mono">{session.id}</span></h2>
        <a href={href("writer")}>All unknown devices</a>
      </div>
      <dl class="facts-grid">
        {#each Object.entries(session.detected) as [key, value] (key)}
          <div><dt class="label">{key.replace(/_/g, " ")}</dt><dd class="mono">{detectedText(value)}</dd></div>
        {/each}
      </dl>
      {#each session.problems as problem, index (index)}<p class="problem">{problem}</p>{/each}
      {#if session.sources.length}
        <details>
          <summary>What the device and its sources said, shown as data</summary>
          {#each session.sources as source, index (index)}
            {@const block = dataBlock(source)}
            {#if block}
              <p class="label source-label">{block.source ?? "source"}</p>
              <pre class="data-block">{block.text}</pre>
            {/if}
          {/each}
        </details>
      {/if}
    </section>

    {#if session.status === "drafting"}
      <section class="section" aria-labelledby="propose-title">
        <h2 id="propose-title">Propose a draft</h2>
        <p class="muted">Paste a Device File draft, for example one your AI wrote from the manual. Every limit in it stays suggested.</p>
        <form onsubmit={propose} class="stack">
          <label class="field"><span>Draft YAML</span><textarea bind:value={proposal} rows="12" spellcheck="false"></textarea></label>
          <div><button class="button primary" type="submit" disabled={busy || !proposal.trim()}>Propose the draft</button></div>
        </form>
      </section>
    {/if}

    {#if session.status === "interview" && questions.length}
      <section class="section" aria-labelledby="interview-title">
        <h2 id="interview-title">Limits interview</h2>
        <p class="muted">Answer each question from the device's datasheet or your own setup. The suggestions come from the draft.</p>
        <form onsubmit={submitAnswers} class="stack">
          {#each questions as question (question.id)}
            <div class="question">
              <label class="q-label" for="q-{question.id}">
                <span class="mono q-id">{question.id}</span>
                <span>{question.prompt}</span>
              </label>
              {#if question.reason}<p class="muted small">{question.reason}</p>{/if}
              <div class="answer">
                <input id="q-{question.id}" type="text" bind:value={answers[question.id]} autocomplete="off" spellcheck="false" />
                <span class="muted small">Suggested <span class="mono">{suggestedText(question)}</span></span>
                <button
                  class="button small"
                  type="button"
                  onclick={() => (answers[question.id] = suggestedText(question))}
                  aria-label="Use the suggested value for {question.id}"
                >
                  Use suggested
                </button>
              </div>
            </div>
          {/each}
          <div><button class="button primary" type="submit" disabled={busy || !allAnswered}>Confirm these limits</button></div>
        </form>
      </section>
    {/if}

    {#if session.draft_yaml}
      <section class="section" aria-labelledby="file-title">
        <div class="section-head">
          <h2 id="file-title">File preview</h2>
          {#if stats}<span class="muted mono small">{stats.added} added, {stats.removed} removed since the draft</span>{/if}
        </div>
        {#if diff}
          <ol class="diff" aria-label="Changes from the suggested draft to the confirmed file">
            {#each diff as line, index (index)}
              <li class="line {line.kind}">
                <span class="sign" aria-hidden="true">{line.kind === "added" ? "+" : line.kind === "removed" ? "-" : " "}</span>
                <span class="visually-hidden">{line.kind === "same" ? "" : line.kind}</span>
                <code>{line.text || " "}</code>
              </li>
            {/each}
          </ol>
        {:else}
          <pre class="file"><code>{session.draft_yaml}</code></pre>
        {/if}
      </section>
    {/if}

    {#if plan}
      <section class="section" aria-labelledby="plan-title">
        <h2 id="plan-title">Staged test plan</h2>
        <p class="muted small">Generated and dry-run through the Safety Kernel. Nothing here runs.</p>
        {#each plan.problems as problem, index (index)}<p class="problem">{problem}</p>{/each}
        <ol class="plan">
          {#each plan.steps as step, index (index)}
            <li>
              {#if typeof step.command === "string"}
                <code>{step.command}</code>
              {:else}
                <Json value={step.command} />
              {/if}
              <span class="muted">{step.expected}</span>
              {#if step.needs_approval}<StatusMark tone="confirm" label="confirmation required" />{/if}
            </li>
          {/each}
        </ol>
      </section>
    {/if}

    {#if session.status === "ready" || session.status === "interview"}
      <section class="section" aria-labelledby="save-title">
        <h2 id="save-title">Save</h2>
        <form onsubmit={save} class="save">
          <label class="field">
            <span>File name</span>
            <span class="name-input"><input type="text" bind:value={saveAs} spellcheck="false" autocomplete="off" /><span class="mono muted">.hal.yaml</span></span>
          </label>
          <button class="button primary" type="submit" disabled={busy || !saveAs.trim()}>Save the Device File</button>
        </form>
        {#if session.status === "interview"}
          <p class="muted small">Saving before the interview is done gives a read-only file.</p>
        {/if}
      </section>
    {/if}

    {#if saved}
      <section class="section human-surface saved" aria-live="polite">
        <StatusMark tone="ok" label="saved" />
        <p>Saved <code>{saved.path}</code> as device <a class="mono" href={href("devices", saved.device_id)}>{saved.device_id}</a>, {saved.writable ? "writable" : "read-only"}.</p>
      </section>
    {/if}
  {:else if error}
    <p class="problem" role="alert">{error}</p>
  {/if}

  {#if error && session}<p class="problem" role="alert">{error}</p>{/if}
</div>

<style>
  .view {
    display: grid;
    max-width: 980px;
  }

  .small {
    font-size: var(--t-label);
  }

  .unknown {
    display: grid;
    gap: var(--s-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .unknown li {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--s-3);
    padding: var(--s-3) var(--s-4);
    border: var(--rule);
    border-radius: var(--radius);
  }

  .facts {
    display: grid;
    gap: 2px;
  }

  .name {
    font-weight: 700;
  }

  .steps {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-2) var(--s-5);
    margin: 0 0 var(--s-4);
    padding: 0;
    list-style: none;
    color: var(--text-2);
  }

  .steps li {
    display: inline-flex;
    align-items: baseline;
    gap: var(--s-2);
  }

  .steps .n {
    display: inline-grid;
    place-items: center;
    width: 24px;
    height: 24px;
    border: 1px solid var(--border);
    border-radius: 50%;
    font-size: var(--t-label);
  }

  .steps .done {
    color: var(--text);
  }

  .steps .done .n {
    border-color: var(--text);
  }

  .steps .current {
    color: var(--accent);
    font-weight: 700;
  }

  .steps .current .n {
    border: 2px solid var(--accent);
  }

  .facts-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: var(--s-3);
    margin: 0;
  }

  .facts-grid div {
    display: grid;
    gap: 2px;
  }

  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }

  details summary {
    cursor: pointer;
    color: var(--accent);
  }

  details pre {
    margin-top: var(--s-2);
  }

  .stack {
    display: grid;
    gap: var(--s-4);
  }

  .question {
    display: grid;
    gap: var(--s-1);
    padding-bottom: var(--s-3);
    border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  }

  .q-label {
    display: grid;
    gap: 2px;
  }

  .q-id {
    color: var(--accent);
    font-weight: 700;
  }

  .answer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--s-2) var(--s-3);
  }

  .answer input {
    width: 18ch;
    font-family: var(--font-mono);
  }

  .diff,
  .file {
    margin: 0;
    padding: var(--s-3) 0;
    border: var(--rule);
    border-radius: var(--radius);
    background: var(--surface);
    list-style: none;
    font-family: var(--font-mono);
    font-size: var(--t-mono);
    overflow-x: auto;
  }

  .file {
    padding: var(--s-3) var(--s-4);
  }

  .line {
    display: grid;
    grid-template-columns: 3ch minmax(0, 1fr);
    padding: 0 var(--s-3);
    white-space: pre-wrap;
  }

  .line.added {
    background: var(--bg);
    font-weight: 700;
  }

  .line.added .sign {
    color: var(--ok);
    font-weight: 700;
  }

  .line.removed {
    color: var(--text-2);
  }

  .line.removed code {
    text-decoration: line-through;
  }

  .plan {
    display: grid;
    gap: var(--s-2);
    margin: 0;
    padding-left: var(--s-5);
  }

  .plan li {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-3);
  }

  .save {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: var(--s-3);
  }

  .name-input {
    display: inline-flex;
    align-items: center;
    gap: var(--s-1);
  }

  .saved {
    padding: var(--s-3) var(--s-4);
    border-top: 0;
  }
</style>
