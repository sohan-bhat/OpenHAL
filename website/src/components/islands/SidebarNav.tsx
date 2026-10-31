import * as React from "react";
import { ChevronRight } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarProvider,
  SidebarRail,
} from "@/components/ui/sidebar";
import { CLOSE, OPEN, release, still, tween } from "@/lib/motion";
import { isCollapsed, rememberGroup, startsOpen } from "@/lib/sidebar";
import { cn } from "@/lib/utils";
import { useIslandReady, withBase } from "./ready";

export interface NavLink {
  label: string;
  href: string;
  current?: boolean;
  badge?: string;
  attrs?: Record<string, string | number | boolean>;
}

export interface NavGroup {
  label: string;
  entries: NavEntry[];
  closed?: boolean;
  badge?: string;
}

export type NavEntry = NavLink | NavGroup;

interface Props {
  entries: NavEntry[];
  hash: string;
}

const WIDE = "(min-width: 50rem)";
const ROW = "h-auto py-[4.5px]";
const CHEVRON = "[&>svg]:size-[18px] motion-safe:[&>svg]:transition-[rotate] motion-safe:[&>svg]:duration-200 motion-safe:[&>svg]:ease-(--ease) [&[data-state=open]>svg]:rotate-90";
const LABEL = cn("h-auto py-1 font-bold text-foreground", CHEVRON);
const SUB = "mx-0 ml-2 translate-x-0 gap-0 px-0 py-0 pl-2 [&[data-state=closed]:not([data-closing])]:hidden";
const SUB_ROW = "h-auto translate-x-0 py-[4.5px]";
const SUB_LABEL = cn(SUB_ROW, "w-full cursor-pointer border-0 bg-transparent py-1 text-left font-bold text-foreground", CHEVRON);

const isGroup = (entry: NavEntry): entry is NavGroup => "entries" in entry;
const holdsCurrent = (entry: NavEntry): boolean => (isGroup(entry) ? entry.entries.some(holdsCurrent) : Boolean(entry.current));

/**
 * The parts of a page that move over when the sidebar hides or shows, each with the element whose
 * place says how far it moves: the content, measured by its column, and the outline beside it or
 * above it.
 */
function movers(): Array<[HTMLElement, HTMLElement]> {
  const pairs: Array<[HTMLElement | null, HTMLElement | null]> = [[document.querySelector("main"), document.querySelector<HTMLElement>("main .sl-container")]];
  for (const element of document.querySelectorAll<HTMLElement>(".right-sidebar, mobile-starlight-toc nav")) pairs.push([element, element]);
  return pairs.filter((pair): pair is [HTMLElement, HTMLElement] => Boolean(pair[0] && pair[1]?.getClientRects().length));
}

/**
 * Marks the root, so the stylesheet gives the content and the outline the space the sidebar leaves
 * or takes, and moves them over from where they stood with Motion while the sidebar slides, using
 * transforms only. A part moving already starts again from where it is.
 */
function moveOver(open: boolean): void {
  const root = document.documentElement;
  const moving = matchMedia(WIDE).matches && !still();
  const before = moving ? movers().map(([mover, probe]) => [mover, probe, probe.getBoundingClientRect().left] as const) : [];
  for (const [mover] of before) {
    for (const animation of mover.getAnimations()) animation.cancel();
    release(mover, "transform");
  }
  if (open) delete root.dataset.sidebar;
  else root.dataset.sidebar = "collapsed";
  const shifts = before.map(([mover, probe, left]) => [mover, left - probe.getBoundingClientRect().left] as const);
  for (const [mover, shift] of shifts) {
    if (Math.abs(shift) < 0.5) continue;
    const from = `translateX(${shift}px)`;
    mover.style.transform = from;
    tween(mover, { transform: [from, "translateX(0px)"] }, open ? OPEN : CLOSE).then(
      () => release(mover, "transform"),
      () => {},
    );
  }
}

const turns = new WeakMap<HTMLElement, number>();

/**
 * Grows a group open or shrinks it closed with Motion, in 200 ms and 150 ms. A closing group stays
 * drawn until its motion ends, and a group pressed again midway turns back from where it is.
 */
function grow(body: HTMLElement, opening: boolean): void {
  if (still()) return;
  const turn = (turns.get(body) ?? 0) + 1;
  turns.set(body, turn);
  const settled = !body.hasAttribute("data-closing");
  body.toggleAttribute("data-closing", !opening);
  const height = opening ? `${body.scrollHeight}px` : "0px";
  body.style.overflow = "hidden";
  if (opening && settled) Object.assign(body.style, { height: "0px", opacity: "0" });
  const frames = opening ? { height: [settled ? "0px" : null, height], opacity: [settled ? 0 : null, 1] } : { height: [null, height], opacity: [null, 0] };
  tween(body, frames, opening ? OPEN : CLOSE).then(
    () => {
      if (turns.get(body) !== turn) return;
      body.removeAttribute("data-closing");
      release(body, "height", "opacity", "overflow");
    },
    () => {},
  );
}

function useGrow(ref: React.RefObject<HTMLElement | null>, open: boolean): void {
  const first = React.useRef(true);
  React.useLayoutEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (ref.current) grow(ref.current, open);
  }, [ref, open]);
}

function Badge({ text }: { text?: string }) {
  return text ? <span className="ml-auto text-xs font-normal text-muted-foreground">{text}</span> : null;
}

function Group({ group, path, depth }: { group: NavGroup; path: string; depth: number }) {
  const key = path ? `${path} / ${group.label}` : group.label;
  const current = holdsCurrent(group);
  const [open, setOpen] = React.useState(() => (typeof document === "undefined" ? current || !group.closed : startsOpen(key, current, Boolean(group.closed))));
  const body = React.useRef<HTMLUListElement>(null);
  useGrow(body, open);
  const toggle = (next: boolean) => {
    setOpen(next);
    rememberGroup(key, next);
  };
  const marks = { "data-group": key, "data-current": current ? "" : undefined, "data-closed": group.closed ? "" : undefined };
  const label = (
    <>
      {group.label}
      <Badge text={group.badge} />
      <ChevronRight aria-hidden="true" strokeWidth={1.75} className={group.badge ? undefined : "ml-auto"} />
    </>
  );
  const content = (
    <CollapsibleContent forceMount asChild>
      <SidebarMenuSub ref={body} className={SUB}>
        {group.entries.map((entry, index) => (
          <Entry key={index} entry={entry} path={key} depth={depth + 1} />
        ))}
      </SidebarMenuSub>
    </CollapsibleContent>
  );

  if (depth === 0) {
    return (
      <Collapsible asChild open={open} onOpenChange={toggle}>
        <SidebarMenuItem {...marks}>
          <CollapsibleTrigger asChild>
            <SidebarMenuButton className={LABEL}>{label}</SidebarMenuButton>
          </CollapsibleTrigger>
          {content}
        </SidebarMenuItem>
      </Collapsible>
    );
  }

  return (
    <Collapsible asChild open={open} onOpenChange={toggle}>
      <SidebarMenuSubItem {...marks}>
        <CollapsibleTrigger asChild>
          <SidebarMenuSubButton asChild className={SUB_LABEL}>
            <button type="button">{label}</button>
          </SidebarMenuSubButton>
        </CollapsibleTrigger>
        {content}
      </SidebarMenuSubItem>
    </Collapsible>
  );
}

function Entry({ entry, path, depth }: { entry: NavEntry; path: string; depth: number }) {
  if (isGroup(entry)) return <Group group={entry} path={path} depth={depth} />;
  const current = Boolean(entry.current);
  const { class: className, ...attrs } = entry.attrs ?? {};
  const link = { href: withBase(entry.href), "aria-current": current ? ("page" as const) : undefined, ...attrs };

  if (depth === 0) {
    return (
      <SidebarMenuItem>
        <SidebarMenuButton asChild isActive={current} className={cn(ROW, String(className ?? ""))}>
          <a {...link}>
            {entry.label}
            <Badge text={entry.badge} />
          </a>
        </SidebarMenuButton>
      </SidebarMenuItem>
    );
  }

  return (
    <SidebarMenuSubItem>
      <SidebarMenuSubButton isActive={current} className={cn(SUB_ROW, String(className ?? ""))} {...link}>
        {entry.label}
        <Badge text={entry.badge} />
      </SidebarMenuSubButton>
    </SidebarMenuSubItem>
  );
}

/**
 * The documentation sidebar, built from shadcn/ui's Sidebar on Starlight's route data, so every page
 * keeps its items, order, numbers, badges and current page. It collapses off canvas from its own
 * SidebarRail and from Command or Control and B, and the content and the outline move over to use
 * the space. Its links are plain links that work without JavaScript, and React loads once a person
 * reaches for a group, the rail or the shortcut.
 */
export default function SidebarNav({ entries, hash }: Props) {
  const [open, setOpen] = React.useState(() => !isCollapsed());
  const rail = React.useRef<HTMLButtonElement>(null);
  useIslandReady(rail);
  const change = React.useCallback((next: boolean) => {
    moveOver(next);
    setOpen(next);
  }, []);

  return (
    <SidebarProvider
      open={open}
      onOpenChange={change}
      className="contents"
      style={{ "--sidebar-width": "calc(var(--oh-gutter) + var(--sl-sidebar-width))", "--sidebar-top": "var(--sl-nav-height)" } as React.CSSProperties}
    >
      <Sidebar id="oh-sidebar">
        <SidebarContent data-hash={hash} className="min-[50rem]:[scrollbar-gutter:stable]">
          <SidebarGroup className="p-0 min-[50rem]:py-4 min-[50rem]:pr-4 min-[50rem]:pl-[calc(var(--oh-gutter)+var(--sl-sidebar-pad-x))]">
            <SidebarMenu className="gap-2">
              {entries.map((entry, index) => (
                <Entry key={index} entry={entry} path="" depth={0} />
              ))}
            </SidebarMenu>
          </SidebarGroup>
        </SidebarContent>
        <SidebarRail ref={rail} aria-controls="oh-sidebar" aria-expanded={open} aria-keyshortcuts="Control+B Meta+B" />
      </Sidebar>
    </SidebarProvider>
  );
}
