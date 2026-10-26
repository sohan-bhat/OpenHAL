export interface SideItem {
  title: string;
  href?: string;
  number?: string;
  depth?: number;
  summary?: string;
}

export interface SideGroup {
  name: string;
  items: SideItem[];
}
