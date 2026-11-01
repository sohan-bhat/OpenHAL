<script lang="ts">
	import { cn, type WithElementRef } from "$lib/utils.js";
	import type { HTMLTdAttributes } from "svelte/elements";

	let {
		ref = $bindable(null),
		class: className,
		children,
		...restProps
	}: WithElementRef<HTMLTdAttributes> = $props();
</script>

<td bind:this={ref} data-slot="table-cell" class={cn("border-b border-[color-mix(in_srgb,var(--border)_60%,transparent)] py-2 pr-3 align-top", className)} {...restProps}>
	{@render children?.()}
</td>
