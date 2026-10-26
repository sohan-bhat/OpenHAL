<script lang="ts">
  import { untrack } from "svelte";
  import { api } from "../lib/api";
  import { describeDecision, type DecisionSummary } from "../lib/devices";
  import { href } from "../lib/router.svelte";
  import { confirmTier } from "../lib/status";
  import type { ActionSpec } from "../lib/types";
  import { formatDuration, formatQuantity, identifiersOf, quantity, unitSymbol } from "../lib/units";
  import LimitScale from "./LimitScale.svelte";
  import Prose from "./Prose.svelte";
  import Reason from "./Reason.svelte";
  import StatusMark from "./StatusMark.svelte";

  let {
    device,
    name,
    spec,
    disabled = false,
    readOnly = false,
    safeState = false,
    disabledReason = "",
    onran,
  }: {
    device: string;
    name: string;
    spec: ActionSpec;
    disabled?: boolean;
    readOnly?: boolean;
    safeState?: boolean;
    disabledReason?: string;
    onran?: () => void;
  } = $props();

  const tier = $derived(confirmTier(spec.confirm));
  const confirms = $derived(tier.tone === "confirm");
  const ident = $derived(`${device}-action-${name}`.replace(/[^a-z0-9-]/gi, "-"));
  const args = $derived(Object.entries(spec.args));

  let values = $state<Record<string, string>>(
    untrack(() =>
      Object.fromEntries(
        Object.entries(spec.args)
          .filter(([, argSpec]) => argSpec.min !== undefined)
          .map(([arg, argSpec]) => [arg, String(argSpec.min)]),
      ),
    ),
  );
  const requirements = $derived(
    spec.requirements ?? spec.require.map((condition) => ({ condition, message: null as string | null })),
  );
  const runs = $derived(
    spec.max_runs
      ? `at most ${spec.max_runs.count} ${spec.max_runs.count === 1 ? "run" : "runs"} per ${formatDuration(spec.max_runs.per_s)}`
      : null,
  );
  let busy = $state(false);
  let outcome = $state<DecisionSummary | null>(null);
  let requestId = $state<string | null>(null);

  function argValue(arg: string): unknown {
    const argSpec = spec.args[arg]!;
    const raw = values[arg] ?? "";
    if (argSpec.type === "bool") return raw === "true";
    if (numeric(arg)) return quantity(Number(raw), argSpec.unit);
    return raw;
  }

  function numeric(arg: string): boolean {
    const argSpec = spec.args[arg]!;
    return !!argSpec.unit || argSpec.type === "number" || argSpec.min !== undefined;
  }

  function inRange(arg: string): boolean {
    const argSpec = spec.args[arg]!;
    const raw = (values[arg] ?? "").trim();
    if (raw === "") return false;
    if (!numeric(arg)) return true;
    const number = Number(raw);
    if (!Number.isFinite(number)) return false;
    return (argSpec.min === undefined || number >= argSpec.min) && (argSpec.max === undefined || number <= argSpec.max);
  }

  const ready = $derived(args.every(([arg]) => inRange(arg)));

  async function run(event: SubmitEvent) {
    event.preventDefault();
    if (busy || disabled || !ready) return;
    busy = true;
    const payload = Object.fromEntries(args.map(([arg]) => [arg, argValue(arg)]));
    try {
      const decision = await api.action(device, name, payload);
      outcome = describeDecision(decision);
      requestId = decision.request_id;
    } catch (error) {
      outcome = { tone: "failed", word: "failed", head: "", reason: error instanceof Error ? error.message : "The command failed." };
    }
    busy = false;
    onran?.();
  }
</script>

<form class="action" onsubmit={run} aria-labelledby="{ident}-name">
  <div class="top">
    <h3 id="{ident}-name" class="mono">{name}</h3>
    <StatusMark tone={tier.tone} label={tier.label} />
  </div>
  {#if spec.description}<p>{spec.description}</p>{/if}
  {#if args.length}
    <div class="args">
      {#each args as [arg, argSpec] (arg)}
        {@const fieldId = `${ident}-${arg}`}
        <div class="field arg">
          <label for={fieldId} class="mono arg-name">{arg}{argSpec.unit ? ` in ${unitSymbol(argSpec.unit)}` : ""}</label>
          {#if argSpec.values?.length}
            <select id={fieldId} bind:value={values[arg]} {disabled}>
              <option value="">Choose</option>
              {#each argSpec.values ?? [] as option (option)}<option value={option}>{option}</option>{/each}
            </select>
          {:else if argSpec.type === "bool"}
            <select id={fieldId} bind:value={values[arg]} {disabled}>
              <option value="">Choose</option>
              <option value="false">false</option>
              <option value="true">true</option>
            </select>
          {:else}
            {#if numeric(arg) && argSpec.min !== undefined && argSpec.max !== undefined}
              <LimitScale
                id="{fieldId}-range"
                label="{arg} for {name}, slider"
                min={argSpec.min}
                max={argSpec.max}
                unit={argSpec.unit ?? null}
                value={values[arg] && Number.isFinite(Number(values[arg])) ? Number(values[arg]) : null}
                {disabled}
                interactive={!readOnly}
                oninput={(value) => (values[arg] = value)}
              />
            {/if}
            {#if readOnly}
              {#if argSpec.min !== undefined && argSpec.max !== undefined}
                <small class="muted mono nobreak">{formatQuantity(argSpec.min, argSpec.unit)} to {formatQuantity(argSpec.max, argSpec.unit)}</small>
              {/if}
            {:else}
            <span class="entry">
              <input
                id={fieldId}
                type={numeric(arg) ? "number" : "text"}
                inputmode={numeric(arg) ? "decimal" : undefined}
                autocomplete="off"
                min={argSpec.min}
                max={argSpec.max}
                bind:value={values[arg]}
                {disabled}
              />
              {#if argSpec.min !== undefined && argSpec.max !== undefined}
                <small class="muted mono nobreak">{formatQuantity(argSpec.min, argSpec.unit)} to {formatQuantity(argSpec.max, argSpec.unit)}</small>
              {/if}
            </span>
            {/if}
          {/if}
        </div>
      {/each}
    </div>
  {/if}
  {#if requirements.length || runs || spec.effects.length}
    <dl class="meta">
      {#if runs}<div><dt class="label">run limit</dt><dd>{runs}</dd></div>{/if}
      {#if requirements.length}
        <div class="requirements">
          <dt class="label">requires</dt>
          {#each requirements as requirement (requirement.condition)}
            <dd>
              <code class="condition">{requirement.condition}</code>
              {#if requirement.message}<span class="why"><Prose text={requirement.message} /></span>{/if}
            </dd>
          {/each}
        </div>
      {/if}
      {#if spec.effects.length}<div><dt class="label">changes</dt><dd class="mono">{spec.effects.join(", ")}</dd></div>{/if}
    </dl>
  {/if}
  {#if !readOnly}
    <div class="run">
      <button class="button" class:primary={!safeState} type="submit" disabled={disabled || busy || !ready}>
        <span>{confirms ? "Confirm and run" : "Run"} <span class="mono">{name}</span></span>
      </button>
      {#if confirms}
        <p class="muted note"><span class="mono">{name}</span> needs a person's confirmation each time. Your click is that confirmation.</p>
      {:else if safeState}
        <p class="muted note"><span class="mono">{name}</span> is this device's safe state. STOP in the header puts every device in its safe state.</p>
      {/if}
    </div>
  {/if}
  {#if disabled && disabledReason && !readOnly}
    <p class="muted note">{disabledReason}</p>
  {/if}
  <div aria-live="polite">
    {#if outcome}
      <div class="result appear {outcome.tone}">
        <StatusMark
          tone={outcome.tone === "granted" ? "ok" : outcome.tone === "pending" ? "confirm" : "blocked"}
          label={outcome.word}
        />
        {#if outcome.head && outcome.tone !== "granted"}<span class="mono head {outcome.tone}">{outcome.head}</span>{/if}
        <p class="reason"><Reason text={outcome.reason} code={identifiersOf(device, `action:${name}`)} /></p>
        {#if requestId}
          <p class="reason">Request <a class="mono" href={href("confirmations")}>{requestId}</a> waits in the confirmation queue.</p>
        {/if}
      </div>
    {/if}
  </div>
</form>

<style>
  .action {
    display: grid;
    gap: var(--s-3);
    padding: var(--s-4);
    border: var(--rule);
    border-radius: var(--radius);
  }

  .top {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--s-2);
  }

  .top h3 {
    font-size: 16px;
  }

  .args {
    display: grid;
    gap: var(--s-3);
  }

  .arg-name {
    font-size: var(--t-ui);
    font-weight: 700;
    color: var(--text);
  }

  .entry {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--s-2) var(--s-3);
  }

  .entry input {
    width: 10ch;
    font-family: var(--font-mono);
    text-align: right;
  }

  small {
    font-size: var(--t-label);
  }

  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-2) var(--s-5);
    margin: 0;
  }

  .meta div {
    display: grid;
    gap: 2px;
  }

  .meta dd {
    margin: 0;
  }

  .requirements dd {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-3);
  }

  .condition {
    white-space: nowrap;
  }

  .why {
    color: var(--text-2);
  }

  .run {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--s-2) var(--s-4);
  }

  .note {
    font-size: var(--t-label);
  }

  .result {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-3);
    padding: var(--s-2) var(--s-3);
    background: var(--surface);
    border-left: 3px solid var(--ok);
  }

  .result.blocked,
  .result.failed {
    border-left-color: var(--blocked);
  }

  .result.pending {
    border-left-color: var(--confirm);
  }

  .head.blocked,
  .head.failed {
    color: var(--blocked);
    font-weight: 700;
  }

  .head.pending {
    color: var(--confirm);
    font-weight: 700;
  }

  .reason {
    flex-basis: 100%;
  }
</style>
