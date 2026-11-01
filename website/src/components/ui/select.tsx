import * as React from "react";
import { suppressOthers } from "aria-hidden";
import { cn } from "@/lib/utils";
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from "lucide-react";
import { Select as SelectPrimitive } from "radix-ui";

function Select({ ...props }: React.ComponentProps<typeof SelectPrimitive.Root>) {
  return <SelectPrimitive.Root data-slot="select" {...props} />;
}

function SelectGroup({ ...props }: React.ComponentProps<typeof SelectPrimitive.Group>) {
  return <SelectPrimitive.Group data-slot="select-group" {...props} />;
}

function SelectValue({ ...props }: React.ComponentProps<typeof SelectPrimitive.Value>) {
  return <SelectPrimitive.Value data-slot="select-value" {...props} />;
}

/**
 * The select's button, a 40 px field with the 1.5 px control outline, its value's word and a chevron
 * that turns over while the list is open.
 */
function SelectTrigger({ className, children, ...props }: React.ComponentProps<typeof SelectPrimitive.Trigger>) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      className={cn(
        "flex h-10 w-full cursor-pointer items-center justify-between gap-2 rounded-md border border-input bg-background pr-2 pl-3 text-left text-base whitespace-nowrap text-foreground [box-shadow:var(--oh-control-ring)_var(--oh-control-border)] outline-offset-2 hover:border-muted-foreground hover:[box-shadow:var(--oh-control-ring)_var(--text-2)] focus-visible:outline-2 focus-visible:outline-accent disabled:cursor-default disabled:border-border disabled:bg-muted disabled:text-muted-foreground data-[state=open]:border-muted-foreground data-[state=open]:[box-shadow:var(--oh-control-ring)_var(--text-2)] *:data-[slot=select-value]:truncate [&_svg]:pointer-events-none [&_svg]:shrink-0",
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDownIcon
          strokeWidth={1.75}
          className="size-[18px] text-muted-foreground transition-transform duration-200 ease-out in-data-[state=open]:rotate-180 motion-reduce:transition-none"
        />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}

/**
 * The list, 4 px under its button or above it where the screen has no room, on the page background
 * in a 1 px border box with no shadow, like the header's pickers. It grows from the button in 200 ms
 * and shrinks back in 150 ms on the site's ease, and with reduced motion it opens and closes at once.
 * While the list is open the rest of the page is inert as well as hidden, through aria-hidden's
 * suppressOthers, because the list holds focus until it closes.
 */
function SelectContent({
  className,
  children,
  position = "popper",
  align = "start",
  sideOffset = 4,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Content>) {
  const undo = React.useRef<(() => void) | null>(null);
  const suppress = React.useCallback((node: HTMLDivElement | null) => {
    undo.current?.();
    undo.current = node?.isConnected ? suppressOthers(node) : null;
  }, []);
  React.useEffect(() => () => undo.current?.(), []);
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        ref={suppress}
        data-slot="select-content"
        className={cn(
          "relative z-50 max-h-(--radix-select-content-available-height) min-w-(--radix-select-trigger-width) origin-(--radix-select-content-transform-origin) overflow-x-hidden overflow-y-auto rounded-md border border-border bg-popover text-popover-foreground outline-none",
          "ease-out data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-98 data-[state=closed]:duration-150 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-98 data-[state=open]:duration-200 motion-reduce:animate-none!",
          className,
        )}
        position={position}
        align={align}
        sideOffset={position === "popper" ? sideOffset : undefined}
        {...props}
      >
        <SelectScrollUpButton />
        <SelectPrimitive.Viewport className="p-1">{children}</SelectPrimitive.Viewport>
        <SelectScrollDownButton />
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
}

function SelectLabel({ className, ...props }: React.ComponentProps<typeof SelectPrimitive.Label>) {
  return <SelectPrimitive.Label data-slot="select-label" className={cn("px-3 py-1.5 text-sm font-bold text-muted-foreground", className)} {...props} />;
}

/** A choice, its word only, with the chosen one in bold on the surface highlight and the component's check mark. */
function SelectItem({ className, children, ...props }: React.ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item
      data-slot="select-item"
      className={cn(
        "relative flex w-full cursor-pointer items-center rounded-sm py-1.5 pr-9 pl-3 text-sm leading-[1.4] whitespace-nowrap text-foreground outline-none select-none focus-visible:-outline-offset-2! data-[disabled]:pointer-events-none data-[disabled]:opacity-55 data-[highlighted]:bg-muted data-[state=checked]:bg-highlight data-[state=checked]:font-bold",
        className,
      )}
      {...props}
    >
      <span data-slot="select-item-indicator" className="absolute right-3 flex size-4 items-center justify-center">
        <SelectPrimitive.ItemIndicator>
          <CheckIcon strokeWidth={2} className="size-4" />
        </SelectPrimitive.ItemIndicator>
      </span>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  );
}

function SelectSeparator({ className, ...props }: React.ComponentProps<typeof SelectPrimitive.Separator>) {
  return <SelectPrimitive.Separator data-slot="select-separator" className={cn("pointer-events-none -mx-1 my-1 h-px bg-border", className)} {...props} />;
}

function SelectScrollUpButton({ className, ...props }: React.ComponentProps<typeof SelectPrimitive.ScrollUpButton>) {
  return (
    <SelectPrimitive.ScrollUpButton data-slot="select-scroll-up-button" className={cn("flex cursor-default items-center justify-center py-1 text-muted-foreground", className)} {...props}>
      <ChevronUpIcon className="size-4" />
    </SelectPrimitive.ScrollUpButton>
  );
}

function SelectScrollDownButton({ className, ...props }: React.ComponentProps<typeof SelectPrimitive.ScrollDownButton>) {
  return (
    <SelectPrimitive.ScrollDownButton data-slot="select-scroll-down-button" className={cn("flex cursor-default items-center justify-center py-1 text-muted-foreground", className)} {...props}>
      <ChevronDownIcon className="size-4" />
    </SelectPrimitive.ScrollDownButton>
  );
}

export { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectScrollDownButton, SelectScrollUpButton, SelectSeparator, SelectTrigger, SelectValue };
