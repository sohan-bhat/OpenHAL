import * as React from "react";
import { AnimatePresence } from "motion/react";
import * as m from "motion/react-m";
import { cn } from "@/lib/utils";
import { Tooltip as TooltipPrimitive } from "radix-ui";
import { useTimings } from "./motion";

const OpenContext = React.createContext(false);

function TooltipProvider({ delayDuration = 300, ...props }: React.ComponentProps<typeof TooltipPrimitive.Provider>) {
  return <TooltipPrimitive.Provider data-slot="tooltip-provider" delayDuration={delayDuration} {...props} />;
}

/** shadcn/ui's Tooltip, which keeps its own open state so the content can leave with Motion. */
function Tooltip({ open: wanted, defaultOpen, onOpenChange, ...props }: React.ComponentProps<typeof TooltipPrimitive.Root>) {
  const [own, setOwn] = React.useState(defaultOpen ?? false);
  const open = wanted ?? own;
  const change = React.useCallback(
    (next: boolean) => {
      setOwn(next);
      onOpenChange?.(next);
    },
    [onOpenChange],
  );
  return (
    <OpenContext.Provider value={open}>
      <TooltipPrimitive.Root data-slot="tooltip" open={open} onOpenChange={change} {...props} />
    </OpenContext.Provider>
  );
}

function TooltipTrigger({ ...props }: React.ComponentProps<typeof TooltipPrimitive.Trigger>) {
  return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />;
}

/** The tooltip itself, on the page background in a 1 px border box, fading in 200 ms and out in 150 ms. */
function TooltipContent({ className, sideOffset = 6, children, ...props }: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  const open = React.useContext(OpenContext);
  const { open: enter, close } = useTimings();
  return (
    <AnimatePresence>
      {open && (
        <TooltipPrimitive.Portal forceMount>
          <TooltipPrimitive.Content data-slot="tooltip-content" sideOffset={sideOffset} forceMount asChild {...props}>
            <m.div
              className={cn(
                "z-50 flex w-fit origin-(--radix-tooltip-content-transform-origin) items-center gap-2 rounded-md border border-border bg-popover px-2 py-1 text-sm text-popover-foreground",
                className,
              )}
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1, transition: enter }}
              exit={{ opacity: 0, scale: 0.98, transition: close }}
            >
              {children}
            </m.div>
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      )}
    </AnimatePresence>
  );
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
