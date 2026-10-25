<script lang="ts">
  import Prose from "./Prose.svelte";
  import { api } from "../lib/api";
  import { describeDecision, type DecisionSummary } from "../lib/devices";
  import { confirmTier } from "../lib/status";
  import type { WriteSpec } from "../lib/types";
  import { formatNumber, formatQuantity, quantityString, unitSymbol, valueWidth } from "../lib/units";
  import LimitScale from "./LimitScale.svelte";
  import StatusMark from "./StatusMark.svelte";

  let {
    device,
    channel,
    spec,
    disabled = false,
    disabledReason = "",
    onwritten,
  }: {
    device: string;
    channel: string;
    spec: WriteSpec;
    disabled?: boolean;
    disabledReason?: string;
    onwritten?: () => void;
  } = $props();

  const isNumber = $derived(spec.type === "number");
  const bounded = $derived(isNumber && spec.min !== null && spec.max !== null && spec.max > spec.min);
  const symbol = $derived(unitSymbol(spec.unit));
  const width = $derived(valueWidth(spec.min, spec.max, spec.step));
  const tier = $derived(confirmTier(spec.confirm));
  const ident = $derived(`${device}-${channel}`.replace(/[^a-z0-9-]/gi, "-"));

  const lo = $derived(spec.min ?? 0);
  const hi = $derived(spec.max ?? 100);

  let draft = $state<string>("");
  let dirty = $state(false);
  let busy = $state(false);
  let outcome = $state<DecisionSummary | null>(null);
  let requestedText = $state("");

  $effect(() => {
    if (dirty) return;
    const value = spec.value;
    if (value === null || value === undefined) draft = "";
    else if (typeof value === "number") draft = formatNumber(value, spec.step);
    else draft = String(value);
  });

  const current = $derived(spec.known ? formatQuantity(spec.value, spec.unit, spec.step) : "unknown");
  const numericDraft = $derived(Number(draft));
  const draftValid = $derived(
    !isNumber || (draft.trim() !== "" && Number.isFinite(numericDraft) && (!bounded || (numericDraft >= lo && numericDraft <= hi))),
  );

  function payload(): { value: unknown; unit?: string } {
    if (isNumber) return spec.unit ? { value: numericDraft, unit: spec.unit } : { value: numericDraft };
    if (spec.type === "bool") return { value: draft === "true" };
    return { value: draft };
  }

  async function send(event?: SubmitEvent) {
    event?.preventDefault();
    if (disabled || busy || !draftValid) return;
    busy = true;
    const body = payload();
    requestedText = typeof body.value === "number" ? quantityString(body.value, spec.unit) : String(body.value);
    try {
      outcome = describeDecision(await api.write(device, channel, body.value, body.unit));
    } catch (error) {
      outcome = { tone: "failed", word: "failed", head: "", reason: error instanceof Error ? error.message : "The change failed." };
    }
    busy = false;
    dirty = false;
    onwritten?.();
  }

  function setDraft(value: string) {
    draft = value;
    dirty = true;
  }

  const outcomeTone = $derived(
    outcome?.tone === "granted" ? "ok" : outcome?.tone === "pending" ? "confirm" : "blocked",
  );
</script>

<form class="write" onsubmit={send} aria-labelledby="{ident}-name">
  <div class="top">
    <div class="title">
      <h4 id="{ident}-name" class="mono">{channel}</h4>
      <span class="type muted">{spec.type}{symbol ? ` in ${symbol}` : ""}</span>
    </div>
    <div class="now" aria-live="off">
      <span class="label">now</span>
      <output class="value mono" style="min-width: {width + 3}ch" for="{ident}-input" class:unknown={!spec.known}>
        {current}
      </output>
    </div>
  </div>

  {#if bounded}
    <LimitScale
      id="{ident}-range"
      label="{channel} new value"
      min={lo}
      max={hi}
      step={spec.step}
      unit={spec.unit}
      value={Number.isFinite(numericDraft) ? numericDraft : null}
      current={spec.known && typeof spec.value === "number" ? spec.value : null}
      {disabled}
      oninput={setDraft}
    />
  {/if}

  <div class="entry">
    {#if isNumber}
      <label class="number">
        <span class="visually-hidden">{channel} value in {symbol || "its unit"}</span>
        <input
          id="{ident}-input"
          type="number"
          inputmode="decimal"
          min={spec.min ?? undefined}
          max={spec.max ?? undefined}
          step={spec.step ?? "any"}
          value={draft}
          {disabled}
          oninput={(event) => setDraft((event.currentTarget as HTMLInputElement).value)}
          style="width: {width + 4}ch"
        />
        {#if symbol}<span class="unit mono">{symbol}</span>{/if}
      </label>
    {:else if spec.type === "bool"}
      <div class="choices" role="radiogroup" aria-label="{channel} new value">
        {#each ["false", "true"] as option (option)}
          <label class="choice">
            <input type="radio" name="{ident}-bool" value={option} checked={draft === option} {disabled} onchange={() => setDraft(option)} />
            <span class="mono">{option}</span>
          </label>
        {/each}
      </div>
    {:else if spec.type === "enum" && spec.values}
      <div class="choices" role="radiogroup" aria-label="{channel} new value">
        {#each spec.values as option (option)}
          <label class="choice">
            <input type="radio" name="{ident}-enum" value={option} checked={draft === option} {disabled} onchange={() => setDraft(option)} />
            <span class="mono">{option}</span>
          </label>
        {/each}
      </div>
    {:else}
      <label class="number">
        <span class="visually-hidden">{channel} new value</span>
        <input id="{ident}-input" type="text" value={draft} {disabled} oninput={(event) => setDraft((event.currentTarget as HTMLInputElement).value)} />
      </label>
    {/if}
    <button class="button primary" type="submit" disabled={disabled || busy || !draftValid}>Set {channel}</button>
  </div>

  <dl class="meta">
    {#if bounded}
      <div><dt class="label">limit</dt><dd class="mono">{formatQuantity(lo, spec.unit, spec.step)} to {formatQuantity(hi, spec.unit, spec.step)}</dd></div>
    {/if}
    {#if spec.step}<div><dt class="label">step</dt><dd class="mono">{formatQuantity(spec.step, spec.unit)}</dd></div>{/if}
    {#if spec.max_change_per_s}
      <div><dt class="label">rate limit</dt><dd class="mono">{formatQuantity(spec.max_change_per_s, spec.unit)}/s</dd></div>
    {/if}
    {#if spec.values}<div><dt class="label">values</dt><dd class="mono">{spec.values.join(", ")}</dd></div>{/if}
    <div><dt class="label">confirmation</dt><dd><StatusMark tone={tier.tone} label={tier.label} compact /></dd></div>
    {#if spec.suggested}<div><dt class="label">limits</dt><dd><StatusMark tone="unverified" label="suggested, not confirmed" /></dd></div>{/if}
  </dl>

  {#if disabled && disabledReason}
    <p class="muted reason-line">{disabledReason}</p>
  {/if}

  <div class="outcome" aria-live="polite">
    {#if outcome}
      <div class="result appear {outcome.tone}">
        <StatusMark tone={outcomeTone} label={outcome.word} />
        <span class="mono asked">{requestedText}</span>
        {#if outcome.head}
          <span
            class="mono head"
            class:error={outcome.tone === "blocked" || outcome.tone === "failed"}
            class:pending={outcome.tone === "pending"}>{outcome.head}</span
          >
        {/if}
        <p class="mono reason"><Prose text={outcome.reason} /></p>
      </div>
    {/if}
  </div>
</form>

<style>
  .write {
    display: grid;
    gap: var(--s-3);
    padding: var(--s-4);
    border: var(--rule);
    border-radius: var(--radius);
    background: var(--bg);
  }

  .top {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--s-2) var(--s-4);
  }

  .title {
    display: flex;
    align-items: baseline;
    gap: var(--s-3);
  }

  .title h4 {
    font-size: 16px;
  }

  .type {
    font-size: var(--t-label);
  }

  .now {
    display: flex;
    align-items: baseline;
    gap: var(--s-2);
  }

  .value {
    display: inline-block;
    text-align: right;
    font-size: 22px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }

  .value.unknown {
    color: var(--text-2);
    font-weight: 400;
    font-size: 16px;
  }

  .entry {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--s-2) var(--s-3);
  }

  .number {
    display: inline-flex;
    align-items: center;
    gap: var(--s-2);
  }

  .number input {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    text-align: right;
  }

  .unit {
    color: var(--text-2);
  }

  .choices {
    display: inline-flex;
    flex-wrap: wrap;
    border: var(--rule);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .choice {
    display: inline-flex;
    align-items: center;
    gap: var(--s-1);
    min-height: 36px;
    padding: 0 var(--s-3);
    border-right: var(--rule);
    cursor: pointer;
  }

  .choice:last-child {
    border-right: 0;
  }

  .choice:has(input:checked) {
    background: var(--surface);
    font-weight: 700;
  }

  .choice:has(input:focus-visible) {
    outline: var(--focus);
    outline-offset: -2px;
  }

  .choice input {
    accent-color: var(--accent);
    margin: 0;
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
    font-size: var(--t-ui);
  }

  .reason-line {
    font-size: var(--t-label);
  }

  .outcome {
    min-height: 0;
  }

  .result {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-3);
    padding: var(--s-2) var(--s-3);
    background: var(--surface);
    border-left: 3px solid var(--ok);
    border-radius: 0 var(--radius) var(--radius) 0;
  }

  .result.blocked,
  .result.failed {
    border-left-color: var(--blocked);
  }

  .result.pending {
    border-left-color: var(--confirm);
  }

  .head.error {
    color: var(--blocked);
    font-weight: 700;
  }

  .head.pending {
    color: var(--confirm);
    font-weight: 700;
  }

  .reason {
    flex-basis: 100%;
    font-size: var(--t-mono);
  }
</style>
