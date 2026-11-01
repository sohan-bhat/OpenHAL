<script lang="ts">
  import type { Snippet } from "svelte";
  import { AspectRatio } from "$lib/components/ui/aspect-ratio/index.js";
  import { Badge } from "$lib/components/ui/badge/index.js";
  import { Button } from "$lib/components/ui/button/index.js";
  import { frames } from "../lib/frames.svelte";
  import { imageFacts, imageSize, type ImageReading } from "../lib/images";
  import { formatTime } from "../lib/trace";

  let {
    device,
    channel,
    label,
    latest = null,
    width = 640,
    demo = false,
    heading,
  }: {
    device: string;
    channel: string;
    label: string;
    latest?: ImageReading | null;
    width?: number;
    demo?: boolean;
    heading?: Snippet;
  } = $props();

  const frame = $derived(frames.get(device, channel));
  const image = $derived(frame?.image ?? latest);
  const size = $derived(image ? imageSize(image) : null);
  const shownWidth = $derived(Math.min(width, size?.width ?? width));
  const ratio = $derived(size && size.height > 0 ? size.width / size.height : 4 / 3);
  const time = $derived(frame?.at ? formatTime(new Date(frame.at * 1000)).slice(0, 8) : "");

  $effect(() => {
    frames.ensure(device, channel, latest);
  });
</script>

<div class="frame" style="max-width: {shownWidth}px">
  <div class="head">
    {@render heading?.()}
    <Button size="sm" class="ml-auto" disabled={frame?.reading} onclick={() => void frames.read(device, channel)}>
      Read frame
    </Button>
  </div>
  <figure>
    <AspectRatio ratio={ratio} class="overflow-hidden rounded-md border border-border bg-muted">
      {#if frame?.src}
        <img
          src={frame.src}
          alt="{demo ? 'Demo frame' : 'Latest frame'} from {label}{time ? `, read at ${time}` : ''}"
          width={size?.width}
          height={size?.height}
          decoding="async"
          draggable="false"
        />
      {:else if frame && !frame.reading}
        <p class="none">No frame to show</p>
      {:else}
        <p class="none" aria-hidden="true">&emsp;</p>
      {/if}
    </AspectRatio>
    <figcaption>
      <span class="facts mono">
        {#if demo}<Badge class="font-sans">demo frame</Badge>{/if}
        {#if image}{#each imageFacts(image) as fact (fact)}<span>{fact}</span>{/each}{:else}<span>no frame read yet</span>{/if}
      </span>
      <span class="when" aria-live="polite">
        {#if frame?.reading}reading…{:else if time}read at <span class="mono">{time}</span>{/if}
      </span>
    </figcaption>
  </figure>
  {#if frame?.problem}
    <div class="problem" role="alert">
      <p>{frame.problem}{frame.src ? " The frame above is the last one read." : ""}</p>
      {#if frame.detail}<p class="label">Reason, shown as data</p><p class="detail">{frame.detail}</p>{/if}
    </div>
  {/if}
</div>

<style>
  .frame {
    display: grid;
    gap: var(--s-2);
    width: 100%;
    min-width: 0;
  }

  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    justify-content: space-between;
    gap: var(--s-2) var(--s-3);
    min-height: 30px;
  }

  figure {
    display: grid;
    gap: var(--s-2);
    margin: 0;
  }

  img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }

  .none {
    display: grid;
    place-items: center;
    height: 100%;
    color: var(--text-2);
  }

  figcaption {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--s-1) var(--s-3);
    font-size: var(--t-label);
    color: var(--text-2);
  }

  .facts {
    display: inline-flex;
    flex-wrap: wrap;
    gap: 0 var(--s-3);
    font-size: var(--t-label);
    color: var(--text);
  }

  .when {
    font-variant-numeric: tabular-nums;
  }

  .when .mono {
    font-size: var(--t-label);
  }

  .problem .label {
    margin-top: var(--s-2);
  }

  .detail {
    overflow-wrap: anywhere;
  }
</style>
