import * as React from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SEARCH, applyChoices, keepInAddress, readChoices, type Choices } from "@/lib/catalog-filter";
import { cn } from "@/lib/utils";
import { useIslandReady } from "./ready";

/** The value of a select's first row, Any, which Radix needs as a word because an empty value clears the select. */
const ANY = "any";

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterSelect {
  name: string;
  label: string;
  options: FilterOption[];
}

interface Props {
  /** The search landmark's name, such as "Filter drivers". */
  label: string;
  placeholder: string;
  selects?: FilterSelect[];
}

/**
 * The filters over a catalog table, the Drivers page and the Device Library, on shadcn/ui's Input,
 * Label and Select (Radix). Each choice shows and hides the server-rendered rows, updates the count
 * line and stays in the address bar, so a filtered view can be shared.
 */
export default function CatalogFilters({ label, placeholder, selects = [] }: Props) {
  const id = React.useId();
  const form = React.useRef<HTMLFormElement>(null);
  const search = React.useRef<HTMLInputElement>(null);
  const fields = React.useMemo(() => [SEARCH, ...selects.map((select) => select.name)], [selects]);
  const [choices, setChoices] = React.useState<Choices>({});
  const [ready, setReady] = React.useState(false);
  useIslandReady(form);

  React.useEffect(() => {
    const start = readChoices(window.location.search, fields);
    const typed = search.current?.value.trim();
    if (typed) start[SEARCH] = typed;
    else if (start[SEARCH] && search.current) search.current.value = start[SEARCH];
    setChoices(start);
    setReady(true);
  }, [fields]);

  React.useEffect(() => {
    if (!ready) return;
    applyChoices(choices);
    keepInAddress(choices, fields);
  }, [choices, fields, ready]);

  const choose = (field: string, value: string) => setChoices((now) => ({ ...now, [field]: value === ANY ? "" : value }));

  return (
    <form ref={form} role="search" aria-label={label} data-filters className={cn("grid gap-3", selects.length > 0 ? "md:grid-cols-[2fr_repeat(var(--selects),minmax(0,1fr))]" : "max-w-[420px]")}
      style={{ "--selects": selects.length } as React.CSSProperties}
      onSubmit={(event) => event.preventDefault()}>
      <div className="grid content-start gap-1">
        <Label htmlFor={`${id}-${SEARCH}`}>Filter</Label>
        <Input ref={search} id={`${id}-${SEARCH}`} type="search" name={SEARCH} placeholder={placeholder} autoComplete="off" onChange={(event) => choose(SEARCH, event.currentTarget.value)} />
      </div>
      {selects.map((select) => {
        const value = choices[select.name] || ANY;
        const shown = select.options.find((option) => option.value === value)?.label ?? "Any";
        return (
          <div key={select.name} className="grid content-start gap-1">
            <Label htmlFor={`${id}-${select.name}`}>{select.label}</Label>
            <Select name={select.name} value={value} onValueChange={(next) => choose(select.name, next)}>
              <SelectTrigger id={`${id}-${select.name}`} data-filter={select.name}>
                <SelectValue>{shown}</SelectValue>
              </SelectTrigger>
              <SelectContent aria-label={select.label}>
                <SelectItem value={ANY}>Any</SelectItem>
                {select.options.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        );
      })}
    </form>
  );
}
