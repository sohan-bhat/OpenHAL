import * as m from "motion/react-m";
import { ChevronDown } from "lucide-react";
import { useMenuOpen } from "@/components/ui/dropdown-menu";
import { useTimings } from "@/components/ui/motion";

/** A picker's menu button in the header and the phone menu: its word and a chevron, never an icon. */
export const PICKER =
  "inline-flex h-9 shrink-0 cursor-pointer items-center gap-0.5 rounded-md bg-transparent pr-1 pl-2 text-sm leading-[1.4] font-semibold whitespace-nowrap text-muted-foreground hover:bg-muted hover:text-foreground data-[state=open]:bg-muted data-[state=open]:text-foreground";

/** The chevron after a picker's word, which turns over in 200 ms while the list is open. */
export function Chevron() {
  const open = useMenuOpen();
  const { open: enter, close } = useTimings();
  return (
    <m.span aria-hidden="true" className="inline-flex" initial={false} animate={{ rotate: open ? 180 : 0 }} transition={open ? enter : close}>
      <ChevronDown strokeWidth={1.75} className="size-[18px]" />
    </m.span>
  );
}

/** Where a menu inside the phone menu renders its list: inside the menu, which sits in the top layer. */
export function menuContainer(place: "header" | "menu"): HTMLElement | undefined {
  if (place !== "menu" || typeof document === "undefined") return undefined;
  return document.getElementById("starlight__sidebar") ?? undefined;
}
