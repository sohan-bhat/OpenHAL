import * as React from "react";
import * as m from "motion/react-m";
import { cn } from "@/lib/utils";
import { Dialog as DialogPrimitive } from "radix-ui";
import { useTimings } from "./motion";

function Dialog({ ...props }: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />;
}

function DialogTrigger({ ...props }: React.ComponentProps<typeof DialogPrimitive.Trigger>) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />;
}

function DialogClose({ ...props }: React.ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />;
}

/**
 * shadcn/ui's DialogContent with its overlay, kept mounted for Motion so both fade out before they
 * leave. Render it inside AnimatePresence, only while the dialog is open.
 */
function DialogContent({
  className,
  overlayClassName,
  children,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & { overlayClassName?: string }) {
  const { open, close } = useTimings();
  return (
    <DialogPrimitive.Portal forceMount data-slot="dialog-portal">
      <DialogPrimitive.Overlay forceMount asChild>
        <m.div
          data-slot="dialog-overlay"
          className={cn("fixed inset-0 z-50 bg-(--oh-overlay)", overlayClassName)}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, transition: open }}
          exit={{ opacity: 0, transition: close }}
        />
      </DialogPrimitive.Overlay>
      <DialogPrimitive.Content data-slot="dialog-content" forceMount asChild {...props}>
        <m.div
          className={cn("fixed z-50 flex flex-col overflow-hidden border border-border bg-background text-foreground outline-none", className)}
          initial={{ opacity: 0, y: -8, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1, transition: open }}
          exit={{ opacity: 0, y: -4, scale: 0.98, transition: close }}
        >
          {children}
        </m.div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

function DialogTitle({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return <DialogPrimitive.Title data-slot="dialog-title" className={cn("text-base font-bold", className)} {...props} />;
}

function DialogDescription({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return <DialogPrimitive.Description data-slot="dialog-description" className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

export { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger };
