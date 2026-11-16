"use client";

import { Music, Sparkles } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { JobStatus, Library, MediaCard, PoweredBy, ProjectSelect, UploadButton, useCapability, useJobRunner } from "@/components/studio";
import { Button, ButtonLink, Card, Field, Notice, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Asset, BeatRequest } from "@/lib/types";

const ENERGY = ["", "Very calm", "Laid back", "Steady groove", "Energetic", "Hard hitting"];

export default function BeatPage() {
  const params = useSearchParams();
  const lyricsId = params.get("lyrics");
  const options = useLoad(api.options);
  const music = useCapability("music");
  const library = useLoad(() => api.assets("kind=beat&limit=30"));
  const runner = useJobRunner();

  const [form, setForm] = useState<BeatRequest>({
    genre: params.get("genre") ?? "trap",
    bpm: Number(params.get("bpm")) || null,
    mood: null,
    instruments: [],
    energy: 3,
    duration_seconds: 30,
    key: null,
    description: null,
    variations: 1,
  });
  const [projectId, setProjectId] = useState(params.get("project") ?? "");
  const [results, setResults] = useState<Asset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const set = <K extends keyof BeatRequest>(key: K, value: BeatRequest[K]) => setForm((f) => ({ ...f, [key]: value }));

  async function showResults(job: { result_asset_ids: string[] }) {
    setResults(await Promise.all(job.result_asset_ids.map((id) => api.asset(id))));
    library.reload();
  }

  async function generate() {
    setResults([]);
    const job = await runner.run(() => api.generateBeat(form, projectId || null, lyricsId));
    if (job) await showResults(job);
  }

  async function upload(file: File) {
    setUploading(true);
    setUploadError(null);
    try {
      setResults([await api.uploadAudio(file, "beat", projectId || null, form.bpm)]);
      library.reload();
    } catch (reason) {
      setUploadError(errorMessage(reason));
    } finally {
      setUploading(false);
    }
  }

  const songLink = (asset: Asset) => (
    <ButtonLink size="sm" href={`/song?beat=${asset.id}${lyricsId ? `&lyrics=${lyricsId}` : ""}`}>
      <Music size={13} /> Use in a song
    </ButtonLink>
  );

  return (
    <>
      <PageHeader eyebrow="Instrumental" title="Generate Beat">
        Make an instrumental on its own, or upload one you already have. Beats are saved as MP3 and can be reused in
        any number of songs.
      </PageHeader>

      <div className="mb-6">
        <PoweredBy {...music} what="beats" />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,26rem)_1fr]">
        <Card className="space-y-4 p-5">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Genre">
              <input className="control" list="genres" value={form.genre} onChange={(e) => set("genre", e.target.value)} maxLength={60} />
              <datalist id="genres">{options.data?.genres.map((g) => <option key={g} value={g} />)}</datalist>
            </Field>
            <Field label="BPM" hint="blank = genre default">
              <input className="control" type="number" min={50} max={220} value={form.bpm ?? ""} placeholder="auto" onChange={(e) => set("bpm", e.target.value ? Number(e.target.value) : null)} />
            </Field>
            <Field label="Mood">
              <select className="control" value={form.mood ?? ""} onChange={(e) => set("mood", e.target.value || null)}>
                <option value="">Any</option>
                {options.data?.moods.map((m) => <option key={m}>{m}</option>)}
              </select>
            </Field>
            <Field label="Key" hint="optional">
              <input className="control" value={form.key ?? ""} placeholder="e.g. F minor" maxLength={20} onChange={(e) => set("key", e.target.value || null)} />
            </Field>
          </div>

          <Field label="Energy" hint={ENERGY[form.energy]}>
            <input type="range" min={1} max={5} value={form.energy} onChange={(e) => set("energy", Number(e.target.value))} className="w-full accent-[var(--color-volt)]" />
          </Field>

          <Field label="Length" hint={`${form.duration_seconds} seconds`}>
            <input type="range" min={5} max={180} step={5} value={form.duration_seconds} onChange={(e) => set("duration_seconds", Number(e.target.value))} className="w-full accent-[var(--color-volt)]" />
          </Field>

          <div>
            <p className="mb-1.5 text-xs font-medium text-muted">Instruments</p>
            <div className="flex flex-wrap gap-1.5">
              {options.data?.instruments.map((instrument) => {
                const on = form.instruments.includes(instrument);
                return (
                  <button
                    key={instrument}
                    type="button"
                    aria-pressed={on}
                    onClick={() => set("instruments", on ? form.instruments.filter((i) => i !== instrument) : [...form.instruments, instrument])}
                    className={`rounded-full border px-2.5 py-1 text-xs transition ${on ? "border-volt/60 bg-volt/10 text-volt" : "border-line text-muted hover:text-fg"}`}
                  >
                    {instrument}
                  </button>
                );
              })}
            </div>
          </div>

          <Field label="Anything else" hint="optional">
            <textarea className="control [field-sizing:content]" rows={2} maxLength={500} value={form.description ?? ""} placeholder="e.g. dark and spacious, like a villain entering a supermarket" onChange={(e) => set("description", e.target.value || null)} />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Variations">
              <select className="control" value={form.variations} onChange={(e) => set("variations", Number(e.target.value))}>
                {[1, 2, 3, 4].map((n) => <option key={n}>{n}</option>)}
              </select>
            </Field>
            <ProjectSelect value={projectId} onChange={setProjectId} />
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            <Button variant="primary" busy={runner.busy} disabled={!music.capability?.configured || !form.genre.trim()} onClick={generate}>
              {!runner.busy && <Sparkles size={15} />} Generate beat
            </Button>
            <UploadButton label="Upload my own" busy={uploading} onFile={upload} />
          </div>
          <p className="text-xs text-muted">Uploads: audio up to {options.data?.max_upload_mb ?? 50} MB. Set the BPM above first if you know it.</p>
        </Card>

        <div className="space-y-4">
          <JobStatus runner={runner} onRetried={showResults} />
          {uploadError && <Notice>{uploadError}</Notice>}
          {results.map((asset) => (
            <MediaCard key={asset.id} asset={asset} actions={songLink(asset)} />
          ))}
          {!results.length && !runner.busy && !runner.error && (
            <div className="rounded-2xl border border-dashed border-line px-6 py-12 text-center text-sm text-muted">
              Your beat will appear here with a player and a download button.
            </div>
          )}
        </div>
      </div>

      <Library title="Your beats" assets={library.data} loading={library.loading} empty="No beats yet." onChanged={library.reload} actions={songLink} />
    </>
  );
}
