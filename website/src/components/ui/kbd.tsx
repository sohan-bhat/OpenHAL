import { cn } from "@/lib/utils";

/** shadcn/ui's Kbd, drawn like the header's search shortcut: a ringed key in the text face at the legend size. */
function Kbd({ className, ...props }: React.ComponentProps<"kbd">) {
  return (
    <kbd
      data-slot="kbd"
      className={cn(
        "pointer-events-none inline-flex h-[23px] min-w-[23px] items-center justify-center gap-[0.25em] rounded-sm border border-border bg-background px-1.5 font-sans! text-xs font-bold text-muted-foreground select-none [box-shadow:var(--oh-control-ring)_var(--border)]",
        "[&_svg:not([class*='size-'])]:size-3",
        className,
      )}
      {...props}
    />
  );
}

function KbdGroup({ className, ...props }: React.ComponentProps<"kbd">) {
  return <kbd data-slot="kbd-group" className={cn("inline-flex items-center gap-1 font-sans!", className)} {...props} />;
}

export { Kbd, KbdGroup };
