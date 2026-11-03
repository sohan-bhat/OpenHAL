import * as React from "react";
import { cn } from "@/lib/utils";
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from "lucide-react";
import { Select as SelectPrimitive } from "radix-ui";
import { useKeysInOrder } from "./keys-in-order";

/** Whether the list is open, or null outside this file's Select. */
const SelectOpen = React.createContext<boolean | null>(null);

/** shadcn/ui's Select. It keeps its own open state so the list knows the moment it closes, before its exit ends. */
function Select({ open: wanted, defaultOpen, onOpenChange, ...props }: React.ComponentProps<typeof SelectPrimitive.Root>) {
  const [own, setOwn] = React.useState(defaultOpen ?? false);
  const open = wanted ?? own;
  const setOpen = React.useCallback(
    (next: boolean) => {
      setOwn(next);
      onOpenChange?.(next);
    },
    [onOpenChange],
  );
  return (
    <SelectOpen.Provider value={open}>
      <SelectPrimitive.Root data-slot="select" open={open} onOpenChange={setOpen} {...props} />
    </SelectOpen.Provider>
  );
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

type Stop = React.RefObject<(() => void) | null>;

/** Ends the key redirect a closed list left in place. */
function stopRedirect(stop: Stop): void {
  stop.current?.();
  stop.current = null;
}

/**
 * From the moment a list closes until Radix gives focus back, a key pressed with focus in the
 * leaving list or lost to the page moves focus to the list's button first, and a key aimed at the
 * leaving list goes no further, so Tab moves on from the button. Radix keeps focus in a closed list
 * for its 150 ms exit and gives focus back in a timer after that, so Tab right after Enter was lost
 * to the leaving list or started from the page. Focus can't simply move as the list closes, because
 * the Enter that closed it would then press the button and open the list again.
 */
function redirectKeys(trigger: HTMLElement, content: HTMLElement): () => void {
  const redirect = (event: KeyboardEvent) => {
    const focused = document.activeElement;
    const inList = focused !== null && content.contains(focused);
    if (!inList && focused !== null && focused !== document.body) return;
    trigger.focus({ preventScroll: true });
    if (inList) event.stopPropagation();
  };
  document.addEventListener("keydown", redirect, true);
  return () => document.removeEventListener("keydown", redirect, true);
}

/**
 * While the list is open, makes the rest of the page inert as well as hidden by the aria-hidden
 * Radix sets, so no hidden part stays focusable. The inert attribute is set directly rather than
 * through aria-hidden's inertOthers, whose shared counter would leave one of the two attributes
 * behind when both undo. The page comes back the moment the list closes, though the list stays on
 * screen for its exit, and the closed list's keys go to its button until Radix gives focus back. The
 * button is found while the list is open, because only then does it name the list in aria-controls.
 * Radix keeps a closed list's items in a detached fragment, where this does nothing.
 */
function WhileOpen({ stop }: { stop: Stop }) {
  const open = React.useContext(SelectOpen);
  const marker = React.useRef<HTMLSpanElement>(null);
  React.useLayoutEffect(() => {
    const content = marker.current?.closest<HTMLElement>("[data-slot=select-content]");
    if (open === false || !content?.isConnected) return;
    stopRedirect(stop);
    const trigger = content.id ? document.querySelector<HTMLElement>(`[aria-controls="${CSS.escape(content.id)}"]`) : null;
    const others = [...document.body.children].filter((element) => !element.contains(content) && !element.hasAttribute("inert"));
    for (const element of others) element.setAttribute("inert", "");
    return () => {
      for (const element of others) element.removeAttribute("inert");
      stopRedirect(stop);
      if (trigger) stop.current = redirectKeys(trigger, content);
    };
  }, [open, stop]);
  return <span ref={marker} hidden />;
}

/**
 * The list, 4 px under its button or above it where the screen has no room, on the page background
 * in a 1 px border box with no shadow, like the header's pickers. It grows from the button in 200 ms
 * and shrinks back in 150 ms on the site's ease, and with reduced motion it opens and closes at once.
 * While the list is open the rest of the page is inert as well as hidden, because the list holds
 * focus until it closes. Keys run in the order they were pressed, so Enter right after an arrow key
 * chooses the item the arrow reached, and Tab right after Enter moves on from the button. Radix's own
 * return of focus runs only when focus was lost, so it never pulls focus back from where a person
 * has moved on to.
 */
function SelectContent({
  className,
  children,
  position = "popper",
  align = "start",
  sideOffset = 4,
  onKeyDown,
  onKeyDownCapture,
  onCloseAutoFocus,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Content>) {
  const keys = useKeysInOrder();
  const stop = React.useRef<(() => void) | null>(null);
  React.useEffect(() => () => stopRedirect(stop), []);
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        data-slot="select-content"
        onKeyDownCapture={(event) => {
          onKeyDownCapture?.(event);
          keys.onKeyDownCapture(event);
        }}
        onKeyDown={(event) => {
          onKeyDown?.(event);
          keys.onKeyDown(event);
        }}
        onCloseAutoFocus={(event) => {
          onCloseAutoFocus?.(event);
          stopRedirect(stop);
          const focused = document.activeElement;
          if (focused !== null && focused !== document.body) event.preventDefault();
        }}
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
        <WhileOpen stop={stop} />
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
