import * as React from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { SidebarMenu } from "@/components/ui/sidebar";
import { Entry, type NavEntry } from "./SidebarNav";
import { useIslandReady } from "./ready";

interface Props {
  label: string;
  entries: NavEntry[];
}

/**
 * A section's pages on a phone, beside "On this page": shadcn/ui's Sheet on Radix Dialog, opened by
 * an outlined Button that reads the section's name with a chevron. The sheet slides in from the left
 * with the sidebar's own rows, the current page marked and every group collapsible. The phone menu
 * keeps only the sections and the theme.
 */
export default function SectionPages({ label, entries }: Props) {
  const trigger = React.useRef<HTMLButtonElement>(null);
  useIslandReady(trigger);

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button ref={trigger} type="button" variant="outline" size="sm" data-section-pages-trigger="" className="relative h-9 gap-1 pr-1.5 pl-3 leading-[1.4] font-normal after:absolute after:-inset-y-1 after:inset-x-0 after:content-[''] data-[state=open]:bg-muted">
          {label}
          <span className="sr-only"> pages</span>
          <ChevronDown aria-hidden="true" strokeWidth={1.75} className="size-[18px]" />
        </Button>
      </SheetTrigger>
      <SheetContent
        side="left"
        className="w-[min(85vw,20rem)] max-w-none outline-none! sm:max-w-none"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          const content = event.target as HTMLElement;
          content.focus({ preventScroll: true });
          content.querySelector("[aria-current=page]")?.scrollIntoView({ block: "center" });
        }}
      >
        <SheetHeader className="h-(--sl-nav-height) shrink-0 justify-center border-b border-border px-4 py-0 pr-14">
          <SheetTitle className="text-base">{label}</SheetTitle>
          <SheetDescription className="sr-only">The pages in {label}</SheetDescription>
        </SheetHeader>
        <nav aria-label={`${label} pages`} className="min-h-0 flex-1 overflow-y-auto px-4 pt-3 pb-8 text-sidebar-foreground">
          <SidebarMenu className="gap-2">
            {entries.map((entry, index) => (
              <Entry key={index} entry={entry} path="" depth={0} />
            ))}
          </SidebarMenu>
        </nav>
      </SheetContent>
    </Sheet>
  );
}
