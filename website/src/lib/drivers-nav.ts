import { drivers, statusWord } from "./catalog";
import type { SideGroup } from "./nav-types";

export function driversSidebar(): SideGroup[] {
  const all = drivers();
  const running = all.filter((driver) => driver.status !== "planned");
  const planned = all.filter((driver) => driver.status === "planned");
  return [
    {
      name: "",
      items: [
        { title: "All drivers", href: "/drivers/" },
        { title: "Coverage plan", href: "/drivers/coverage/" },
        { title: "Writing a driver", href: "/docs/tutorials/write-a-driver/" },
      ],
    },
    { name: statusWord("implemented"), items: running.map((driver) => ({ title: driver.name, href: `/drivers/${driver.name}/` })) },
    { name: "Planned", items: planned.map((driver) => ({ title: driver.name, href: `/drivers/${driver.name}/` })) },
  ];
}
