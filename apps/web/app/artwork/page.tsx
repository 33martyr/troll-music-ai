"use client";

import { Sparkles } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { JobStatus, Library, MediaCard, PoweredBy, ProjectSelect, useCapability, useJobRunner } from "@/components/studio";
import { Button, Card, Field, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { humanize, useLoad } from "@/lib/hooks";
import type { Asset } from "@/lib/types";

export default function ArtworkPage() {
  const params = useSearchParams();
  const options = useLoad(api.options);
  const image = useCapability("image");
  const covers = useLoad(() => api.assets("kind=artwork&limit=24"));
  const runner = useJobRunner();
  const [title, setTitle] = useState(params.get("title") ?? "");
  const [genre, setGenre] = useState("hip-hop");
  const [mood, setMood] = useState("");
  const [style, setStyle] = useState("cartoon");
  const [character, setCharacter] = useState("");
  const [notes, setNotes] = useState("");
  const [projectId, setProjectId] = useState("");
  const [cover, setCover] = useState<Asset | null>(null);

  async function generate() {
    setCover(null);
    const job = await runner.run(() =>
      api.generateArtwork({ project_id: projectId || null, title: title.trim(), genre, mood: mood || null, style, character: character.trim() || null, notes: notes.trim() || null }),
    );
    if (job) {
      setCover(await api.asset(job.result_asset_id!));
      covers.reload();
    }
  }

  return (
    <>
      <PageHeader eyebrow="Workshop" title="Cover Maker">
        A 1024 × 1024 cover for a track, saved as PNG.
      </PageHeader>
      <div className="mb-6">
        <PoweredBy {...image} what="cover art" />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,26rem)_1fr]">
        <Card className="space-y-4 p-5">
          <Field label="Track title">
            <input className="control" value={title} maxLength={120} placeholder="Lambo On Layaway" onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Genre">
              <input className="control" list="art-genres" value={genre} maxLength={60} onChange={(e) => setGenre(e.target.value)} />
              <datalist id="art-genres">{options.data?.genres.map((g) => <option key={g} value={g} />)}</datalist>
            </Field>
            <Field label="Mood">
              <select className="control" value={mood} onChange={(e) => setMood(e.target.value)}>
                <option value="">Any</option>
                {options.data?.moods.map((m) => <option key={m}>{m}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Style">
            <select className="control" value={style} onChange={(e) => setStyle(e.target.value)}>
              {options.data?.visual_styles.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </select>
          </Field>
          <Field label="Character or subject" hint="optional, fictional">
            <input className="control" value={character} maxLength={300} placeholder="a llama in a tracksuit" onChange={(e) => setCharacter(e.target.value)} />
          </Field>
          <Field label="Anything else" hint="optional">
            <textarea className="control [field-sizing:content]" rows={2} maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
          <ProjectSelect value={projectId} onChange={setProjectId} />
          <Button variant="primary" busy={runner.busy} disabled={!title.trim() || !image.capability?.configured} onClick={generate}>
            {!runner.busy && <Sparkles size={15} />} Generate cover
          </Button>
          {image.capability && !image.capability.is_ai && image.capability.configured && (
            <p className="text-xs leading-relaxed text-muted">
              The built-in engine draws a typographic cover from the title; it ignores style, character and notes.
              Choose an AI image provider in AI Settings for illustrated covers.
            </p>
          )}
        </Card>

        <div className="space-y-4">
          <JobStatus runner={runner} onRetried={async (job) => setCover(await api.asset(job.result_asset_id!))} />
          {cover && <MediaCard asset={cover} />}
          {!cover && !runner.busy && !runner.error && (
            <div className="rounded-2xl border border-dashed border-line px-6 py-12 text-center text-sm text-muted">
              Your cover will appear here.
            </div>
          )}
        </div>
      </div>

      <Library title="Your covers" assets={covers.data} loading={covers.loading} empty="No covers yet." onChanged={covers.reload} />
    </>
  );
}
