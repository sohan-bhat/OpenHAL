export interface SideItem {
  title: string;
  href: string;
  number?: string;
  depth?: number;
}

export interface SideGroup {
  name: string;
  items: SideItem[];
}
