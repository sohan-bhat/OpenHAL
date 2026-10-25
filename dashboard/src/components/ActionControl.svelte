<script lang="ts">
  import { api } from "../lib/api";
  import { describeDecision, type DecisionSummary } from "../lib/devices";
  import { href } from "../lib/router.svelte";
  import { confirmTier } from "../lib/status";
  import type { ActionSpec } from "../lib/types";
  import { formatQuantity, quantityString, unitSymbol } from "../lib/units";
  import StatusMark from "./StatusMark.svelte";

  let {
    device,
    name,
    spec,
    disabled = false,
    onran,
  }: { device: string; name: string; spec: ActionSpec; disabled?: boolean; onran?: () => void } = $props();

  const tier = $derived(confirmTier(spec.confirm));
  const ident = $derived(`${device}-action-${name}`.replace(/[^a-z0-9-]/gi, "-"));
  const args = $derived(Object.entries(spec.args));

  let values = $state<Record<string, string>>({});
  let busy = $state(false);
  let outcome = $state<DecisionSummary | null>(null);
  let requestId = $state<string | null>(null);

  function argValue(arg: string): unknown {
    const argSpec = spec.args[arg]!;
    const raw = values[arg] ?? "";
    if (argSpec.type === "bool") return raw === "true";
    if (argSpec.unit || argSpec.type === "number" || argSpec.min !== undefined) return quantityString(Number(raw), argSpec.unit);
    return raw;
  }

  const ready = $derived(args.every(([arg]) => (values[arg] ?? "").trim() !== ""));

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
      outcome = { tone: "failed", word: "failed", head: "", reason: error instanceof Error ? error.message : "The action failed." };
    }
    busy = false;
    onran?.();
  }
</script>

<form class="action" onsubmit={run} aria-labelledby="{ident}-name">
  <div class="top">
    <h4 id="{ident}-name" class="mono">{name}</h4>
    <StatusMark tone={tier.tone} label={tier.label} />
  </div>
  {#if spec.description}<p>{spec.description}</p>{/if}
  {#if args.length}
    <div class="args">
      {#each args as [arg, argSpec] (arg)}
        <label class="field">
          <span class="mono">{arg}{argSpec.unit ? ` in ${unitSymbol(argSpec.unit)}` : ""}</span>
          {#if argSpec.values?.length}
            <select bind:value={values[arg]} {disabled}>
              <option value="">Choose</option>
              {#each argSpec.values ?? [] as option (option)}<option value={option}>{option}</option>{/each}
            </select>
          {:else if argSpec.type === "bool"}
            <select bind:value={values[arg]} {disabled}>
              <option value="">Choose</option>
              <option value="false">false</option>
              <option value="true">true</option>
            </select>
          {:else}
            <input
              type={argSpec.unit || argSpec.type === "number" || argSpec.min !== undefined ? "number" : "text"}
              inputmode={argSpec.unit || argSpec.type === "number" ? "decimal" : undefined}
              autocomplete="off"
              min={argSpec.min}
              max={argSpec.max}
              bind:value={values[arg]}
              {disabled}
            />
          {/if}
          {#if argSpec.min !== undefined && argSpec.max !== undefined}
            <small class="muted mono">{formatQuantity(argSpec.min, argSpec.unit)} to {formatQuantity(argSpec.max, argSpec.unit)}</small>
          {/if}
        </label>
      {/each}
    </div>
  {/if}
  {#if spec.require.length || spec.effects.length}
    <dl class="meta">
      {#if spec.require.length}<div><dt class="label">requires</dt><dd class="mono">{spec.require.join(", ")}</dd></div>{/if}
      {#if spec.effects.length}<div><dt class="label">changes</dt><dd class="mono">{spec.effects.join(", ")}</dd></div>{/if}
    </dl>
  {/if}
  <div>
    <button class="button primary" type="submit" disabled={disabled || busy || !ready}>Run {name}</button>
  </div>
  <div aria-live="polite">
    {#if outcome}
      <div class="result appear {outcome.tone}">
        <StatusMark
          tone={outcome.tone === "granted" ? "ok" : outcome.tone === "pending" ? "confirm" : "blocked"}
          label={outcome.word}
        />
        {#if outcome.head && outcome.tone !== "granted"}<span class="mono head {outcome.tone}">{outcome.head}</span>{/if}
        <p class="mono reason">{outcome.reason}</p>
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

  .top h4 {
    font-size: 16px;
  }

  .args {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-3);
  }

  .args input {
    width: 12ch;
    font-family: var(--font-mono);
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
