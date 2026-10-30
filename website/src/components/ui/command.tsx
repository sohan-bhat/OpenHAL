import * as React from "react";
import { Command as CommandPrimitive } from "cmdk";
import { cn } from "@/lib/utils";
import { SearchIcon } from "lucide-react";

/** shadcn/ui's Command on cmdk, themed with the site's tokens. */
function Command({ className, ...props }: React.ComponentProps<typeof CommandPrimitive>) {
  return <CommandPrimitive data-slot="command" className={cn("flex h-full w-full min-h-0 flex-col bg-popover text-popover-foreground", className)} {...props} />;
}

/**
 * The search field. Its row draws a rule underneath that turns to the accent while the field has
 * focus, which stands in for the outline.
 */
function CommandInput({ className, children, ...props }: React.ComponentProps<typeof CommandPrimitive.Input>) {
  return (
    <div data-slot="command-input-wrapper" className="flex min-h-14 shrink-0 items-center gap-3 border-b border-border px-4 focus-within:border-primary focus-within:[box-shadow:inset_0_-0.5px_0_var(--accent)]">
      <SearchIcon aria-hidden="true" strokeWidth={1.75} className="size-[18px] shrink-0 text-primary" />
      <CommandPrimitive.Input
        data-slot="command-input"
        className={cn(
          "h-12 w-full min-w-0 bg-transparent text-base text-foreground outline-none! [-webkit-appearance:none] placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-55",
          className,
        )}
        {...props}
      />
      {children}
    </div>
  );
}

function CommandList({ className, ...props }: React.ComponentProps<typeof CommandPrimitive.List>) {
  return <CommandPrimitive.List data-slot="command-list" className={cn("min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain scroll-py-2 p-2", className)} {...props} />;
}

function CommandEmpty({ className, ...props }: React.ComponentProps<typeof CommandPrimitive.Empty>) {
  return <CommandPrimitive.Empty data-slot="command-empty" className={cn("px-5 py-5 text-sm text-muted-foreground", className)} {...props} />;
}

function CommandLoading({ className, ...props }: React.ComponentProps<typeof CommandPrimitive.Loading>) {
  return <CommandPrimitive.Loading data-slot="command-loading" className={cn("px-5 py-5 text-sm text-muted-foreground", className)} {...props} />;
}

function CommandGroup({ className, ...props }: React.ComponentProps<typeof CommandPrimitive.Group>) {
  return (
    <CommandPrimitive.Group
      data-slot="command-group"
      className={cn(
        "text-foreground [&+&]:mt-2 [&_[cmdk-group-heading]]:flex [&_[cmdk-group-heading]]:items-center [&_[cmdk-group-heading]]:justify-between [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-bold [&_[cmdk-group-heading]]:text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

function CommandSeparator({ className, ...props }: React.ComponentProps<typeof CommandPrimitive.Separator>) {
  return <CommandPrimitive.Separator data-slot="command-separator" className={cn("mx-3 my-2 h-px bg-border", className)} {...props} />;
}

/** A row of the list. The active row sits on the nav's blue highlight with its title in the accent. */
function CommandItem({ className, ...props }: React.ComponentProps<typeof CommandPrimitive.Item>) {
  return (
    <CommandPrimitive.Item
      data-slot="command-item"
      className={cn(
        "relative flex cursor-pointer flex-col gap-0.5 rounded-sm px-3 py-2 text-sm text-foreground no-underline outline-none select-none data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-55 data-[selected=true]:bg-accent [&[data-selected=true]_[data-title]]:text-primary",
        className,
      )}
      {...props}
    />
  );
}

export { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandLoading, CommandSeparator };
