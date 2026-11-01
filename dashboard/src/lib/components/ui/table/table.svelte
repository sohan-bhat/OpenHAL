<script lang="ts">
	import { cn, type WithElementRef } from "$lib/utils.js";
	import type { HTMLTableAttributes } from "svelte/elements";

	let {
		ref = $bindable(null),
		class: className,
		region,
		children,
		...restProps
	}: WithElementRef<HTMLTableAttributes> & { region: string } = $props();
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	data-slot="table-container"
	class="relative w-full max-w-full overflow-x-auto focus-visible:outline-offset-[-2px]"
	tabindex="0"
	role="region"
	aria-label={region}
>
	<table
		bind:this={ref}
		data-slot="table"
		class={cn("w-full border-collapse text-base", className)}
		{...restProps}
	>
		{@render children?.()}
	</table>
</div>
