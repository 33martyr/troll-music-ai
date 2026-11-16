"use client";

import { Check, Clapperboard, Copy, Download, FolderOpen, PenLine, RefreshCw, Share2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage, fileUrl } from "@/lib/api";
import type { Asset, Intensity, Job, LineTiming, Lyrics, TrollKind, TrollMeta } from "@/lib/types";
import { JobStatus, OriginBadge, useJobRunner } from "./studio";
import { Badge, Button, Card, Equalizer, Notice } from "./ui";

// --------------------------------- vocab ----------------------------------- //

export const KINDS: { id: TrollKind; emoji: string; label: string; blurb: string }[] = [
  { id: "diss_track", emoji: "🎤", label: "Diss Track", blurb: "Two verses and a hook about them" },
  { id: "roast", emoji: "🔥", label: "Savage Roast", blurb: "A dozen one-liners over a beat" },
  { id: "rap_battle", emoji: "⚔️", label: "Rap Battle", blurb: "You vs them, two voices" },
  { id: "meme_song", emoji: "🎶", label: "Meme Song", blurb: "A chant the group chat can't unhear" },
  { id: "group_roast", emoji: "💬", label: "Group Chat Roast", blurb: "Everyone gets a verse" },
  { id: "funny_beat", emoji: "🥁", label: "Funny Beat", blurb: "An instrumental with a ridiculous title" },
  { id: "meme_video", emoji: "🎬", label: "Meme Video", blurb: "Vertical MP4, ready for the chat" },
];

export const STYLES: { id: string; emoji: string; label: string; beatOnly?: boolean }[] = [
  { id: "drill", emoji: "🥶", label: "Drill" },
  { id: "trap", emoji: "💸", label: "Trap" },
  { id: "hip-hop", emoji: "🧢", label: "Hip-Hop" },
  { id: "pop", emoji: "🍭", label: "Pop" },
  { id: "country", emoji: "🤠", label: "Country" },
  { id: "opera", emoji: "🎭", label: "Opera" },
  { id: "techno", emoji: "🪩", label: "Techno" },
  { id: "circus", emoji: "🤡", label: "Circus", beatOnly: true },
  { id: "8-bit", emoji: "👾", label: "8-Bit", beatOnly: true },
];

export const INTENSITIES: { id: Intensity; emoji: string; label: string; blurb: string }[] = [
  { id: "friendly", emoji: "😇", label: "Friendly", blurb: "They'll laugh" },
  { id: "savage", emoji: "🔥", label: "Savage", blurb: "They'll need a minute" },
  { id: "brutal", emoji: "💀", label: "Brutal", blurb: "Emotional damage" },
];

export const DELIVERIES: { id: string; label: string }[] = [
  { id: "cocky", label: "😎 Overconfident" },
  { id: "hype", label: "📣 Hype Man" },
  { id: "narrator", label: "🎙️ Dramatic Narrator" },
  { id: "deadpan", label: "😐 Deadpan" },
  { id: "news", label: "📺 Breaking News" },
  { id: "diva", label: "💅 Diva" },
];

const JOKES = [
  "Consulting the group chat archives…",
  "Teaching the beat some disrespect…",
  "Finding a rhyme for 'borrowed'…",
  "Removing anything HR would flag…",
  "Polishing the punchlines…",
  "Asking the 808 to hit harder…",
  "Printing the parental advisory sticker…",
];

// --------------------------------- progress -------------------------------- //

/** Real job progress, with jokes while it runs. */
export function TrollProgress({ runner }: { runner: ReturnType<typeof useJobRunner> }) {
  const [tick, setTick] = useState(0);
  const running = runner.busy;
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setTick((value) => value + 1), 2600);
    return () => clearInterval(timer);
  }, [running]);
  if (!running) return <JobStatus runner={runner} />;
  const job = runner.job;
  return (
    <Card className="overflow-hidden p-6 text-center">
      <p className="text-4xl" aria-hidden>
        {["🎤", "🔥", "💀", "🎶", "🥁"][tick % 5]}
      </p>
      <p className="mt-3 font-display text-lg font-bold">{JOKES[tick % JOKES.length]}</p>
      <p className="mt-1 text-sm text-muted" role="status" aria-live="polite">
        {job ? (job.status === "queued" ? "In the queue" : job.stage) : "Starting"}
      </p>
      <div className="mx-auto mt-5 h-3 max-w-md overflow-hidden rounded-full bg-line" aria-hidden>
        <div
          className="h-full rounded-full bg-gradient-to-r from-grape to-volt transition-all duration-700"
          style={{ width: `${Math.max(4, (job?.progress ?? 0) * 100)}%` }}
        />
      </div>
      <div className="mt-4 flex items-center justify-center gap-3">
        <Equalizer />
        <span className="font-mono text-xs text-muted">{Math.round((job?.progress ?? 0) * 100)}%</span>
        <Button size="sm" variant="ghost" onClick={runner.cancel}>
          Cancel
        </Button>
      </div>
    </Card>
  );
}

// ---------------------------------- result --------------------------------- //

interface Made {
  main: Asset;
  song: Asset | null;
  video: Asset | null;
  cover: Asset | null;
  lyrics: Asset<Lyrics> | null;
  parts: Asset[];
  troll: TrollMeta | null;
}

async function loadMade(job: Job): Promise<Made> {
  const parts = await Promise.all(job.result_asset_ids.map((id) => api.asset(id)));
  const byKind = (kind: string) => parts.filter((a) => a.kind === kind).at(-1) ?? null;
  const withMeta = parts.find((a) => a.meta?.troll) ?? null;
  const troll = withMeta?.meta?.troll ?? null;
  const main = parts.find((a) => a.id === job.result_asset_id) ?? parts[parts.length - 1];
  return {
    main,
    song: byKind("song") ?? byKind("beat"),
    video: byKind("video"),
    cover: byKind("artwork"),
    lyrics: byKind("lyrics") as Asset<Lyrics> | null,
    parts,
    troll,
  };
}

function lyricsText(made: Made): string {
  const lyrics = made.lyrics?.content;
  if (!lyrics) return "";
  return [lyrics.title, ...lyrics.sections.map((s) => [`[${s.label}]`, ...s.lines].join("\n"))].join("\n\n");
}

/** Lines from the vocal timing, highlighted as the audio plays. */
function Karaoke({ timings, lyrics, time }: { timings: LineTiming[] | null | undefined; lyrics: Lyrics | null | undefined; time: number }) {
  const active = useRef<HTMLParagraphElement>(null);
  const current = timings ? timings.findIndex((line, i) => time >= line.start && time < (timings[i + 1]?.start ?? Infinity)) : -1;
  useEffect(() => {
    active.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [current]);
  if (timings?.length) {
    return (
      <div className="max-h-72 space-y-1 overflow-y-auto pr-2">
        {timings.map((line, index) => (
          <p
            key={index}
            ref={index === current ? active : undefined}
            className={`transition ${index === current ? "scale-[1.02] font-semibold text-volt" : index < current ? "text-muted" : "text-fg/80"}`}
          >
            {(index === 0 || timings[index - 1].label !== line.label) && (
              <span className="mb-0.5 mt-3 block text-[11px] font-semibold uppercase tracking-widest text-grape">{line.label}</span>
            )}
            {line.text}
          </p>
        ))}
      </div>
    );
  }
  if (!lyrics) return null;
  return (
    <div className="max-h-72 space-y-3 overflow-y-auto pr-2">
      {lyrics.sections.map((section) => (
        <div key={section.id}>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-grape">{section.label}</p>
          {section.lines.map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </div>
      ))}
    </div>
  );
}

const extension = (asset: Asset) => (asset.mime_type?.includes("mp4") ? "mp4" : asset.mime_type?.includes("png") ? "png" : "mp3");
const fileName = (asset: Asset, title: string) => `${title.replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "-") || "troll"}.${extension(asset)}`;

/** Native share sheet with the file itself (phones); otherwise copy the caption and download. */
function ShareButton({ asset, title, caption }: { asset: Asset; title: string; caption: string }) {
  const [state, setState] = useState<"idle" | "busy" | "copied" | "error">("idle");
  async function share() {
    setState("busy");
    try {
      const blob = await (await fetch(fileUrl(asset))).blob();
      const file = new File([blob], fileName(asset, title), { type: asset.mime_type ?? blob.type });
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title, text: caption });
        setState("idle");
        return;
      }
      // Desktop browsers can't share files: put the caption on the clipboard and save the file.
      await navigator.clipboard?.writeText(caption).catch(() => undefined);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = file.name;
      link.click();
      URL.revokeObjectURL(url);
      setState("copied");
    } catch (reason) {
      setState((reason as Error)?.name === "AbortError" ? "idle" : "error");
    }
  }
  return (
    <Button variant="primary" onClick={share} busy={state === "busy"} className="flex-1 sm:flex-none">
      {state !== "busy" && <Share2 size={16} />}
      {state === "copied" ? "Saved + caption copied" : state === "error" ? "Couldn't share, try Download" : "Send to the group chat"}
    </Button>
  );
}

function DownloadLink({ asset, label }: { asset: Asset; label: string }) {
  return (
    <a
      href={fileUrl(asset, true)}
      className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-raised px-3 py-2 text-sm hover:border-grape/60"
    >
      <Download size={14} /> {label}
    </a>
  );
}

/** What made each part, in plain words. Keeps every honesty label visible. */
function MadeWith({ made }: { made: Made }) {
  const rows: [string, Asset<unknown> | null][] = [
    ["Words", made.lyrics],
    ["Beat", made.parts.find((a) => a.kind === "beat") ?? null],
    ["Voice", made.parts.find((a) => a.kind === "vocals") ?? null],
    ["Cover", made.cover],
    ["Video", made.video],
  ];
  return (
    <details className="text-xs text-muted">
      <summary className="cursor-pointer select-none hover:text-fg">What made this?</summary>
      <ul className="mt-2 space-y-1.5">
        {rows
          .filter(([, asset]) => asset)
          .map(([label, asset]) => (
            <li key={label} className="flex flex-wrap items-center gap-2">
              <span className="w-12">{label}</span>
              <OriginBadge asset={asset!} />
              {asset!.meta?.delivery === "spoken" && <Badge tone="mock">Spoken, not sung</Badge>}
              {asset!.meta?.renderer === "ffmpeg-stills" && <Badge>Still images + motion</Badge>}
              {asset!.meta?.meme_overlay && <Badge>Text and sticker drawn built-in</Badge>}
            </li>
          ))}
      </ul>
    </details>
  );
}

export function TrollResult({ job, onRegenerate, regenerating }: { job: Job; onRegenerate: () => void; regenerating: boolean }) {
  const [made, setMade] = useState<Made | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [time, setTime] = useState(0);
  const [copied, setCopied] = useState(false);
  const videoRunner = useJobRunner();

  useEffect(() => {
    let live = true;
    loadMade(job)
      .then((value) => live && setMade(value))
      .catch((reason) => live && setError(errorMessage(reason)));
    return () => {
      live = false;
    };
  }, [job]);

  if (error) return <Notice>{error}</Notice>;
  if (!made) {
    return (
      <Card className="p-6 text-center text-sm text-muted">
        <Equalizer /> Loading your masterpiece…
      </Card>
    );
  }

  const troll = made.troll;
  const title = made.lyrics?.content?.title ?? made.song?.title ?? made.main.title;
  const artist = troll?.artist ?? "TROLL-MUSIC-AI";
  const media = made.video ?? made.song;
  const timings = made.song?.meta?.line_timings;
  const caption = `🔥 "${title}" by ${artist}${troll ? ` (feat. ${troll.target}'s dignity)` : ""}. Made with TROLL-MUSIC-AI.`;

  async function makeVideo() {
    if (!made?.song) return;
    const done = await videoRunner.run(() =>
      api.generateVideo({
        project_id: job.project_id,
        audio_asset_id: made.song!.id,
        lyrics_asset_id: made.lyrics?.id ?? null,
        title,
        style: "meme",
        aspect: "9:16",
        subtitles: true,
        intro: { presenter: artist, title },
        notes: "meme music video, comedic scenes, dramatic and ridiculous",
      }),
    );
    if (done?.result_asset_id) {
      const video = await api.asset(done.result_asset_id);
      setMade((current) => (current ? { ...current, video, parts: [...current.parts, video] } : current));
    }
  }

  return (
    <section className="rise space-y-4" aria-label="Your result">
      <Card className="overflow-hidden">
        <div className="grid gap-0 md:grid-cols-[minmax(0,320px)_1fr]">
          <div className="bg-black/40">
            {made.video ? (
              <video
                key={made.video.id}
                controls
                playsInline
                preload="metadata"
                src={fileUrl(made.video)}
                poster={made.cover ? fileUrl(made.cover) : undefined}
                onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
                className="mx-auto max-h-[70vh] w-full bg-black"
              />
            ) : made.cover ? (
              // eslint-disable-next-line @next/next/no-img-element -- served by the API with a signed URL
              <img src={fileUrl(made.cover)} alt={`Cover of ${title}`} className="aspect-square w-full object-cover" />
            ) : (
              <div className="flex aspect-square items-center justify-center text-7xl">🎤</div>
            )}
          </div>
          <div className="flex min-w-0 flex-col gap-4 p-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-grape">
                {troll?.label ?? "Fresh troll"} · {artist}
              </p>
              <h2 className="mt-1 font-display text-2xl font-extrabold leading-tight sm:text-3xl">{title}</h2>
              {troll && <p className="mt-1 text-sm text-muted">Starring {troll.target}. They had it coming.</p>}
            </div>
            {!made.video && made.song && (
              <audio
                controls
                autoPlay
                src={fileUrl(made.song)}
                onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
                className="w-full"
              />
            )}
            <Karaoke timings={timings} lyrics={made.lyrics?.content} time={time} />
          </div>
        </div>
      </Card>

      {troll?.warnings?.map((warning) => (
        <Notice key={warning} tone="mock">
          {warning}
        </Notice>
      ))}

      <div className="flex flex-wrap items-center gap-2">
        {media && <ShareButton asset={media} title={title} caption={caption} />}
        {media && <DownloadLink asset={media} label={made.video ? "Video (MP4)" : "Song (MP3)"} />}
        {made.video && made.song && <DownloadLink asset={made.song} label="MP3" />}
        {made.cover && <DownloadLink asset={made.cover} label="Cover" />}
        {made.lyrics && (
          <Button
            onClick={async () => {
              await navigator.clipboard?.writeText(lyricsText(made));
              setCopied(true);
            }}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : "Copy lyrics"}
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={onRegenerate} busy={regenerating}>
          {!regenerating && <RefreshCw size={14} />} Again, but different
        </Button>
        {!made.video && made.song?.kind === "song" && (
          <Button onClick={makeVideo} busy={videoRunner.busy}>
            {!videoRunner.busy && <Clapperboard size={14} />} Make it a meme video
          </Button>
        )}
        {made.lyrics && (
          <Link href={`/lyrics?asset=${made.lyrics.id}`} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-muted hover:bg-white/5 hover:text-fg">
            <PenLine size={14} /> Tweak the lyrics
          </Link>
        )}
        {job.project_id && (
          <Link href={`/projects/${job.project_id}`} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-muted hover:bg-white/5 hover:text-fg">
            <FolderOpen size={14} /> Saved in My Trolls
          </Link>
        )}
      </div>
      {videoRunner.busy || videoRunner.error ? <JobStatus runner={videoRunner} /> : null}
      <MadeWith made={made} />
    </section>
  );
}
