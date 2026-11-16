"use client";

import { ArrowRight, ChevronRight, FolderOpen, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ProviderBanner, useTextProvider } from "@/components/ProviderBanner";
import { Badge, Button, ButtonLink, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { formatWhen, useLoad } from "@/lib/hooks";
import { GENERATORS, PIPELINE } from "@/lib/modules";
import type { Capability } from "@/lib/types";

function CapabilityBadge({ capability }: { capability: Capability | undefined }) {
  if (!capability) return null;
  if (!capability.configured) return <Badge tone="danger">Needs setup</Badge>;
  if (capability.is_mock) return <Badge tone="mock">Mock</Badge>;
  return capability.is_ai ? <Badge tone="grape">AI</Badge> : <Badge tone="live">Built-in</Badge>;
}

const IDEAS = [
  "My flatmate who 'forgets' to buy toilet paper",
  "A crypto guru who lives with his mum",
  "The printer that only breaks before deadlines",
];

export default function StudioPage() {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const provider = useTextProvider();
  const projects = useLoad(api.projects);
  const capabilities = useLoad(api.capabilities);

  const start = (text: string) => router.push(`/lyrics?prompt=${encodeURIComponent(text.trim())}`);

  return (
    <div className="space-y-14">
      <section className="rise">
        <p className="mb-4 text-xs font-semibold uppercase tracking-[0.25em] text-grape">
          Open-source AI music studio
        </p>
        <h1 className="font-display text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-6xl">
          TURN ANY ROAST
          <br />
          INTO A <span className="text-gradient">BANGER.</span>
        </h1>
        <p className="mt-5 max-w-xl text-lg text-muted">
          Generate lyrics, beats, songs and music videos with AI.
        </p>

        <form
          className="mt-8 flex max-w-2xl flex-col gap-2 rounded-2xl border border-line bg-panel/80 p-2 shadow-2xl shadow-grape/10 focus-within:border-grape/60 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (prompt.trim().length >= 3) start(prompt);
          }}
        >
          <input
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="What are we roasting today?"
            aria-label="Song idea"
            className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-base outline-none placeholder:text-muted/60"
          />
          <Button type="submit" variant="primary" disabled={prompt.trim().length < 3}>
            <Sparkles size={16} /> Write the lyrics
          </Button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {IDEAS.map((idea) => (
            <button
              key={idea}
              type="button"
              onClick={() => start(idea)}
              className="rounded-full border border-line px-3 py-1 text-xs text-muted transition hover:border-grape/60 hover:text-fg"
            >
              {idea}
            </button>
          ))}
        </div>
      </section>

      <ProviderBanner {...provider} />

      <section>
        <div className="mb-5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 className="font-display text-lg font-semibold">Make one thing</h2>
          <p className="text-sm text-muted">Every module stands alone. No wizard.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {GENERATORS.map((module, index) => {
            const Icon = module.icon;
            return (
              <Link
                key={module.href}
                href={module.href}
                style={{ animationDelay: `${index * 50}ms` }}
                className="rise group relative overflow-hidden rounded-2xl border border-line bg-panel/80 p-5 transition duration-200 hover:-translate-y-0.5 hover:border-grape/60 hover:shadow-xl hover:shadow-grape/10"
              >
                <span className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-grape/20 opacity-0 blur-2xl transition group-hover:opacity-100" />
                <div className="mb-5 flex items-start justify-between">
                  <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-grape to-grape-deep text-white">
                    <Icon size={20} />
                  </span>
                  <CapabilityBadge capability={capabilities.data?.find((c) => c.kind === module.provider)} />
                </div>
                <h3 className="flex items-center gap-1 font-semibold">
                  {module.title}
                  <ArrowRight size={15} className="-translate-x-1 opacity-0 transition group-hover:translate-x-0 group-hover:opacity-100" />
                </h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{module.blurb}</p>
              </Link>
            );
          })}
        </div>
      </section>

      <section>
        <div className="mb-5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 className="font-display text-lg font-semibold">Or the whole production</h2>
          <p className="text-sm text-muted">Skip, redo or reuse any stage.</p>
        </div>
        <Card className="overflow-x-auto p-5">
          <ol className="flex min-w-max items-center gap-2">
            {PIPELINE.map((stage, index) => (
              <li key={stage.label} className="flex items-center gap-2">
                <Link href={stage.href} className="rounded-xl border border-volt/40 bg-volt/5 px-4 py-2.5 transition hover:border-volt">
                  <p className="font-display text-xs font-semibold uppercase">{stage.label}</p>
                </Link>
                {index < PIPELINE.length - 1 && <ChevronRight size={16} className="text-line" />}
              </li>
            ))}
          </ol>
          <p className="mt-4 text-sm text-muted">
            Every stage produces a real file you can play and download. What does the work at each stage is shown on
            its page and chosen in Model Settings.
          </p>
        </Card>
      </section>

      <section>
        <div className="mb-5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 className="font-display text-lg font-semibold">Recent projects</h2>
          <Link href="/projects" className="text-sm text-muted hover:text-fg">
            All projects →
          </Link>
        </div>
        {projects.data && projects.data.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {projects.data.slice(0, 3).map((project) => (
              <Link
                key={project.id}
                href={`/projects/${project.id}`}
                className="rounded-2xl border border-line bg-panel/80 p-5 transition hover:border-grape/60"
              >
                <p className="flex items-center gap-2 font-semibold">
                  <FolderOpen size={16} className="text-grape" /> {project.name}
                </p>
                <p className="mt-2 text-xs text-muted">
                  {Object.entries(project.asset_counts).map(([kind, n]) => `${n} ${kind}`).join(" · ") || "Empty"} · updated{" "}
                  {formatWhen(project.updated_at)}
                </p>
              </Link>
            ))}
          </div>
        ) : (
          <Card className="flex flex-wrap items-center justify-between gap-4 p-5">
            <p className="text-sm text-muted">
              {projects.loading
                ? "Loading projects…"
                : projects.error
                  ? "Projects are unavailable while the backend is offline."
                  : "No projects yet. A project keeps a song's lyrics, beats and videos together."}
            </p>
            <ButtonLink href="/projects">New project</ButtonLink>
          </Card>
        )}
      </section>
    </div>
  );
}
