<script lang="ts">
  import { onDestroy, tick } from "svelte";
  import { CLOSE, OPEN, release, still, tween } from "../../lib/motion";

  interface Props {
    topic: string;
    text: string;
    href?: string;
  }

  let { topic, text, href }: Props = $props();
  let open = $state(false);
  let leaving = $state(false);
  let shift = $state(-8);
  let wrap: HTMLSpanElement | undefined = $state();
  let button: HTMLButtonElement | undefined = $state();
  let pop: HTMLSpanElement | undefined = $state();
  let turn = 0;
  const id = `info-${topic.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`;

  async function show(): Promise<void> {
    const mine = ++turn;
    const settled = !leaving;
    if (wrap && settled) {
      const width = document.documentElement.clientWidth;
      const left = wrap.getBoundingClientRect().left;
      const room = Math.min(300, width * 0.8);
      shift = Math.round(Math.max(8 - left, Math.min(-8, width - 8 - room - left)));
    }
    open = true;
    leaving = false;
    await tick();
    if (!pop || still()) return;
    if (settled) pop.style.opacity = "0";
    await tween(pop, { opacity: [settled ? 0 : null, 1], transform: [settled ? "translateY(-4px)" : null, "none"] }, OPEN);
    if (mine === turn && pop) release(pop, "opacity", "transform");
  }

  async function hide(): Promise<void> {
    const mine = ++turn;
    open = false;
    if (!pop || still()) return;
    leaving = true;
    await tween(pop, { opacity: [null, 0], transform: [null, "translateY(-2px)"] }, CLOSE);
    if (mine !== turn) return;
    leaving = false;
    if (pop) release(pop, "opacity", "transform");
  }

  function outside(event: PointerEvent): void {
    if (open && wrap && !wrap.contains(event.target as Node)) void hide();
  }

  function key(event: KeyboardEvent): void {
    if (open && event.key === "Escape") {
      void hide();
      button?.focus();
    }
  }

  $effect(() => {
    if (!open) return;
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", key);
    };
  });

  onDestroy(() => {
    turn += 1;
    open = false;
  });
</script>

<span class="info-wrap" bind:this={wrap}>
  <button bind:this={button} type="button" class="info" aria-label={`About ${topic}`} aria-expanded={open} aria-controls={id} onclick={() => (open ? hide() : show())}>i</button>
  <span bind:this={pop} {id} class="info-pop" class:leaving style={`left: ${shift}px`} role="note" hidden={!open && !leaving}>
    {text}
    {#if href}<a href={href}>Read more about {topic}</a>{/if}
  </span>
</span>

<style>
  .info-wrap {
    position: relative;
    display: inline-flex;
    vertical-align: middle;
  }

  .info {
    display: inline-grid;
    place-items: center;
    width: 16px;
    height: 16px;
    margin-left: 6px;
    padding: 0;
    border: 1px solid var(--text-2);
    box-shadow: var(--oh-control-ring) var(--text-2);
    border-radius: 50%;
    background: none;
    color: var(--text-2);
    font: inherit;
    font-family: var(--font-text);
    font-size: 13px;
    font-weight: 700;
    line-height: 1;
    cursor: pointer;
  }

  .info::after {
    content: "";
    position: absolute;
    inset: -12px;
  }

  .info:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .info[aria-expanded="true"] {
    color: var(--text);
    border-color: var(--text);
    box-shadow: var(--oh-control-ring) var(--text);
  }

  .info-pop {
    position: absolute;
    top: calc(100% + 8px);
    left: -8px;
    z-index: 5;
    width: max-content;
    max-width: min(300px, 80vw);
    padding: var(--s-3);
    background: var(--bg);
    border: var(--rule);
    border-radius: var(--radius);
    color: var(--text);
    font-family: var(--font-text);
    font-size: var(--t-small);
    font-weight: 400;
    line-height: 1.5;
    white-space: normal;
    text-align: left;
    transform-origin: left top;
  }

  .info-pop[hidden] {
    display: none;
  }

  .info-pop.leaving {
    pointer-events: none;
  }

  .info-pop a {
    display: block;
    margin-top: var(--s-1);
    font-weight: 700;
  }
</style>
