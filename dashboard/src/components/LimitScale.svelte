<script lang="ts">
  import { formatQuantity, quantityString } from "../lib/units";

  let {
    id,
    label,
    min,
    max,
    step = null,
    unit = null,
    value,
    current = null,
    disabled = false,
    oninput,
  }: {
    id: string;
    label: string;
    min: number;
    max: number;
    step?: number | null;
    unit?: string | null;
    value: number | null;
    current?: number | null;
    disabled?: boolean;
    oninput: (value: string) => void;
  } = $props();

  const span = $derived(max - min || 1);
  const scaleMin = $derived(min > 0 ? min - span * 0.12 : min);
  const scaleMax = $derived(max + span * 0.2);
  const pct = (point: number) => ((point - scaleMin) / (scaleMax - scaleMin)) * 100;
  const middle = $derived(span >= 10 ? Math.round(min + span / 2) : min + span / 2);
  const clamp = (point: number) => Math.min(Math.max(point, scaleMin), scaleMax);
</script>

<div class="meter">
  <div class="scale">
    {#if min > scaleMin}<div class="beyond" style="left: 0; width: {pct(min)}%"></div>{/if}
    <div class="beyond" style="left: {pct(max)}%; right: 0"></div>
    {#if current !== null}
      <div class="now-tick" style="left: {pct(clamp(current))}%"></div>
    {/if}
    <input
      {id}
      class="range"
      type="range"
      {min}
      {max}
      step={step ?? "any"}
      value={value ?? min}
      style="left: calc({pct(min)}% - 8px); width: calc({pct(max) - pct(min)}% + 16px)"
      aria-label={label}
      aria-valuetext={value !== null ? quantityString(value, unit) : undefined}
      {disabled}
      oninput={(event) => oninput((event.currentTarget as HTMLInputElement).value)}
    />
    <div class="limit" style="left: {pct(min)}%"></div>
    <div class="limit" style="left: {pct(max)}%"></div>
  </div>
  <div class="ticks">
    <span class="limit-label min" style="left: {pct(min)}%">min {formatQuantity(min, unit, step)}</span>
    <span class="tick" style="left: {pct(middle)}%" aria-hidden="true">{formatQuantity(middle, unit, step)}</span>
    <span class="limit-label max" style="left: {pct(max)}%">max {formatQuantity(max, unit, step)}</span>
  </div>
</div>

<style>
  .meter {
    padding: 8px 0 0;
  }

  .scale {
    position: relative;
    height: 28px;
    border-bottom: 1px solid var(--border);
  }

  .beyond {
    position: absolute;
    top: 6px;
    bottom: 6px;
    border-radius: 2px;
    border: var(--rule);
    background: var(--surface);
  }

  .range {
    position: absolute;
    top: 0;
    height: 28px;
    margin: 0;
    padding: 0;
    -webkit-appearance: none;
    appearance: none;
    background: transparent;
    cursor: pointer;
  }

  .range::-webkit-slider-runnable-track {
    height: 4px;
    border-radius: 2px;
    background: var(--border);
  }

  .range::-moz-range-track {
    height: 4px;
    border-radius: 2px;
    background: var(--border);
  }

  .range::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    box-sizing: border-box;
    width: 16px;
    height: 16px;
    margin-top: -6px;
    border: 2px solid var(--bg);
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }

  .range::-moz-range-thumb {
    box-sizing: border-box;
    width: 16px;
    height: 16px;
    border: 2px solid var(--bg);
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }

  .range:disabled::-webkit-slider-thumb {
    background: var(--text-2);
    box-shadow: 0 0 0 1px var(--text-2);
  }

  .range:disabled::-moz-range-thumb {
    background: var(--text-2);
    box-shadow: 0 0 0 1px var(--text-2);
  }

  .range:focus-visible {
    outline: var(--focus);
    outline-offset: 0;
    border-radius: var(--radius);
  }

  .range:disabled {
    cursor: not-allowed;
  }

  .limit {
    position: absolute;
    top: -6px;
    bottom: -30px;
    width: 0;
    margin-left: -1px;
    border-left: 2px solid var(--text);
  }

  .now-tick {
    position: absolute;
    bottom: -6px;
    width: 0;
    height: 0;
    margin-left: -5px;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-bottom: 6px solid var(--text-2);
  }

  .ticks {
    position: relative;
    height: 30px;
    font-family: var(--font-mono);
    font-size: var(--t-label);
    color: var(--text-2);
  }

  .ticks span {
    position: absolute;
    top: 10px;
    white-space: nowrap;
    line-height: 1;
  }

  .tick {
    transform: translateX(-50%);
  }

  .limit-label {
    color: var(--text);
    font-weight: 700;
  }

  .limit-label.min {
    padding-left: 8px;
  }

  .limit-label.max {
    padding-right: 8px;
    transform: translateX(-100%);
  }

</style>
