import {
  Clapperboard,
  Drum,
  Flame,
  FolderOpen,
  Image as ImageIcon,
  type LucideIcon,
  Mic,
  Music,
  PenLine,
  Settings,
  Swords,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** The product: one button on the home page, and everything you made. */
export const NAV_MAIN: NavItem[] = [
  { href: "/", label: "Roast Someone", icon: Flame },
  { href: "/projects", label: "My Trolls", icon: FolderOpen },
];

/** Tweak one part of a troll by hand. Optional; the home page does all of this in one go. */
export const NAV_WORKSHOP: NavItem[] = [
  { href: "/lyrics", label: "Lyrics Editor", icon: PenLine },
  { href: "/battles", label: "Battle Builder", icon: Swords },
  { href: "/beat", label: "Beat Maker", icon: Drum },
  { href: "/song", label: "Song Mixer", icon: Music },
  { href: "/voice", label: "Voices", icon: Mic },
  { href: "/video", label: "Video Maker", icon: Clapperboard },
  { href: "/artwork", label: "Cover Maker", icon: ImageIcon },
];

export const NAV_SETTINGS: NavItem = { href: "/settings", label: "AI Settings", icon: Settings };
