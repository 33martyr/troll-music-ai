"use client";

import { Copy, Download, Factory, FolderOpen, Plus, Search, Swords, Trash2 } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { TrackPlayer } from "@/components/player";
import { KINDS } from "@/components/troll";
import { Badge, Button, ButtonLink, Card, Empty, Field, Notice, PageHeader } from "@/components/ui";
import { api, download, errorMessage, fileUrl } from "@/lib/api";
import { formatWhen, useLoad } from "@/lib/hooks";
import type { Asset, Project, TrollKind } from "@/lib/types";

const KIND_PLURALS: Record<string, [string, string]> = {
  song: ["song", "songs"],
  beat: ["beat", "beats"],
  video: ["video", "videos"],
  artwork: ["image", "images"],
  lyrics: ["lyric sheet", "lyric sheets"],
  vocals: ["vocal take", "vocal takes"],
  scorecard: ["scorecard", "scorecards"],
};

/** "2 songs · 1 video · 3 images", most interesting first; storyboards are internal. */
function summary(counts: Record<string, number>): string {
  const order = ["song", "video", "beat", "artwork", "lyrics", "vocals", "scorecard"];
  const parts = order
    .filter((kind) => counts[kind])
    .map((kind) => `${counts[kind]} ${KIND_PLURALS[kind][counts[kind] === 1 ? 0 : 1]}`);
  return parts.join(" · ") || "Empty";
}

type Sort = "new" | "old" | "az";

function TrollCard({ track, cover }: { track: Asset; cover: Asset | null }) {
  const troll = track.meta!.troll!;
  const kind = KINDS.find((k) => k.id === troll.kind);
  return (
    <article className="flex flex-col overflow-hidden rounded-2xl border border-line bg-panel/80 transition hover:border-grape/50">
      <div className="flex gap-3 p-3">
        {cover?.has_file ? (
          // eslint-disable-next-line @next/next/no-img-element -- served by the API with a signed URL
          <img src={fileUrl(cover)} alt="" loading="lazy" className="h-24 w-24 shrink-0 rounded-xl object-cover" />
        ) : (
          <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-xl bg-grape/15 text-4xl" aria-hidden>
            {kind?.emoji ?? "🎤"}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 font-display text-sm font-bold leading-snug">{track.title}</p>
          <p className="mt-0.5 truncate text-xs text-muted">
            {troll.artist} · starring {troll.target}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-1">
            <Badge>{kind?.label ?? troll.label}</Badge>
            {track.is_mock && <Badge tone="mock">Mock words</Badge>}
            <span className="text-[11px] text-muted">{formatWhen(track.created_at)}</span>
          </div>
        </div>
      </div>
      {track.has_file && (
        <div className="px-3">
          <TrackPlayer src={fileUrl(track)} label={track.title} knownDuration={track.duration_seconds} lazy compact />
        </div>
      )}
      <div className="mt-auto flex flex-wrap items-center gap-1.5 p-3">
        <ButtonLink size="sm" href={`/?track=${track.id}`} variant="primary">
          Open
        </ButtonLink>
        {track.project_id && (
          <ButtonLink size="sm" href={`/projects/${track.project_id}`}>
            <FolderOpen size={12} /> Files
          </ButtonLink>
        )}
        <ButtonLink size="sm" href={`/factory?asset=${track.id}`}>
          <Factory size={12} /> Memes
        </ButtonLink>
        {troll.kind === "rap_battle" && (
          <ButtonLink size="sm" href={`/battle?id=${track.id}`}>
            <Swords size={12} /> Judges
          </ButtonLink>
        )}
        {track.has_file && (
          <a href={fileUrl(track, true)} className="ml-auto inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-muted hover:bg-white/5 hover:text-fg">
            <Download size={12} /> MP3
          </a>
        )}
      </div>
    </article>
  );
}

export default function MyTrollsPage() {
  const projects = useLoad(api.projects);
  const tracks = useLoad(() => api.assets("kind=song,beat&limit=200"));
  const covers = useLoad(() => api.assets("kind=artwork&limit=200"));
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<TrollKind | "all">("all");
  const [sort, setSort] = useState<Sort>("new");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const coverById = useMemo(() => new Map((covers.data ?? []).map((a) => [a.id, a])), [covers.data]);
  const trolls = useMemo(() => {
    const words = query.trim().toLowerCase();
    const list = (tracks.data ?? []).filter((t) => {
      const troll = t.meta?.troll;
      if (!troll || (kind !== "all" && troll.kind !== kind)) return false;
      return !words || [t.title, troll.target, troll.artist, troll.request?.situation ?? ""].join(" ").toLowerCase().includes(words);
    });
    return list.sort((a, b) =>
      sort === "az" ? a.title.localeCompare(b.title) : (sort === "new" ? -1 : 1) * a.created_at.localeCompare(b.created_at),
    );
  }, [tracks.data, query, kind, sort]);
  const kindsPresent = new Set((tracks.data ?? []).map((t) => t.meta?.troll?.kind).filter(Boolean));

  async function act(tag: string, action: () => Promise<unknown>) {
    setBusy(tag);
    setError(null);
    try {
      await action();
      projects.reload();
      tracks.reload();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  }

  const remove = (project: Project) => {
    const count = Object.values(project.asset_counts).reduce((a, b) => a + b, 0);
    if (confirm(`Delete “${project.name}” and its ${count} file(s)? This can't be undone.`)) {
      act(`delete:${project.id}`, () => api.deleteProject(project.id));
    }
  };

  return (
    <>
      <PageHeader eyebrow="Your hall of shame" title="My Trolls">
        Every roast you&apos;ve made, ready to replay, re-share or turn into memes. Projects keep each one&apos;s lyrics, beat, vocals,
        cover and videos together.
      </PageHeader>

      {(error || projects.error || tracks.error) && (
        <div className="mb-6">
          <Notice>{error ?? projects.error ?? tracks.error}</Notice>
        </div>
      )}

      <section className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative min-w-0 flex-1 basis-56">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              className="control !pl-9"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by title, target or rapper"
              aria-label="Search your trolls"
            />
          </label>
          <select className="control !w-auto" value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort">
            <option value="new">Newest first</option>
            <option value="old">Oldest first</option>
            <option value="az">A to Z</option>
          </select>
        </div>
        {kindsPresent.size > 1 && (
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by type">
            {[{ id: "all" as const, emoji: "✨", label: "Everything" }, ...KINDS.filter((k) => kindsPresent.has(k.id))].map((k) => (
              <button
                key={k.id}
                type="button"
                aria-pressed={kind === k.id}
                onClick={() => setKind(k.id)}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${kind === k.id ? "border-volt bg-volt text-ink" : "border-line hover:border-grape/60"}`}
              >
                {k.emoji} {k.label}
              </button>
            ))}
          </div>
        )}

        {tracks.loading && !tracks.data && <p className="text-sm text-muted">Loading your hall of shame…</p>}
        {tracks.data && !tracks.data.some((t) => t.meta?.troll) && (
          <Empty title="Nobody has been roasted yet">
            <p>Somebody out there is getting away with it.</p>
            <ButtonLink href="/" variant="primary" className="mt-4">Roast someone</ButtonLink>
          </Empty>
        )}
        {tracks.data && tracks.data.some((t) => t.meta?.troll) && !trolls.length && (
          <p className="text-sm text-muted">Nothing matches. Try another search.</p>
        )}
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {trolls.map((track) => (
            <TrollCard key={track.id} track={track} cover={coverById.get(track.meta?.troll?.cover_asset_id ?? "") ?? null} />
          ))}
        </div>
      </section>

      <section className="mt-14 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-lg font-black uppercase tracking-tight">Projects</h2>
          <Button size="sm" onClick={() => setCreating(!creating)} aria-expanded={creating}>
            <Plus size={13} /> New project
          </Button>
        </div>
        {creating && (
          <Card className="p-4">
            <form
              className="grid gap-3 sm:grid-cols-[1fr_1.5fr_auto] sm:items-end"
              onSubmit={(event) => {
                event.preventDefault();
                act("create", async () => {
                  await api.createProject(name, description);
                  setName("");
                  setDescription("");
                  setCreating(false);
                });
              }}
            >
              <Field label="Name">
                <input className="control" value={name} onChange={(e) => setName(e.target.value)} placeholder="Diss Tape Vol. 1" maxLength={120} required />
              </Field>
              <Field label="Description" hint="optional">
                <input className="control" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What's this collection about?" maxLength={2000} />
              </Field>
              <Button type="submit" variant="primary" busy={busy === "create"} disabled={!name.trim()}>
                Create
              </Button>
            </form>
          </Card>
        )}
        {projects.data?.length === 0 && <p className="text-sm text-muted">No projects yet. Every roast creates one automatically.</p>}
        <div className="grid gap-3 md:grid-cols-2">
          {projects.data?.map((project) => (
            <Card key={project.id} className="flex min-w-0 flex-col p-4 transition hover:border-grape/50">
              <Link href={`/projects/${project.id}`} className="group min-w-0 flex-1">
                <p className="flex items-center gap-2 font-semibold group-hover:text-volt">
                  <FolderOpen size={16} className="shrink-0 text-grape" /> <span className="truncate">{project.name}</span>
                </p>
                {project.description && <p className="mt-1 line-clamp-2 text-sm text-muted">{project.description}</p>}
                <p className="mt-2 text-xs text-muted">
                  {summary(project.asset_counts)} · updated {formatWhen(project.updated_at)}
                </p>
              </Link>
              <div className="mt-3 flex flex-wrap gap-2 border-t border-line pt-3">
                <Button size="sm" busy={busy === `dup:${project.id}`} onClick={() => act(`dup:${project.id}`, () => api.duplicateProject(project.id))}>
                  <Copy size={13} /> Duplicate
                </Button>
                <Button size="sm" busy={busy === `exp:${project.id}`} onClick={() => act(`exp:${project.id}`, () => download(`/api/projects/${project.id}/export`, "project.zip"))}>
                  <Download size={13} /> Download all (ZIP)
                </Button>
                <Button size="sm" variant="danger" className="ml-auto" busy={busy === `delete:${project.id}`} onClick={() => remove(project)}>
                  <Trash2 size={13} /> Delete
                </Button>
              </div>
            </Card>
          ))}
        </div>
      </section>
    </>
  );
}
