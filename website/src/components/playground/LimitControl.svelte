<script lang="ts">
  import { formatG } from "../../lib/kernel/pyformat";

  interface Props {
    id: string;
    name: string;
    unit: string;
    min: number;
    max: number;
    step: number | null;
    value: number | null;
    rate: { low: number; high: number } | null;
    attempt: { value: number; code: string; key: number } | null;
    disabled?: boolean;
    onpick: (value: number) => void;
  }

  let { id, name, unit, min, max, step, value, rate, attempt, disabled = false, onpick }: Props = $props();

  const shown = $derived(unit === "percent" || unit === "%" ? "%" : unit);
  const span = $derived(max - min || 1);
  const lo = $derived(min - span * 0.18);
  const hi = $derived(max + span * 0.18);
  const pct = (v: number) => ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * 100;
  let draft = $state<number | null>(null);
  const current = $derived(draft ?? value ?? min);
  const offScale = $derived(attempt !== null && (attempt.value > hi || attempt.value < lo));
  let pulseKey = $state(0);
  $effect(() => {
    if (attempt && (attempt.code === "above_max" || attempt.code === "below_min")) pulseKey = attempt.key;
  });
</script>

<div class="limit-track" style={`--lo:${lo}`} aria-hidden="true">
  <div class="rail"></div>
  <div class="fill" style={`--from:${pct(min)};--to:${pct(value ?? min)}`}></div>
  {#if rate}
    <div class="rate" style={`--from:${pct(rate.low)};--to:${pct(rate.high)}`}></div>
  {/if}
  {#key attempt?.code === "below_min" ? pulseKey : -1}
    <div class="limit min" class:pulse={attempt?.code === "below_min"} style={`--at:${pct(min)}`}>
      <span class="limit-flag">Min {formatG(min)} {shown}</span>
    </div>
  {/key}
  {#key attempt?.code === "above_max" ? pulseKey : -1}
    <div class="limit max" class:pulse={attempt?.code === "above_max"} style={`--at:${pct(max)}`}>
      <span class="limit-flag">Max {formatG(max)} {shown}</span>
    </div>
  {/key}
  <div class="thumb" style={`--at:${pct(value ?? min)}`}></div>
  {#if attempt}
    <div class="attempt" class:off-scale={offScale && attempt.value > hi} style={`--at:${pct(attempt.value)}`}></div>
  {/if}
</div>
<div class="slider" style={`--left:${pct(min)}%;--right:${100 - pct(max)}%`}>
  <label class="visually-hidden" for={id}>{name} in {shown}, from {formatG(min)} to {formatG(max)}</label>
  <input
    {id}
    type="range"
    {min}
    {max}
    step={step ?? "any"}
    value={current}
    {disabled}
    oninput={(event) => (draft = Number((event.currentTarget as HTMLInputElement).value))}
    onchange={(event) => {
      const picked = Number((event.currentTarget as HTMLInputElement).value);
      draft = null;
      onpick(picked);
    }}
  />
</div>

<style>
  .slider {
    position: relative;
    margin: -56px var(--s-2) 0;
    padding-left: var(--left);
    padding-right: var(--right);
    height: 40px;
  }

  input[type="range"] {
    width: 100%;
    height: 40px;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }

  .slider:has(input:focus-visible) {
    outline: 2px solid var(--signal);
    outline-offset: 2px;
  }

  input[type="range"]:disabled {
    cursor: default;
  }
</style>
