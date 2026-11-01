<script lang="ts">
	import { cn, type WithElementRef, type WithoutChildren } from "$lib/utils.js";
	import type { HTMLTextareaAttributes } from "svelte/elements";

	let {
		ref = $bindable(null),
		value = $bindable(),
		class: className,
		"data-slot": dataSlot = "textarea",
		...restProps
	}: WithoutChildren<WithElementRef<HTMLTextareaAttributes>> = $props();
</script>

<textarea
	bind:this={ref}
	data-slot={dataSlot}
	class={cn(
		"min-h-[120px] w-full resize-y rounded-md border border-input bg-background px-2 py-1 font-mono text-(length:--t-mono) text-foreground [box-shadow:var(--control-ring)_var(--control-border)] transition-[border-color,box-shadow] placeholder:text-muted-foreground not-disabled:hover:border-muted-foreground not-disabled:hover:[box-shadow:var(--control-ring)_var(--text-2)] disabled:cursor-not-allowed disabled:border-muted disabled:bg-muted disabled:text-muted-foreground disabled:[box-shadow:none]",
		className
	)}
	bind:value
	{...restProps}></textarea>
