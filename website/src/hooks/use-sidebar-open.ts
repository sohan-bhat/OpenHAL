import * as React from "react";
import { isCollapsed, watchSidebar } from "@/lib/sidebar";

const shown = () => !isCollapsed();
const server = () => true;

/**
 * Whether the documentation sidebar is shown, read from the root that every control marks, so every
 * island that shows the sidebar's state agrees whichever loads first. The server renders it shown,
 * and the page's scripts put the stored choice in place before the first paint.
 */
export function useSidebarOpen(): boolean {
  return React.useSyncExternalStore(watchSidebar, shown, server);
}
