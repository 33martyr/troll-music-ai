"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { AssetSelect, JobStatus, Library, MediaCard, PoweredBy, formatDuration, useCapability, useJobRunner } from "@/components/studio";
import { Badge, Button, Card, Field, Notice, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { humanize, useLoad } from "@/lib/hooks";
import type { Asset, Job, Storyboard } from "@/lib/types";

const ASPECT_LABEL: Record<string, string> = { "16:9": "16:9 landscape", "9:16": "9:16 vertical", "1:1": "1:1 square" };

export default function VideoPage() {
  const params = useSearchParams();
  const options = useLoad(api.options);
  const audioList = useLoad(() => api.assets("kind=song,beat,vocals&limit=100"));
  const lyricsList = useLoad(() => api.assets("kind=lyrics&limit=100"));
  const videos = useLoad(() => api.assets("kind=video&limit=20"));
  const image = useCapability("image");
  const runner = useJobRunner();

  const [audioId, setAudioId] = useState(params.get("audio") ?? "");
  const [lyricsId, setLyricsId] = useState(params.get("lyrics") ?? "");
  const [style, setStyle] = useState("lyric video");
  const [aspect, setAspect] = useState("16:9");
  const [subtitles, setSubtitles] = useState(true);
  const [seconds, setSeconds] = useState(20);
  const [notes, setNotes] = useState("");
  const [result, setResult] = useState<{ video: Asset; storyboard: Asset<Storyboard> | null } | null>(null);

  async function show(job: Job) {
    const video = await api.asset(job.result_asset_id!);
    const boardId = video.meta?.storyboard_asset_id;
    setResult({ video, storyboard: boardId ? await api.asset<Storyboard>(boardId) : null });
    videos.reload();
  }

  async function generate() {
    setResult(null);
    const job = await runner.run(() =>
      api.generateVideo({
        audio_asset_id: audioId || null,
        lyrics_asset_id: lyricsId || null,
        style,
        aspect,
        subtitles,
        duration_seconds: audioId ? null : seconds,
        notes: notes.trim() || null,
      }),
    );
    if (job) await show(job);
  }

  const board = result?.storyboard?.content;

  return (
    <>
      <PageHeader eyebrow="Workshop" title="Video Maker">
        Plans a storyboard from the song&apos;s sections, creates one image per scene and renders an MP4 with motion,
        fades, the audio and timed lyrics.
      </PageHeader>

      <div className="mb-6 space-y-3">
        <PoweredBy {...image} what="scene images" />
        <Notice tone="info">
          Videos are rendered from still images with FFmpeg (slow zoom and fades). No AI video-animation model is
          integrated, so scenes do not contain generated motion.
        </Notice>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,26rem)_1fr]">
        <Card className="space-y-4 p-5">
          <AssetSelect
            label="Audio"
            hint="song, beat or vocals"
            assets={audioList.data}
            value={audioId}
            onChange={setAudioId}
            none="No audio (silent video)"
            empty={<>Nothing saved yet. <Link href="/song" className="underline">Make a song</Link>.</>}
          />
          <AssetSelect
            label="Lyrics"
            hint={audioId ? "optional: found from the song automatically" : "required without audio"}
            assets={lyricsList.data}
            value={lyricsId}
            onChange={setLyricsId}
            none={audioId ? "Use the song's own lyrics" : "Choose…"}
            empty={<>No lyrics yet. <Link href="/lyrics" className="underline">Write some</Link>.</>}
          />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Visual style">
              <select className="control" value={style} onChange={(e) => setStyle(e.target.value)}>
                {options.data?.visual_styles.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
              </select>
            </Field>
            <Field label="Format">
              <select className="control" value={aspect} onChange={(e) => setAspect(e.target.value)}>
                {(options.data?.aspects ?? ["16:9"]).map((a) => <option key={a} value={a}>{ASPECT_LABEL[a] ?? a}</option>)}
              </select>
            </Field>
          </div>
          {!audioId && (
            <Field label="Length" hint={`${seconds} seconds`}>
              <input type="range" min={5} max={120} step={5} value={seconds} onChange={(e) => setSeconds(Number(e.target.value))} className="w-full accent-[var(--color-volt)]" />
            </Field>
          )}
          <Field label="Director's notes" hint="optional">
            <textarea className="control [field-sizing:content]" rows={2} maxLength={500} value={notes} placeholder="e.g. everything happens in a supermarket at 3am" onChange={(e) => setNotes(e.target.value)} />
          </Field>
          <label className="flex items-center gap-2.5 text-sm">
            <input type="checkbox" checked={subtitles} onChange={(e) => setSubtitles(e.target.checked)} className="h-4 w-4 accent-[var(--color-volt)]" />
            Burn in the lyrics as subtitles
          </label>
          <Button variant="primary" busy={runner.busy} disabled={!audioId && !lyricsId} onClick={generate}>
            {!runner.busy && <Sparkles size={15} />} Generate video
          </Button>
          <p className="text-xs text-muted">A one-minute song takes roughly a minute to render with the built-in title cards; AI images take longer.</p>
        </Card>

        <div className="space-y-4">
          <JobStatus runner={runner} onRetried={show} />
          {result && (
            <MediaCard asset={result.video}>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <Badge>{result.video.meta?.scenes} scenes</Badge>
                <Badge>Images: {result.video.meta?.image_provider}</Badge>
                <Badge>Storyboard: {result.video.meta?.storyboard_source === "llm" ? "AI-directed" : "template"}</Badge>
                {!!result.video.meta?.image_fallbacks && result.video.meta.image_provider !== "typographic" && (
                  <Badge tone="mock">{result.video.meta.image_fallbacks} scene(s) fell back to title cards</Badge>
                )}
              </div>
            </MediaCard>
          )}
          {board && (
            <Card className="p-4">
              <h3 className="mb-3 font-display text-sm font-semibold">Storyboard</h3>
              <ol className="space-y-2.5">
                {board.scenes.map((scene) => (
                  <li key={scene.index} className="flex gap-3 text-sm">
                    <span className="w-24 shrink-0 font-mono text-xs text-muted">
                      {formatDuration(scene.start)}–{formatDuration(scene.end)}
                    </span>
                    <span className="min-w-0">
                      <span className="font-medium">{scene.label}</span>
                      <span className="block text-xs text-muted">{scene.description}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </Card>
          )}
          {!result && !runner.busy && !runner.error && (
            <div className="rounded-2xl border border-dashed border-line px-6 py-12 text-center text-sm text-muted">
              Your video will appear here with a player, its storyboard and a download button.
            </div>
          )}
        </div>
      </div>

      <Library title="Your videos" assets={videos.data} loading={videos.loading} empty="No videos yet." onChanged={videos.reload} />
    </>
  );
}
