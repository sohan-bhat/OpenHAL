<script lang="ts">
  import { Slider } from "$lib/components/ui/slider/index.js";
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
    interactive = true,
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
    interactive?: boolean;
    oninput?: (value: string) => void;
  } = $props();

  const span = $derived(max - min || 1);
  const scaleMin = $derived(min > 0 ? min - span * 0.12 : min);
  const scaleMax = $derived(max + span * 0.2);
  const pct = (point: number) => ((point - scaleMin) / (scaleMax - scaleMin)) * 100;
  const middle = $derived(span >= 10 ? Math.round(min + span / 2) : min + span / 2);
  const clamp = (point: number) => Math.min(Math.max(point, scaleMin), scaleMax);
  const stride = $derived(step ?? (span >= 10 ? 1 : 10 ** Math.floor(Math.log10(span / 10))));
  const places = $derived(Math.max(0, -Math.floor(Math.log10(stride))));
  const shown = $derived(value === null ? min : Math.min(Math.max(value, min), max));

  function moved(next: number) {
    oninput?.(String(Number(next.toFixed(places))));
  }
</script>

<div class="meter">
  <div class="scale">
    {#if min > scaleMin}<div class="beyond" style="left: 0; width: {pct(min)}%"></div>{/if}
    <div class="beyond" style="left: {pct(max)}%; right: 0"></div>
    {#if current !== null}
      <div class="now-tick" style="left: {pct(clamp(current))}%"></div>
    {/if}
    {#if interactive}
      <div class="range" style="left: {pct(min)}%; width: {pct(max) - pct(min)}%">
        <Slider
          {id}
          {label}
          {min}
          {max}
          step={stride}
          value={shown}
          valueText={value !== null ? quantityString(value, unit) : undefined}
          {disabled}
          onValueChange={moved}
        />
      </div>
    {:else}
      <div class="track" style="left: {pct(min)}%; width: {pct(max) - pct(min)}%"></div>
    {/if}
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
    z-index: 1;
  }

  .track {
    position: absolute;
    top: 12px;
    height: 4px;
    border-radius: 2px;
    background: var(--border);
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
