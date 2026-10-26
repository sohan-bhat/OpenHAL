import { type Driver, deviceDrivers, referenceDrivers } from "./catalog";
import type { SideGroup } from "./nav-types";

const link = (driver: Driver) => ({ title: driver.name, href: `/drivers/${driver.name}/` });

export function driversSidebar(): SideGroup[] {
  const devices = deviceDrivers();
  return [
    {
      name: "",
      items: [
        { title: "All drivers", href: "/drivers/" },
        { title: "Coverage plan", href: "/drivers/coverage/" },
        { title: "Build a driver", href: "/docs/tutorials/build-a-driver/" },
      ],
    },
    { name: "Verified on hardware", items: devices.filter((driver) => driver.status === "verified").map(link) },
    { name: "Tested on simulator", items: devices.filter((driver) => driver.status !== "planned" && driver.status !== "verified").map(link) },
    { name: "Planned", items: devices.filter((driver) => driver.status === "planned").map(link) },
    { name: "Reference driver", items: referenceDrivers().map(link) },
  ].filter((group) => group.items.length > 0);
}
