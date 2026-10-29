import * as React from "react";
import { AnimatePresence } from "motion/react";
import { ArrowDown, ArrowUp, SearchIcon } from "lucide-react";
import { isShortcut } from "../../directives/intent";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandLoading } from "@/components/ui/command";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/kbd";
import { MotionRoot } from "@/components/ui/motion";
import { cn } from "@/lib/utils";
import { useIslandReady, withBase } from "./ready";
import { type Group, type Section, type Segment, group, highlight, marked } from "./search/hits";
import { BASE, pagefind, search } from "./search/pagefind";
import { forget, readRecent, remember } from "./search/recent";

interface Suggestion {
  label: string;
  href: string;
}

interface Props {
  sections: Section[];
  suggestions: Suggestion[];
}

type Found = { status: "idle" } | { status: "pending" } | { status: "loading" } | { status: "error" } | { status: "done"; query: string; groups: Group[] };

function Text({ parts, className }: { parts: Segment[]; className?: string }) {
  return (
    <span className={className}>
      {parts.map((part, index) =>
        part.mark ? (
          <mark key={index} className="rounded-xs bg-transparent font-bold text-primary">
            {part.text}
          </mark>
        ) : (
          <React.Fragment key={index}>{part.text}</React.Fragment>
        ),
      )}
    </span>
  );
}

/**
 * The site search: the header's search field and a command palette over the site's Pagefind index,
 * built from shadcn/ui's Command and Dialog on cmdk and Radix, opening and closing with Motion.
 */
export default function SearchPalette({ sections, suggestions }: Props) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [found, setFound] = React.useState<Found>({ status: "idle" });
  const [recent, setRecent] = React.useState<string[]>([]);
  const [active, setActive] = React.useState("");
  const trigger = React.useRef<HTMLButtonElement>(null);
  const pointer = React.useRef(false);
  useIslandReady(trigger);

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!isShortcut("mod+k", event)) return;
      event.preventDefault();
      setOpen((was) => !was);
    };
    document.addEventListener("keydown", onKey);
    void pagefind().catch(() => {});
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  React.useEffect(() => {
    if (open) setRecent(readRecent());
  }, [open]);

  React.useEffect(() => {
    const term = query.trim();
    if (!open || !term) {
      setFound({ status: "idle" });
      return;
    }
    let live = true;
    setFound((was) => (was.status === "idle" ? { status: "pending" } : was));
    const slow = window.setTimeout(() => live && setFound((was) => (was.status === "done" ? was : { status: "loading" })), 150);
    search(term)
      .then((results) => {
        if (!live || !results) return;
        setFound({ status: "done", query: term, groups: group(results, sections, BASE) });
      })
      .catch(() => live && setFound({ status: "error" }))
      .finally(() => window.clearTimeout(slow));
    return () => {
      live = false;
      window.clearTimeout(slow);
    };
  }, [query, open, sections]);

  React.useEffect(() => {
    if (found.status === "done") setActive(found.groups[0]?.hits[0]?.id ?? "");
    else if (found.status === "idle") setActive(recent[0] ? `recent ${recent[0]}` : suggestions[0] ? `go ${suggestions[0].href}` : "");
  }, [found, recent, suggestions]);

  const go = (href: string, term: string) => {
    setRecent(remember(term));
    if (pointer.current) {
      pointer.current = false;
      return;
    }
    setOpen(false);
    window.location.assign(href);
  };

  const hits = found.status === "done" ? found.groups.reduce((sum, item) => sum + item.hits.length, 0) : 0;
  const pages = found.status === "done" ? new Set(found.groups.flatMap((item) => item.hits.map((hit) => hit.url.split("#")[0]))).size : 0;
  const announce =
    found.status === "done" ? (hits ? `${pages} ${pages === 1 ? "page" : "pages"} found` : `No results for ${found.query}`) : found.status === "error" ? "Search could not load" : "";

  return (
    <MotionRoot>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setQuery("");
        }}
      >
        <DialogTrigger asChild>
          <button
            ref={trigger}
            type="button"
            data-search-trigger=""
            aria-label="Search"
            aria-keyshortcuts="Control+K Meta+K"
            className={cn(
              "flex h-10 shrink-0 cursor-pointer items-center gap-2 rounded-md bg-transparent px-1.5 text-sm text-muted-foreground",
              "min-[50rem]:w-full min-[50rem]:max-w-[260px] min-[50rem]:border min-[50rem]:border-input min-[50rem]:bg-background min-[50rem]:pr-2 min-[50rem]:pl-3 min-[50rem]:[box-shadow:var(--oh-control-ring)_var(--oh-control-border)]",
              "min-[50rem]:hover:border-primary min-[50rem]:hover:text-foreground min-[50rem]:hover:[box-shadow:var(--oh-control-ring)_var(--accent)]",
              "min-[64rem]:max-[71.24rem]:w-10 min-[64rem]:max-[71.24rem]:justify-center min-[64rem]:max-[71.24rem]:p-0",
            )}
          >
            <SearchIcon aria-hidden="true" strokeWidth={2.25} className="size-[15px] shrink-0 text-primary" />
            <span aria-hidden="true" className="hidden min-[50rem]:block min-[64rem]:max-[71.24rem]:hidden">
              Search
            </span>
            <Kbd aria-hidden="true" className="ml-auto hidden min-[50rem]:inline-flex min-[64rem]:max-[71.24rem]:hidden">
              <span className="[:root[data-platform=mac]_&]:hidden">Ctrl</span>
              <span className="[:root:not([data-platform=mac])_&]:hidden">⌘</span>
              <span>K</span>
            </Kbd>
          </button>
        </DialogTrigger>
        <AnimatePresence>
          {open && (
            <DialogContent
              className={cn(
                "inset-0 rounded-none border-0",
                "min-[50rem]:inset-auto min-[50rem]:top-16 min-[50rem]:left-1/2 min-[50rem]:max-h-[min(640px,calc(100dvh-128px))] min-[50rem]:w-[min(640px,calc(100vw-32px))] min-[50rem]:-translate-x-1/2 min-[50rem]:rounded-md min-[50rem]:border",
              )}
              onCloseAutoFocus={(event) => {
                event.preventDefault();
                trigger.current?.focus({ preventScroll: true });
              }}
            >
              <DialogTitle className="sr-only">Search</DialogTitle>
              <DialogDescription className="sr-only">
                Search the docs, the specification, the drivers and the device library. Use the up and down arrow keys to move through the results and Enter to open one.
              </DialogDescription>
              <Command shouldFilter={false} loop vimBindings={false} label="Search" value={active} onValueChange={setActive} className="min-h-0 flex-1">
                <CommandInput
                  value={query}
                  onValueChange={setQuery}
                  onKeyDown={() => {
                    pointer.current = false;
                  }}
                  placeholder="Search the docs, spec, drivers and devices"
                >
                  <DialogClose className="h-9 shrink-0 cursor-pointer rounded-md px-2 text-sm font-semibold text-primary hover:bg-muted min-[50rem]:hidden">Cancel</DialogClose>
                </CommandInput>
                <CommandList>
                  {found.status === "loading" && <CommandLoading label="Searching">Searching</CommandLoading>}
                  {found.status === "error" && <CommandEmpty>Search could not load. Check your connection, then try again.</CommandEmpty>}
                  {found.status === "done" && !hits && (
                    <CommandEmpty>
                      No results for "{found.query}". Try a method such as <code className="font-mono text-foreground">hal/write</code> or an error code such as{" "}
                      <code className="font-mono text-foreground">LIMIT_EXCEEDED</code>.
                    </CommandEmpty>
                  )}
                  {found.status === "done" &&
                    found.groups.map((item) => (
                      <CommandGroup key={item.section} heading={item.section}>
                        {item.hits.map((hit) => (
                          <CommandItem key={hit.id} value={hit.id} asChild onSelect={() => go(hit.url, found.query)}>
                            <a
                              href={hit.url}
                              onPointerDown={() => {
                                pointer.current = true;
                              }}
                              className={cn(hit.heading && "ml-3 rounded-l-none border-l border-border pl-3")}
                            >
                              <span data-title="" className="flex min-w-0 items-center gap-1 font-semibold">
                                <Text parts={highlight(hit.heading ?? hit.title, found.query)} className="truncate" />
                                {hit.heading && <span className="sr-only">, in {hit.title}</span>}
                              </span>
                              {hit.excerpt && <Text parts={marked(hit.excerpt)} className="line-clamp-2 text-xs leading-normal text-muted-foreground" />}
                            </a>
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    ))}
                  {found.status === "idle" && (
                    <>
                      {recent.length > 0 && (
                        <CommandGroup heading="Recent searches">
                          {recent.map((term) => (
                            <CommandItem key={`recent ${term}`} value={`recent ${term}`} onSelect={() => setQuery(term)}>
                              <span data-title="" className="truncate">
                                {term}
                              </span>
                            </CommandItem>
                          ))}
                          <CommandItem value="recent clear" onSelect={() => setRecent(forget())}>
                            <span data-title="" className="text-muted-foreground">
                              Clear recent searches
                            </span>
                          </CommandItem>
                        </CommandGroup>
                      )}
                      <CommandGroup heading="Start here">
                        {suggestions.map((suggestion) => (
                          <CommandItem key={suggestion.href} value={`go ${suggestion.href}`} asChild onSelect={() => go(withBase(suggestion.href), "")}>
                            <a
                              href={withBase(suggestion.href)}
                              onPointerDown={() => {
                                pointer.current = true;
                              }}
                            >
                              <span data-title="" className="font-semibold">
                                {suggestion.label}
                              </span>
                            </a>
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </>
                  )}
                </CommandList>
              </Command>
              <div aria-hidden="true" className="hidden shrink-0 items-center gap-4 border-t border-border px-4 py-2.5 text-xs text-muted-foreground min-[50rem]:flex">
                <span className="flex items-center gap-1.5">
                  <Kbd>
                    <ArrowUp strokeWidth={2} />
                  </Kbd>
                  <Kbd>
                    <ArrowDown strokeWidth={2} />
                  </Kbd>
                  to move
                </span>
                <span className="flex items-center gap-1.5">
                  <Kbd>Enter</Kbd> to open
                </span>
                <span className="flex items-center gap-1.5">
                  <Kbd>Esc</Kbd> to close
                </span>
              </div>
              <p aria-live="polite" className="sr-only">
                {announce}
              </p>
            </DialogContent>
          )}
        </AnimatePresence>
      </Dialog>
    </MotionRoot>
  );
}
