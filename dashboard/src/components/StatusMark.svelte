<script lang="ts">
  import type { Tone } from "../lib/status";

  let {
    tone,
    label,
    compact = false,
  }: { tone: Tone; label: string; compact?: boolean } = $props();
</script>

<span class="status fade-status {tone}" class:compact data-tone={tone}>
  <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
    {#if tone === "ok"}
      <circle cx="6" cy="6" r="5" fill="currentColor" />
    {:else if tone === "confirm" || tone === "pending"}
      <circle cx="6" cy="6" r="4.75" fill="none" stroke="currentColor" stroke-width="1.5" />
      <path d="M6 1.25a4.75 4.75 0 0 0 0 9.5z" fill="currentColor" />
    {:else if tone === "blocked"}
      <circle cx="6" cy="6" r="4.75" fill="none" stroke="currentColor" stroke-width="1.5" />
      <path d="M3 6h6" stroke="currentColor" stroke-width="2" />
    {:else if tone === "unverified"}
      <circle cx="6" cy="6" r="4.75" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="2 1.6" />
    {:else}
      <circle cx="6" cy="6" r="4.75" fill="none" stroke="currentColor" stroke-width="1.5" />
    {/if}
  </svg>
  <span class="word">{label}</span>
</span>

<style>
  .status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--t-label);
    font-weight: 700;
    line-height: 1.2;
    white-space: nowrap;
    color: var(--text-2);
  }

  .status svg {
    flex: none;
  }

  .ok {
    color: var(--ok);
  }

  .confirm,
  .pending {
    color: var(--confirm);
  }

  .blocked {
    color: var(--blocked);
  }

  .unverified {
    color: var(--unverified);
    padding: 1px 6px;
    border: 1px dashed currentColor;
    border-radius: var(--radius);
  }

  .compact .word {
    font-weight: 400;
  }
</style>
