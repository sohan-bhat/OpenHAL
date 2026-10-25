import type { SideGroup } from "./nav-types";

export function sdkSidebar(): SideGroup[] {
  return [
    { name: "", items: [{ title: "Overview", href: "/sdks/" }] },
    {
      name: "Python",
      items: [
        { title: "Guide", href: "/sdks/python/" },
        { title: "API reference", href: "/sdks/python/reference/" },
      ],
    },
    { name: "TypeScript", items: [{ title: "Planned", href: "/sdks/typescript/" }] },
  ];
}
