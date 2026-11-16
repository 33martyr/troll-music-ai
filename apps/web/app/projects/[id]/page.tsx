"use client";

import { ArrowLeft, Check, Copy, Download, PenLine, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Button, ButtonLink, Card, Empty, Notice } from "@/components/ui";
import { api, download, errorMessage } from "@/lib/api";
import { formatWhen, humanize, useLoad } from "@/lib/hooks";
import { MediaCard } from "@/components/studio";

const JOB_TONE = { completed: "live", failed: "danger", processing: "grape", queued: "neutral", cancelled: "neutral" } as const;

const MEDIA_SECTIONS = [
  { kinds: ["song"], title: "Songs", href: "/song", cta: "New song" },
  { kinds: ["beat"], title: "Beats", href: "/beat", cta: "New beat" },
  { kinds: ["vocals"], title: "Vocals", href: "/voice", cta: "New vocals" },
  { kinds: ["video"], title: "Videos", href: "/video", cta: "New video" },
  { kinds: ["artwork"], title: "Artwork", href: "/artwork", cta: "New cover" },
];

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const project = useLoad(() => api.project(id), id);
  const assets = useLoad(() => api.projectAssets(id), id);
  const jobs = useLoad(() => api.projectJobs(id), id);
  const [edit, setEdit] = useState<{ name: string; description: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(tag: string, action: () => Promise<unknown>) {
    setBusy(tag);
    setError(null);
    try {
      await action();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  }

  if (project.error && !project.data) {
    return (
      <div className="space-y-4">
        <Notice>{project.error}</Notice>
        <ButtonLink href="/projects"><ArrowLeft size={15} /> Back to projects</ButtonLink>
      </div>
    );
  }
  if (!project.data) return <p className="text-sm text-muted">Loading project…</p>;

  const data = project.data;
  const lyrics = assets.data?.filter((a) => a.kind === "lyrics") ?? [];

  return (
    <>
      <Link href="/projects" className="mb-5 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={14} /> My Projects
      </Link>

      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        {edit ? (
          <form
            className="w-full max-w-xl space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              act("save", async () => {
                await api.updateProject(id, edit);
                setEdit(null);
                project.reload();
              });
            }}
          >
            <input aria-label="Project name" className="control font-display !text-xl font-extrabold" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} maxLength={120} required autoFocus />
            <textarea aria-label="Description" className="control" value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} placeholder="Description" maxLength={2000} rows={2} />
            <div className="flex gap-2">
              <Button type="submit" variant="primary" size="sm" busy={busy === "save"} disabled={!edit.name.trim()}>Save</Button>
              <Button size="sm" variant="ghost" onClick={() => setEdit(null)}>Cancel</Button>
            </div>
          </form>
        ) : (
          <div className="max-w-2xl">
            <h1 className="font-display text-2xl font-extrabold tracking-tight sm:text-3xl">{data.name}</h1>
            <p className="mt-2 text-sm text-muted">{data.description || "No description."}</p>
            <p className="mt-2 text-xs text-muted">Created {formatWhen(data.created_at)} · updated {formatWhen(data.updated_at)}</p>
          </div>
        )}
        {!edit && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setEdit({ name: data.name, description: data.description })}>
              <PenLine size={13} /> Rename
            </Button>
            <Button size="sm" busy={busy === "dup"} onClick={() => act("dup", async () => router.push(`/projects/${(await api.duplicateProject(id)).id}`))}>
              <Copy size={13} /> Duplicate
            </Button>
            <Button size="sm" busy={busy === "export"} onClick={() => act("export", () => download(`/api/projects/${id}/export`, "project.zip"))}>
              <Download size={13} /> Export bundle
            </Button>
            <Button
              size="sm"
              variant="danger"
              busy={busy === "delete"}
              onClick={() => {
                if (!confirm(`Delete “${data.name}” and everything in it? This can't be undone.`)) return;
                act("delete", async () => {
                  await api.deleteProject(id);
                  router.push("/projects");
                });
              }}
            >
              <Trash2 size={13} /> Delete
            </Button>
          </div>
        )}
      </header>

      {error && <div className="mb-6"><Notice>{error}</Notice></div>}

      <section className="mb-10">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold">Lyrics</h2>
          <ButtonLink href={`/lyrics?project=${id}`} variant="primary" size="sm">
            <Sparkles size={13} /> Generate lyrics
          </ButtonLink>
        </div>
        {lyrics.length === 0 ? (
          <Empty title={assets.loading ? "Loading…" : "No lyrics in this project yet"}>
            Generate some, and they will be saved here with their version history.
          </Empty>
        ) : (
          <div className="space-y-2">
            {lyrics.map((asset) => (
              <Card key={asset.id} className="flex flex-wrap items-center gap-3 p-4 transition hover:border-grape/50">
                <Link href={`/lyrics?asset=${asset.id}`} className="min-w-0 flex-1">
                  <p className="truncate font-medium hover:text-volt">{asset.title}</p>
                  <p className="mt-0.5 text-xs text-muted">
                    v{asset.version} · {humanize(asset.origin)} · {formatWhen(asset.created_at)}
                  </p>
                </Link>
                {asset.is_mock && <Badge tone="mock">Mock</Badge>}
                {asset.approved && <Badge tone="live"><Check size={11} /> Approved</Badge>}
                <Button size="sm" variant="ghost" aria-label={`Download ${asset.title} as Markdown`} onClick={() => act("dl", () => download(`/api/assets/${asset.id}/export?format=md`, "lyrics.md"))}>
                  <Download size={13} />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Delete ${asset.title}`}
                  onClick={() => {
                    if (!confirm(`Delete “${asset.title}” and all its versions?`)) return;
                    act("del", async () => {
                      await api.deleteAsset(asset.id);
                      assets.reload();
                    });
                  }}
                >
                  <Trash2 size={13} />
                </Button>
              </Card>
            ))}
          </div>
        )}
      </section>

      {MEDIA_SECTIONS.map(({ kinds, title, href, cta }) => {
        const items = assets.data?.filter((a) => kinds.includes(a.kind)) ?? [];
        return (
          <section key={title} className="mb-10">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="font-display text-lg font-semibold">{title}</h2>
              <ButtonLink href={`${href}?project=${id}`} size="sm">{cta}</ButtonLink>
            </div>
            {items.length === 0 ? (
              <p className="text-sm text-muted">{assets.loading ? "Loading…" : `No ${title.toLowerCase()} in this project yet.`}</p>
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                {items.map((asset) => <MediaCard key={asset.id} asset={asset} onDeleted={assets.reload} />)}
              </div>
            )}
          </section>
        );
      })}

      <section>
        <h2 className="mb-4 font-display text-lg font-semibold">Generation history</h2>
        {!jobs.data?.length ? (
          <p className="text-sm text-muted">No generations have run in this project.</p>
        ) : (
          <Card className="divide-y divide-line">
            {jobs.data.map((job) => (
              <div key={job.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <Badge tone={JOB_TONE[job.status]}>{job.status}</Badge>
                <span className="font-mono text-xs">{job.kind}</span>
                {job.provider && <span className="font-mono text-xs text-muted">{job.provider}{job.model ? ` · ${job.model}` : ""}</span>}
                {job.error && <span className="min-w-0 flex-1 truncate text-xs text-danger">{job.error}</span>}
                <span className="ml-auto text-xs text-muted">{formatWhen(job.created_at)}</span>
              </div>
            ))}
          </Card>
        )}
      </section>
    </>
  );
}
