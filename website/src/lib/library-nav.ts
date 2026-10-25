import { libraryEntries } from "./library";
import type { SideGroup } from "./nav-types";

export function librarySidebar(): SideGroup[] {
  return [
    {
      name: "",
      items: [
        { title: "All device files", href: "/library/" },
        { title: "How the library works", href: "/docs/library/" },
        { title: "Add a device", href: "/docs/tutorials/add-a-device/" },
      ],
    },
    { name: "Device files", items: libraryEntries().map((entry) => ({ title: entry.title, href: `/library/${entry.slug}/` })) },
  ].filter((group) => group.items.length > 0);
}
