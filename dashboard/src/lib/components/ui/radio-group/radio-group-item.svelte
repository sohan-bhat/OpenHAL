<script lang="ts">
	import { RadioGroup as RadioGroupPrimitive } from "bits-ui";
	import { cn, type WithoutChildrenOrChild } from "$lib/utils.js";
	import type { Snippet } from "svelte";

	let {
		ref = $bindable(null),
		class: className,
		children: label,
		...restProps
	}: WithoutChildrenOrChild<RadioGroupPrimitive.ItemProps> & { children?: Snippet } = $props();
</script>

<RadioGroupPrimitive.Item
	bind:ref
	data-slot="radio-group-item"
	class={cn(
		"group/radio inline-flex min-h-9 cursor-pointer items-center gap-2 border-r border-border px-3 last:border-r-0 first:rounded-l-md last:rounded-r-md focus-visible:outline-offset-[-2px] data-[state=checked]:bg-muted data-[state=checked]:font-bold disabled:cursor-not-allowed disabled:text-muted-foreground",
		className
	)}
	{...restProps}
>
	{#snippet children({ checked })}
		<span
			aria-hidden="true"
			class={cn(
				"flex size-[18px] shrink-0 items-center justify-center rounded-full border-[1.5px] border-muted-foreground bg-background group-hover/radio:border-foreground",
				checked && "border-accent group-hover/radio:border-accent"
			)}
		>
			{#if checked}<span class="size-2 rounded-full bg-accent"></span>{/if}
		</span>
		{@render label?.()}
	{/snippet}
</RadioGroupPrimitive.Item>
