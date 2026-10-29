import * as React from "react";
import { AnimatePresence } from "motion/react";
import * as m from "motion/react-m";
import { cn } from "@/lib/utils";
import { DropdownMenu as DropdownMenuPrimitive } from "radix-ui";
import { useTimings } from "./motion";

interface MenuState {
  open: boolean;
  setOpen: (open: boolean) => void;
  trigger: React.RefObject<HTMLButtonElement | null>;
  leaving: React.RefObject<"forward" | "backward" | null>;
}

const MenuContext = React.createContext<MenuState | null>(null);

const TABBABLE = "a[href], button:not([disabled]), input:not([disabled]):not([type='hidden']), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";

/** The element after or before `from` in the page's tab order, skipping hidden and inert parts. */
function neighbor(from: Element, direction: "forward" | "backward"): HTMLElement | null {
  const all = [...document.querySelectorAll<HTMLElement>(TABBABLE)].filter((element) => element.getClientRects().length && !element.closest("[inert], [data-radix-popper-content-wrapper]"));
  const at = all.indexOf(from as HTMLElement);
  if (at < 0) return null;
  return all[direction === "forward" ? at + 1 : at - 1] ?? null;
}

/**
 * shadcn/ui's DropdownMenu, kept non-modal like a native popover, so a click on another picker
 * closes this one and opens that one. It keeps its own open state so the list can leave with Motion.
 */
function DropdownMenu({ open: wanted, defaultOpen, onOpenChange, modal = false, ...props }: React.ComponentProps<typeof DropdownMenuPrimitive.Root>) {
  const [own, setOwn] = React.useState(defaultOpen ?? false);
  const open = wanted ?? own;
  const trigger = React.useRef<HTMLButtonElement | null>(null);
  const leaving = React.useRef<"forward" | "backward" | null>(null);
  const setOpen = React.useCallback(
    (next: boolean) => {
      setOwn(next);
      onOpenChange?.(next);
    },
    [onOpenChange],
  );
  const state = React.useMemo(() => ({ open, setOpen, trigger, leaving }), [open, setOpen]);
  return (
    <MenuContext.Provider value={state}>
      <DropdownMenuPrimitive.Root data-slot="dropdown-menu" open={open} onOpenChange={setOpen} modal={modal} {...props} />
    </MenuContext.Provider>
  );
}

/** True while the menu around the caller is open, so its trigger can turn its chevron. */
function useMenuOpen(): boolean {
  return React.useContext(MenuContext)?.open ?? false;
}

function DropdownMenuTrigger({ ...props }: React.ComponentProps<typeof DropdownMenuPrimitive.Trigger>) {
  const state = React.useContext(MenuContext);
  return <DropdownMenuPrimitive.Trigger data-slot="dropdown-menu-trigger" ref={state?.trigger} {...props} />;
}

/**
 * The list, 4 px from its button on the page background in a 1 px border box with no shadow. It
 * grows from the button in 200 ms and shrinks back in 150 ms, and Tab closes it and moves on the
 * way a menu button's list should.
 */
function DropdownMenuContent({
  className,
  sideOffset = 4,
  children,
  onKeyDown,
  onCloseAutoFocus,
  container,
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Content> & { container?: HTMLElement }) {
  const state = React.useContext(MenuContext);
  const { open: enter, close } = useTimings();

  return (
    <AnimatePresence>
      {state?.open && (
        <DropdownMenuPrimitive.Portal forceMount container={container}>
          <DropdownMenuPrimitive.Content
            data-slot="dropdown-menu-content"
            sideOffset={sideOffset}
            loop
            forceMount
            asChild
            onKeyDown={(event) => {
              onKeyDown?.(event);
              if (event.key !== "Tab" || !state) return;
              event.preventDefault();
              state.leaving.current = event.shiftKey ? "backward" : "forward";
              state.setOpen(false);
            }}
            onCloseAutoFocus={(event) => {
              onCloseAutoFocus?.(event);
              const direction = state?.leaving.current;
              if (!direction || !state?.trigger.current) return;
              state.leaving.current = null;
              const next = neighbor(state.trigger.current, direction);
              if (!next) return;
              event.preventDefault();
              next.focus();
            }}
            {...props}
          >
            <m.div
              className={cn(
                "z-50 max-h-(--radix-dropdown-menu-content-available-height) min-w-[max(var(--radix-dropdown-menu-trigger-width),7rem)] origin-(--radix-dropdown-menu-content-transform-origin) overflow-x-hidden overflow-y-auto rounded-md border border-border bg-popover p-1 text-popover-foreground outline-none!",
                className,
              )}
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1, transition: enter }}
              exit={{ opacity: 0, scale: 0.98, transition: close }}
            >
              {children}
            </m.div>
          </DropdownMenuPrimitive.Content>
        </DropdownMenuPrimitive.Portal>
      )}
    </AnimatePresence>
  );
}

const ITEM =
  "relative flex w-full cursor-pointer items-center rounded-sm px-3 py-1.5 text-sm leading-[1.4] whitespace-nowrap text-foreground no-underline outline-none select-none data-[highlighted]:bg-muted focus-visible:-outline-offset-2! data-[disabled]:pointer-events-none data-[disabled]:opacity-55 aria-[current]:bg-accent aria-[current]:text-primary data-[state=checked]:bg-accent data-[state=checked]:text-primary";

function DropdownMenuItem({ className, ...props }: React.ComponentProps<typeof DropdownMenuPrimitive.Item>) {
  return <DropdownMenuPrimitive.Item data-slot="dropdown-menu-item" className={cn(ITEM, className)} {...props} />;
}

function DropdownMenuRadioGroup({ ...props }: React.ComponentProps<typeof DropdownMenuPrimitive.RadioGroup>) {
  return <DropdownMenuPrimitive.RadioGroup data-slot="dropdown-menu-radio-group" {...props} />;
}

/** A choice in a radio group, shown as its word only, with the checked one on the nav's blue highlight. */
function DropdownMenuRadioItem({ className, ...props }: React.ComponentProps<typeof DropdownMenuPrimitive.RadioItem>) {
  return <DropdownMenuPrimitive.RadioItem data-slot="dropdown-menu-radio-item" className={cn(ITEM, className)} {...props} />;
}

export { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger, useMenuOpen };
