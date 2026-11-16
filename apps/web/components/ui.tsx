import { Loader2 } from "lucide-react";
import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-volt text-ink font-semibold hover:brightness-110 shadow-[0_0_24px_-6px] shadow-volt/50",
  secondary: "border border-line bg-raised text-fg hover:border-grape/60 hover:bg-grape/10",
  ghost: "text-muted hover:bg-white/5 hover:text-fg",
  danger: "border border-danger/40 text-danger hover:bg-danger/10",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "sm" | "md";
  busy?: boolean;
}

const buttonClass = (variant: Variant, size: "sm" | "md", className: string) =>
  `inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg transition disabled:cursor-not-allowed disabled:opacity-50 ${
    size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-4 py-2.5 text-sm"
  } ${VARIANTS[variant]} ${className}`;

export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  className = "",
  children,
}: {
  href: string;
  variant?: Variant;
  size?: "sm" | "md";
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={buttonClass(variant, size, className)}>
      {children}
    </Link>
  );
}

export function Button({ variant = "secondary", size = "md", busy, className = "", children, ...props }: ButtonProps) {
  return (
    <button type="button" {...props} disabled={props.disabled || busy} className={buttonClass(variant, size, className)}>
      {busy && <Loader2 size={14} className="animate-spin" />}
      {children}
    </button>
  );
}

const TONES = {
  neutral: "border-line text-muted",
  live: "border-volt/40 bg-volt/10 text-volt",
  planned: "border-line bg-white/5 text-muted",
  mock: "border-amber/50 bg-amber/10 text-amber",
  grape: "border-grape/40 bg-grape/10 text-grape",
  danger: "border-danger/40 bg-danger/10 text-danger",
};

export function Badge({ tone = "neutral", children }: { tone?: keyof typeof TONES; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`rounded-2xl border border-line bg-panel/80 ${className}`}>{children}</div>;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-baseline justify-between text-xs font-medium text-muted">
        {label}
        {hint && <span className="font-normal opacity-70">{hint}</span>}
      </span>
      {children}
    </label>
  );
}

export function PageHeader({
  eyebrow,
  title,
  children,
  actions,
}: {
  eyebrow?: string;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        {eyebrow && <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-grape">{eyebrow}</p>}
        <h1 className="font-display text-2xl font-extrabold tracking-tight sm:text-3xl">{title}</h1>
        {children && <p className="mt-2 text-sm leading-relaxed text-muted">{children}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Notice({ tone = "danger", children }: { tone?: "danger" | "mock" | "info"; children: ReactNode }) {
  const styles = {
    danger: "border-danger/40 bg-danger/10 text-danger",
    mock: "border-amber/40 bg-amber/10 text-amber",
    info: "border-grape/40 bg-grape/10 text-fg",
  };
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={`rounded-xl border px-4 py-3 text-sm ${styles[tone]}`}>
      {children}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-line px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mx-auto mt-1.5 max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Equalizer({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex h-4 items-end gap-[3px] ${className}`} aria-hidden>
      {[0, 0.2, 0.4, 0.1].map((delay) => (
        <span key={delay} className="eq-bar h-full w-[3px] rounded-full bg-volt" style={{ animationDelay: `${delay}s` }} />
      ))}
    </span>
  );
}
