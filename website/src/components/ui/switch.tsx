import * as React from "react";
import { cn } from "@/lib/utils";
import { Switch as SwitchPrimitive } from "radix-ui";

/**
 * shadcn/ui's Switch on Radix, drawn the house way: a 30 by 18 track with the 1.5 px outline in the
 * secondary text color, which fills with the accent fill and carries its knob across when on, and a
 * flat surface gray while disabled.
 */
function Switch({ className, ...props }: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        "peer group/switch relative inline-flex h-[18px] w-[30px] shrink-0 cursor-pointer items-center rounded-[9px] border border-muted-foreground bg-transparent [box-shadow:var(--oh-control-ring)_var(--text-2)] outline-offset-3 transition-[background-color,border-color,box-shadow] duration-(--motion-status) ease-linear focus-visible:outline-2 focus-visible:outline-accent data-[state=checked]:border-accent data-[state=checked]:bg-accent-fill data-[state=checked]:[box-shadow:var(--oh-control-ring)_var(--accent)] disabled:cursor-default disabled:border-border disabled:bg-muted disabled:[box-shadow:var(--oh-control-ring)_var(--border)]",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none absolute top-[2px] left-[2px] block size-[11px] rounded-full bg-muted-foreground transition-[translate,background-color] duration-(--motion-status) ease-linear motion-reduce:transition-none group-disabled/switch:bg-border data-[state=checked]:translate-x-3 data-[state=checked]:bg-on-accent"
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
