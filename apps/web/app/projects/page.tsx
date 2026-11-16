"use client";

import { Copy, Download, FolderOpen, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button, Card, Empty, Field, Notice, PageHeader } from "@/components/ui";
import { api, download, errorMessage } from "@/lib/api";
import { formatWhen, useLoad } from "@/lib/hooks";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const projects = useLoad(api.projects);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(tag: string, action: () => Promise<unknown>) {
    setBusy(tag);
    setError(null);
    try {
      await action();
      projects.reload();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  }

  const remove = (project: Project) => {
    const count = Object.values(project.asset_counts).reduce((a, b) => a + b, 0);
    if (confirm(`Delete “${project.name}” and its ${count} asset(s)? This can't be undone.`)) {
      act(`delete:${project.id}`, () => api.deleteProject(project.id));
    }
  };

  return (
    <>
      <PageHeader eyebrow="Library" title="My Projects">
        A project keeps everything for one release together: lyrics now, beats, vocals, songs and videos as those
        modules arrive.
      </PageHeader>

      <Card className="mb-8 p-5">
        <form
          className="grid gap-3 sm:grid-cols-[1fr_1.5fr_auto] sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            act("create", async () => {
              await api.createProject(name, description);
              setName("");
              setDescription("");
            });
          }}
        >
          <Field label="New project">
            <input className="control" value={name} onChange={(e) => setName(e.target.value)} placeholder="Diss Tape Vol. 1" maxLength={120} required />
          </Field>
          <Field label="Description" hint="optional">
            <input className="control" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What's this release about?" maxLength={2000} />
          </Field>
          <Button type="submit" variant="primary" busy={busy === "create"} disabled={!name.trim()}>
            <Plus size={16} /> Create
          </Button>
        </form>
      </Card>

      {(error || projects.error) && <div className="mb-6"><Notice>{error ?? projects.error}</Notice></div>}

      {projects.data?.length === 0 && (
        <Empty title="No projects yet">Create one above, or generate lyrics first and file them later.</Empty>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {projects.data?.map((project) => (
          <Card key={project.id} className="flex flex-col p-5 transition hover:border-grape/50">
            <Link href={`/projects/${project.id}`} className="group flex-1">
              <p className="flex items-center gap-2 font-semibold group-hover:text-volt">
                <FolderOpen size={17} className="text-grape" /> {project.name}
              </p>
              {project.description && <p className="mt-1.5 line-clamp-2 text-sm text-muted">{project.description}</p>}
              <p className="mt-3 text-xs text-muted">
                {project.asset_counts.lyrics ?? 0} lyrics · updated {formatWhen(project.updated_at)}
              </p>
            </Link>
            <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-4">
              <Button size="sm" busy={busy === `dup:${project.id}`} onClick={() => act(`dup:${project.id}`, () => api.duplicateProject(project.id))}>
                <Copy size={13} /> Duplicate
              </Button>
              <Button size="sm" busy={busy === `exp:${project.id}`} onClick={() => act(`exp:${project.id}`, () => download(`/api/projects/${project.id}/export`, "project.zip"))}>
                <Download size={13} /> Export bundle
              </Button>
              <Button size="sm" variant="danger" className="ml-auto" busy={busy === `delete:${project.id}`} onClick={() => remove(project)}>
                <Trash2 size={13} /> Delete
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
