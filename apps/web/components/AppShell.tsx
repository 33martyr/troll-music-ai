"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { NAV_MAIN, NAV_SETTINGS, NAV_WORKSHOP, type NavItem } from "@/lib/modules";

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <span className="flex h-9 w-9 items-end justify-center gap-[3px] rounded-xl bg-gradient-to-br from-grape to-grape-deep p-2 shadow-lg shadow-grape/30">
        {[0.5, 1, 0.7].map((height, index) => (
          <span key={index} className="w-1 rounded-full bg-volt" style={{ height: `${height * 100}%` }} />
        ))}
      </span>
      <span className="font-display text-[13px] font-extrabold leading-tight tracking-tight">
        TROLL
        <br />
        <span className="text-volt">MUSIC</span>·AI
      </span>
    </Link>
  );
}

function NavLink({ item, onNavigate, big }: { item: NavItem; onNavigate?: () => void; big?: boolean }) {
  const pathname = usePathname();
  const { href, label, icon: Icon } = item;
  const active = href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={`group flex items-center gap-3 rounded-lg px-3 transition-colors ${big ? "py-2.5 text-[15px] font-semibold" : "py-1.5 text-sm"} ${
        active ? "bg-grape/15 text-fg" : "text-muted hover:bg-white/5 hover:text-fg"
      }`}
    >
      <Icon size={big ? 18 : 16} className={active ? "text-volt" : "text-muted group-hover:text-fg"} />
      <span className="flex-1">{label}</span>
    </Link>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-6">
      <div className="flex flex-col gap-0.5">
        {NAV_MAIN.map((item) => (
          <NavLink key={item.href} item={item} onNavigate={onNavigate} big />
        ))}
      </div>
      <div className="flex flex-col gap-0.5">
        <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-widest text-muted/70">Workshop</p>
        {NAV_WORKSHOP.map((item) => (
          <NavLink key={item.href} item={item} onNavigate={onNavigate} />
        ))}
      </div>
      <div className="flex flex-col gap-0.5">
        <NavLink item={NAV_SETTINGS} onNavigate={onNavigate} />
      </div>
    </nav>
  );
}

function SidebarFooter() {
  return (
    <p className="px-3 text-xs leading-relaxed text-muted">
      Roast it. Rap it. Release it.
      <br />
      Roast what they did, not who they are.
    </p>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="lg:pl-64">
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col gap-8 border-r border-line bg-panel/70 px-4 py-6 backdrop-blur lg:flex">
        <div className="px-2">
          <Logo />
        </div>
        <div className="flex-1 overflow-y-auto">
          <NavLinks />
        </div>
        <SidebarFooter />
      </aside>

      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-ink/85 px-4 py-3 backdrop-blur lg:hidden">
        <Logo />
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          className="rounded-lg border border-line p-2 text-fg"
        >
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
      </header>
      {open && (
        <div className="fixed inset-x-0 bottom-0 top-[61px] z-20 flex flex-col gap-6 overflow-y-auto bg-ink px-4 py-5 lg:hidden">
          <NavLinks onNavigate={() => setOpen(false)} />
          <SidebarFooter />
        </div>
      )}

      <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-8 lg:py-12">{children}</main>
    </div>
  );
}
