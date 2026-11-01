<script lang="ts">
	import { Dialog as DialogPrimitive } from "bits-ui";
	import { cn, type WithoutChildrenOrChild } from "$lib/utils.js";
	import { holdPageScroll } from "$lib/holdscroll.js";
	import DialogOverlay from "./dialog-overlay.svelte";
	import DialogPortal from "./dialog-portal.svelte";
	import type { Snippet } from "svelte";
	import type { ComponentProps } from "svelte";

	let {
		ref = $bindable(null),
		class: className,
		portalProps,
		children,
		...restProps
	}: WithoutChildrenOrChild<DialogPrimitive.ContentProps> & {
		portalProps?: WithoutChildrenOrChild<ComponentProps<typeof DialogPortal>>;
		children: Snippet;
	} = $props();

	let overlay = $state<HTMLElement | null>(null);

	$effect(() => (ref ? holdPageScroll(ref) : undefined));
	$effect(() => (overlay ? holdPageScroll(overlay) : undefined));
</script>

<DialogPortal {...portalProps}>
	<DialogOverlay bind:ref={overlay} />
	<DialogPrimitive.Content
		bind:ref
		preventScroll={false}
		data-slot="dialog-content"
		class={cn(
			"fixed top-1/2 left-1/2 z-50 grid max-h-[calc(100dvh-32px)] w-[min(460px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 gap-4 overflow-y-auto overscroll-contain rounded-md border border-border bg-background p-6 text-foreground outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
			className
		)}
		{...restProps}
	>
		{@render children?.()}
	</DialogPrimitive.Content>
</DialogPortal>
