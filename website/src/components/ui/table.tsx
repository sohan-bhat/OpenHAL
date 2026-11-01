import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * shadcn/ui's Table set as the site's datasheet tables: body text, headers in bold secondary text
 * over a rule in that color, 1 px rules between rows and no fills, with a selected row on the surface.
 */
function Table({ className, containerClassName, ...props }: React.ComponentProps<"table"> & { containerClassName?: string }) {
  return (
    <div data-slot="table-container" className={cn("relative w-full overflow-x-auto", containerClassName)}>
      <table data-slot="table" className={cn("w-full border-collapse text-base leading-normal", className)} {...props} />
    </div>
  );
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return <thead data-slot="table-header" className={className} {...props} />;
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return <tbody data-slot="table-body" className={className} {...props} />;
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return <tfoot data-slot="table-footer" className={cn("border-t border-border font-bold", className)} {...props} />;
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return <tr data-slot="table-row" className={cn("data-[state=selected]:bg-muted", className)} {...props} />;
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "border-b border-muted-foreground py-2 pr-3 pl-0 text-left align-bottom text-sm font-bold text-muted-foreground [&[scope=row]]:border-border [&[scope=row]]:align-baseline",
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return <td data-slot="table-cell" className={cn("border-b border-border py-2 pr-3 pl-0 align-top [th[scope=row]~&]:align-baseline", className)} {...props} />;
}

function TableCaption({ className, ...props }: React.ComponentProps<"caption">) {
  return <caption data-slot="table-caption" className={cn("pb-2 text-left text-sm text-muted-foreground", className)} {...props} />;
}

export { Table, TableHeader, TableBody, TableFooter, TableHead, TableRow, TableCell, TableCaption };
