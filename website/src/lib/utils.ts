import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Joins class names the way shadcn/ui does, letting a later Tailwind class win over an earlier one. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
