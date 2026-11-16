import {
  Clapperboard,
  Drum,
  FolderOpen,
  Image as ImageIcon,
  LayoutDashboard,
  type LucideIcon,
  Mic,
  Music,
  PenLine,
  Settings,
  Swords,
} from "lucide-react";

export interface StudioModule {
  href: string;
  nav: string;
  title: string;
  blurb: string;
  icon: LucideIcon;
  /** Which provider kind does the creative work, shown as "powered by". */
  provider: "text" | "music" | "voice" | "image";
}

export const GENERATORS: StudioModule[] = [
  {
    href: "/lyrics",
    nav: "Generate Lyrics",
    title: "Generate Lyrics",
    blurb: "Describe the roast. Get a full song: verses, chorus, BPM and beat notes.",
    icon: PenLine,
    provider: "text",
  },
  {
    href: "/beat",
    nav: "Generate Beat",
    title: "Generate Beat",
    blurb: "Instrumentals on their own: pick a genre, BPM and mood, or upload yours.",
    icon: Drum,
    provider: "music",
  },
  {
    href: "/song",
    nav: "Generate Song",
    title: "Generate Song",
    blurb: "Lyrics, beat and vocals mixed into one track. Redo any part on its own.",
    icon: Music,
    provider: "voice",
  },
  {
    href: "/video",
    nav: "Generate Music Video",
    title: "Generate Music Video",
    blurb: "Storyboard, scene images and synced lyrics rendered into an MP4.",
    icon: Clapperboard,
    provider: "image",
  },
  {
    href: "/voice",
    nav: "My Voice",
    title: "Voices",
    blurb: "Try the available voices, or add an authorized voice profile with consent.",
    icon: Mic,
    provider: "voice",
  },
  {
    href: "/battles",
    nav: "Rap Battles",
    title: "Create Rap Battle",
    blurb: "Two fictional rivals, alternating verses, two voices.",
    icon: Swords,
    provider: "text",
  },
  {
    href: "/artwork",
    nav: "Cover Art",
    title: "Generate Cover Art",
    blurb: "A square cover for your track, from its title, genre and style.",
    icon: ImageIcon,
    provider: "image",
  },
];

export const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Studio", icon: LayoutDashboard },
  ...GENERATORS.map((m) => ({ href: m.href, label: m.nav, icon: m.icon })),
  { href: "/projects", label: "My Projects", icon: FolderOpen },
  { href: "/settings", label: "Model Settings", icon: Settings },
];

export const PIPELINE: { label: string; href: string }[] = [
  { label: "Lyrics", href: "/lyrics" },
  { label: "Beat", href: "/beat" },
  { label: "Vocals", href: "/voice" },
  { label: "Song", href: "/song" },
  { label: "Video", href: "/video" },
  { label: "Cover", href: "/artwork" },
];
