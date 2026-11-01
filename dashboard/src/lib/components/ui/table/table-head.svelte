<script lang="ts">
	import { cn, type WithElementRef } from "$lib/utils.js";
	import type { HTMLThAttributes } from "svelte/elements";

	let {
		ref = $bindable(null),
		class: className,
		children,
		...restProps
	}: WithElementRef<HTMLThAttributes> = $props();
</script>

<th bind:this={ref} data-slot="table-head" class={cn("border-b border-border py-2 pr-3 text-left align-bottom text-sm font-bold whitespace-nowrap text-muted-foreground", className)} {...restProps}>
	{@render children?.()}
</th>
