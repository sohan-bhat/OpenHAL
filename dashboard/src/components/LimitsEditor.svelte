<script lang="ts">
  import { Button } from "$lib/components/ui/button/index.js";
  import { Input } from "$lib/components/ui/input/index.js";
  import { Label } from "$lib/components/ui/label/index.js";
  import { api } from "../lib/api";
  import type { LimitChange, WriteSpec } from "../lib/types";
  import { unitSymbol } from "../lib/units";

  const PHRASE = "confirm";

  let {
    device,
    channel,
    spec,
    onchanged,
  }: { device: string; channel: string; spec: WriteSpec; onchanged?: () => void } = $props();

  let low = $state("");
  let high = $state("");
  let rate = $state("");
  let planned = $state<LimitChange | null>(null);
  let phrase = $state("");
  let busy = $state(false);
  let message = $state<string | null>(null);
  let error = $state<string | null>(null);

  const current = $derived(`${spec.min ?? ""}|${spec.max ?? ""}|${spec.max_change_per_s ?? ""}`);

  $effect(() => {
    const [min, max, change] = current.split("|");
    low = min ?? "";
    high = max ?? "";
    rate = change ?? "";
    planned = null;
    phrase = "";
  });

  const unit = $derived(spec.unit ?? "dimensionless");
  const symbol = $derived(unitSymbol(spec.unit) || unit);
  const widens = $derived((planned?.loosens.length ?? 0) > 0);
  const phraseTyped = $derived(phrase.trim().toLowerCase() === PHRASE);

  function body(): Record<string, unknown> {
    const given: Record<string, unknown> = { device, channel };
    if (low.trim() !== String(spec.min ?? "")) given.min = { value: Number(low), unit };
    if (high.trim() !== String(spec.max ?? "")) given.max = { value: Number(high), unit };
    const current = spec.max_change_per_s === null ? "" : String(spec.max_change_per_s);
    if (rate.trim() !== current) given.rate = rate.trim() === "" ? "none" : { value: Number(rate), unit: `${unit}/s` };
    return given;
  }

  async function review(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = null;
    message = null;
    planned = null;
    try {
      const result = await api.limits({ ...body(), dry_run: true });
      if (result.status === "blocked") error = result.message;
      else planned = result;
    } catch (failure) {
      error = failure instanceof Error ? failure.message : "The hub sent no response.";
    }
    busy = false;
  }

  async function save() {
    busy = true;
    error = null;
    try {
      const result = await api.limits({ ...body(), ...(widens ? { phrase } : {}) });
      if (result.status === "blocked") error = result.message;
      else {
        message = result.message;
        planned = null;
        phrase = "";
        onchanged?.();
      }
    } catch (failure) {
      error = failure instanceof Error ? failure.message : "The hub sent no response.";
    }
    busy = false;
  }
</script>

<form class="limits" onsubmit={review} aria-label="Limits of {channel}">
  <h3 class="mono">{channel}</h3>
  <div class="fields">
    <div class="field">
      <Label for="min-{channel}">Min, in {symbol}</Label>
      <Input id="min-{channel}" type="text" inputmode="decimal" bind:value={low} autocomplete="off" class="w-[12ch] font-mono" />
    </div>
    <div class="field">
      <Label for="max-{channel}">Max, in {symbol}</Label>
      <Input id="max-{channel}" type="text" inputmode="decimal" bind:value={high} autocomplete="off" class="w-[12ch] font-mono" />
    </div>
    <div class="field">
      <Label for="rate-{channel}">Max change, in {symbol} per second</Label>
      <Input
        id="rate-{channel}"
        type="text"
        inputmode="decimal"
        bind:value={rate}
        autocomplete="off"
        aria-describedby="rate-hint-{channel}"
        class="w-[12ch] font-mono"
      />
      <p class="muted small" id="rate-hint-{channel}">Empty means no rate limit.</p>
    </div>
    <Button type="submit" disabled={busy}>Review the change</Button>
  </div>
  {#if planned}
    <ul class="changes" aria-label="Changes to {channel}">
      {#each Object.entries(planned.changes) as [name, step] (name)}
        <li><span class="mono">{name}</span> {step.from} to {step.to}</li>
      {/each}
    </ul>
    {#if widens}
      <div class="field">
        <Label for="phrase-{channel}">Phrase</Label>
        <Input
          id="phrase-{channel}"
          type="text"
          bind:value={phrase}
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
          aria-describedby="phrase-hint-{channel}"
          class="w-[12ch] font-mono"
        />
        <p class="muted small" id="phrase-hint-{channel}">The change widens what an agent may do. Type <code>{PHRASE}</code> to widen these limits.</p>
      </div>
    {/if}
    <div>
      <Button variant="primary" onclick={save} disabled={busy || (widens && !phraseTyped)}>Save the limits</Button>
    </div>
  {/if}
  {#if message}<p role="status">{message}</p>{/if}
  {#if error}<p class="problem" role="alert">{error}</p>{/if}
</form>

<style>
  .limits {
    display: grid;
    gap: var(--s-3);
    padding: var(--s-3) var(--s-4);
    border: var(--rule);
    border-radius: var(--radius);
  }

  h3 {
    font-size: var(--t-mono);
  }

  .fields {
    display: flex;
    flex-wrap: wrap;
    align-items: start;
    gap: var(--s-3) var(--s-4);
  }

  .fields :global(button) {
    margin-top: 22px;
  }

  .changes {
    display: grid;
    gap: var(--s-1);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .small {
    font-size: var(--t-label);
  }
</style>
