<script lang="ts">
	import { AlertDialog as AlertDialogPrimitive } from "bits-ui";
	import { cn, type WithoutChild, type WithoutChildrenOrChild } from "$lib/utils.js";
	import { holdPageScroll } from "$lib/holdscroll.js";
	import AlertDialogOverlay from "./alert-dialog-overlay.svelte";
	import AlertDialogPortal from "./alert-dialog-portal.svelte";
	import type { ComponentProps } from "svelte";

	let {
		ref = $bindable(null),
		class: className,
		portalProps,
		onOpenAutoFocus,
		...restProps
	}: WithoutChild<AlertDialogPrimitive.ContentProps> & {
		portalProps?: WithoutChildrenOrChild<ComponentProps<typeof AlertDialogPortal>>;
	} = $props();

	let overlay = $state<HTMLElement | null>(null);

	function focusCancel(event: Event) {
		onOpenAutoFocus?.(event);
		if (event.defaultPrevented) return;
		const cancel = ref?.querySelector<HTMLElement>("[data-alert-dialog-cancel]");
		if (!cancel) return;
		event.preventDefault();
		cancel.focus();
	}

	$effect(() => (ref ? holdPageScroll(ref) : undefined));
	$effect(() => (overlay ? holdPageScroll(overlay) : undefined));
</script>

<AlertDialogPortal {...portalProps}>
	<AlertDialogOverlay bind:ref={overlay} />
	<AlertDialogPrimitive.Content
		bind:ref
		preventScroll={false}
		onOpenAutoFocus={focusCancel}
		data-slot="alert-dialog-content"
		class={cn(
			"fixed top-1/2 left-1/2 z-50 grid max-h-[calc(100dvh-32px)] w-[min(460px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 gap-4 overflow-y-auto overscroll-contain rounded-md border border-border bg-background p-6 text-foreground outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
			className
		)}
		{...restProps}
	/>
</AlertDialogPortal>
