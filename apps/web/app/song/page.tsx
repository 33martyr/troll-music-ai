"use client";

import { Clapperboard, Image as ImageIcon, Sparkles } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { AssetSelect, JobStatus, Library, MediaCard, PoweredBy, UploadButton, useCapability, useJobRunner } from "@/components/studio";
import { Button, ButtonLink, Card, Field, Notice, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Asset, Job } from "@/lib/types";

type VocalSource = "new" | "existing";

export default function SongPage() {
  const params = useSearchParams();
  const lyricsList = useLoad(() => api.assets("kind=lyrics&limit=100"));
  const beats = useLoad(() => api.assets("kind=beat&limit=100"));
  const vocalsList = useLoad(() => api.assets("kind=vocals&limit=100"));
  const songs = useLoad(() => api.assets("kind=song&limit=30"));
  const stock = useLoad(api.stockVoices);
  const profiles = useLoad(api.voices);
  const providers = useLoad(api.providers);
  const voice = useCapability("voice");
  const runner = useJobRunner();

  const [mode, setMode] = useState<"mix" | "model">("mix");
  const [lyricsId, setLyricsId] = useState(params.get("lyrics") ?? "");
  const [beatId, setBeatId] = useState(params.get("beat") ?? "");
  const [vocalSource, setVocalSource] = useState<VocalSource>(params.get("vocals") ? "existing" : "new");
  const [vocalsId, setVocalsId] = useState(params.get("vocals") ?? "");
  const [voiceName, setVoiceName] = useState("");
  const [voiceB, setVoiceB] = useState("");
  const [profileId, setProfileId] = useState("");
  const [title, setTitle] = useState("");
  const [vocalGain, setVocalGain] = useState(3);
  const [beatGain, setBeatGain] = useState(-4);
  const [stylePrompt, setStylePrompt] = useState("");
  const [result, setResult] = useState<{ song: Asset; vocals: Asset | null } | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const lyrics = lyricsList.data?.find((a) => a.id === lyricsId);
  const sections = (lyrics?.content as { sections?: { performer?: string | null }[] } | null)?.sections ?? [];
  const isBattle = new Set(sections.map((s) => s.performer).filter(Boolean)).size > 1;
  const music = providers.data?.find((p) => p.kind === "music");
  const canSing = !!music?.options.find((o) => o.name === music.provider)?.capabilities.includes("full_song_with_vocals");
  const usableProfiles = profiles.data?.filter((p) => p.usable) ?? [];

  const ready =
    !!lyricsId && (mode === "model" ? canSing : !!beatId && (vocalSource === "new" || !!vocalsId));

  async function show(job: Job) {
    const song = await api.asset(job.result_asset_id!);
    const sources = await api.assetSources(song.id);
    setResult({ song, vocals: sources.find((s) => s.relation === "vocals")?.asset ?? null });
    songs.reload();
    vocalsList.reload();
  }

  async function generate(reuseVocals?: string) {
    setResult(null);
    const existing = reuseVocals ?? (vocalSource === "existing" ? vocalsId : null);
    const job = await runner.run(() =>
      api.generateSong({
        mode,
        lyrics_asset_id: lyricsId,
        beat_asset_id: mode === "mix" ? beatId : null,
        vocals_asset_id: mode === "mix" ? existing : null,
        title: title.trim() || null,
        voice: voiceName || null,
        voice_b: isBattle ? voiceB || null : null,
        voice_profile_id: profileId || null,
        vocal_gain_db: vocalGain,
        beat_gain_db: beatGain,
        style_prompt: mode === "model" ? stylePrompt.trim() || null : null,
      }),
    );
    if (job) await show(job);
  }

  async function uploadVocals(file: File) {
    setUploadError(null);
    try {
      const asset = await api.uploadAudio(file, "vocals", null, null);
      vocalsList.reload();
      setVocalSource("existing");
      setVocalsId(asset.id);
    } catch (reason) {
      setUploadError(errorMessage(reason));
    }
  }

  const videoLink = (asset: Asset) => (
    <>
      <ButtonLink size="sm" href={`/video?audio=${asset.id}`}>
        <Clapperboard size={13} /> Make a video
      </ButtonLink>
      <ButtonLink size="sm" href={`/artwork?title=${encodeURIComponent(asset.title)}`}>
        <ImageIcon size={13} /> Cover art
      </ButtonLink>
    </>
  );

  return (
    <>
      <PageHeader eyebrow="Full track" title="Generate Song">
        Combine lyrics, a beat and vocals into one mixed MP3. Each part stays a separate asset, so you can redo the
        vocals or the mix without touching the rest.
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,26rem)_1fr]">
        <Card className="space-y-4 p-5">
          <div className="grid grid-cols-2 gap-1 rounded-xl border border-line p-1 text-sm">
            {([["mix", "Beat + vocals"], ["model", "Sung by a music model"]] as const).map(([value, label]) => (
              <button key={value} type="button" aria-pressed={mode === value} onClick={() => setMode(value)} className={`rounded-lg px-3 py-1.5 transition ${mode === value ? "bg-grape/20 text-fg" : "text-muted hover:text-fg"}`}>
                {label}
              </button>
            ))}
          </div>

          <AssetSelect
            label="Lyrics"
            assets={lyricsList.data}
            value={lyricsId}
            onChange={setLyricsId}
            empty={<>No lyrics yet. <Link href="/lyrics" className="underline">Write or generate some</Link>.</>}
          />

          {mode === "model" ? (
            <>
              {providers.data && !canSing && (
                <Notice tone="info">
                  The active music provider (<span className="font-mono">{music?.provider}</span>) cannot sing lyrics.
                  ACE-Step can: start its server and choose it in{" "}
                  <Link href="/settings" className="underline">Model Settings</Link>. Until then, use “Beat + vocals”.
                </Notice>
              )}
              <Field label="Musical style" hint="optional">
                <input className="control" value={stylePrompt} maxLength={500} placeholder="e.g. comedy trap, deep male rap vocal" onChange={(e) => setStylePrompt(e.target.value)} />
              </Field>
            </>
          ) : (
            <>
              <AssetSelect
                label="Beat"
                assets={beats.data}
                value={beatId}
                onChange={setBeatId}
                empty={<>No beats yet. <Link href={`/beat${lyricsId ? `?lyrics=${lyricsId}` : ""}`} className="underline">Generate or upload one</Link>.</>}
              />

              <div>
                <p className="mb-1.5 text-xs font-medium text-muted">Vocals</p>
                <div className="grid grid-cols-2 gap-1 rounded-xl border border-line p-1 text-sm">
                  {([["new", "Generate new"], ["existing", "Use a saved take"]] as const).map(([value, label]) => (
                    <button key={value} type="button" aria-pressed={vocalSource === value} onClick={() => setVocalSource(value)} className={`rounded-lg px-3 py-1.5 transition ${vocalSource === value ? "bg-grape/20 text-fg" : "text-muted hover:text-fg"}`}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {vocalSource === "existing" ? (
                <div className="space-y-2">
                  <AssetSelect label="Vocal take" assets={vocalsList.data} value={vocalsId} onChange={setVocalsId} empty="No saved vocals yet. Generate new ones, or upload a recording." />
                  <UploadButton label="Upload a vocal recording" onFile={uploadVocals} />
                  {uploadError && <p className="text-xs text-danger">{uploadError}</p>}
                </div>
              ) : (
                <div className="space-y-3">
                  <PoweredBy {...voice} what="vocals" />
                  {stock.data && !stock.data.singing && stock.data.provider && (
                    <p className="text-xs leading-relaxed text-amber">
                      This voice provider speaks. Lines are timed to the beat, one per bar, so the result is rhythmic
                      spoken word, not singing.
                    </p>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    <Field label={isBattle ? "Voice A" : "Voice"}>
                      <select className="control" value={profileId ? `profile:${profileId}` : voiceName} onChange={(e) => {
                        const value = e.target.value;
                        if (value.startsWith("profile:")) { setProfileId(value.slice(8)); setVoiceName(""); }
                        else { setProfileId(""); setVoiceName(value); }
                      }}>
                        <option value="">Default</option>
                        {stock.data?.voices.map((name) => <option key={name}>{name}</option>)}
                        {usableProfiles.map((p) => <option key={p.id} value={`profile:${p.id}`}>{p.name} (voice profile)</option>)}
                      </select>
                    </Field>
                    {isBattle && (
                      <Field label="Voice B">
                        <select className="control" value={voiceB} onChange={(e) => setVoiceB(e.target.value)}>
                          <option value="">Default</option>
                          {stock.data?.voices.map((name) => <option key={name}>{name}</option>)}
                        </select>
                      </Field>
                    )}
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <Field label="Vocal level" hint={`${vocalGain > 0 ? "+" : ""}${vocalGain} dB`}>
                  <input type="range" min={-12} max={12} value={vocalGain} onChange={(e) => setVocalGain(Number(e.target.value))} className="w-full accent-[var(--color-volt)]" />
                </Field>
                <Field label="Beat level" hint={`${beatGain > 0 ? "+" : ""}${beatGain} dB`}>
                  <input type="range" min={-18} max={6} value={beatGain} onChange={(e) => setBeatGain(Number(e.target.value))} className="w-full accent-[var(--color-volt)]" />
                </Field>
              </div>
            </>
          )}

          <Field label="Song title" hint="optional">
            <input className="control" value={title} maxLength={200} placeholder={lyrics?.title ?? "Uses the lyrics title"} onChange={(e) => setTitle(e.target.value)} />
          </Field>

          <Button variant="primary" busy={runner.busy} disabled={!ready} onClick={() => generate()}>
            {!runner.busy && <Sparkles size={15} />} Generate song
          </Button>
        </Card>

        <div className="space-y-4">
          <JobStatus runner={runner} onRetried={show} />
          {result && (
            <>
              <MediaCard asset={result.song} actions={videoLink(result.song)} />
              {result.vocals && (
                <MediaCard
                  asset={result.vocals}
                  actions={
                    <>
                      <Button size="sm" disabled={runner.busy} onClick={() => generate(result.vocals!.id)}>Remix with these vocals</Button>
                      <Button size="sm" disabled={runner.busy} onClick={() => { setVocalSource("new"); generate(""); }}>New vocal take</Button>
                    </>
                  }
                />
              )}
              <p className="text-xs text-muted">
                “Remix” applies your level changes to the same vocal take. “New vocal take” records the lyrics again
                and leaves the beat and lyrics as they are.
              </p>
            </>
          )}
          {!result && !runner.busy && !runner.error && (
            <div className="rounded-2xl border border-dashed border-line px-6 py-12 text-center text-sm text-muted">
              Your song will appear here with a player, the separate vocal track and a download button.
            </div>
          )}
        </div>
      </div>

      <Library title="Your songs" assets={songs.data} loading={songs.loading} empty="No songs yet." onChanged={songs.reload} actions={videoLink} />
    </>
  );
}
