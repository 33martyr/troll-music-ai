"use client";

import { Check, Clapperboard, Copy, Download, Factory, FolderOpen, PenLine, RefreshCw, Shuffle, Share2, Swords } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { formatTime, TrackPlayer } from "./player";
import { api, errorMessage, fileUrl, type RemixBody } from "@/lib/api";
import type { Asset, Intensity, Job, LineTiming, Lyrics, TrollKind, TrollMeta, TrollRequest } from "@/lib/types";
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
  { id: "nuclear", emoji: "☢️", label: "Nuclear", blurb: "Friendship may not survive" },
];

export const LENGTHS: { id: string; label: string }[] = [
  { id: "short", label: "Short" },
  { id: "standard", label: "Standard" },
  { id: "long", label: "Long" },
];

/** Mirrors troll.SUBGENRES in the toolkit. */
export const SUBGENRES: Record<string, { id: string; label: string }[]> = {
  drill: [{ id: "uk", label: "UK Drill" }, { id: "ny", label: "NY Drill" }, { id: "jersey", label: "Jersey Club Drill" }],
  trap: [{ id: "rage", label: "Rage" }, { id: "plugg", label: "Plugg" }, { id: "phonk", label: "Phonk" }],
  "hip-hop": [{ id: "boom-bap", label: "Boom Bap" }, { id: "lofi", label: "Lo-fi" }, { id: "west-coast", label: "West Coast" }],
  pop: [{ id: "bubblegum", label: "Bubblegum" }, { id: "kpop", label: "K-Pop style" }, { id: "ballad", label: "Power Ballad" }],
  country: [{ id: "outlaw", label: "Outlaw" }, { id: "bro", label: "Bro-Country" }, { id: "bluegrass", label: "Bluegrass" }],
  opera: [{ id: "tragic", label: "Tragic Aria" }, { id: "comic", label: "Comic Opera" }, { id: "rock-opera", label: "Rock Opera" }],
  techno: [{ id: "hard", label: "Hard Techno" }, { id: "eurodance", label: "Eurodance" }, { id: "hyperpop", label: "Hyperpop" }],
};

export const DELIVERIES: { id: string; label: string }[] = [
  { id: "cocky", label: "😎 Overconfident" },
  { id: "hype", label: "📣 Hype Man" },
  { id: "narrator", label: "🎙️ Dramatic Narrator" },
  { id: "deadpan", label: "😐 Deadpan" },
  { id: "news", label: "📺 Breaking News" },
  { id: "diva", label: "💅 Diva" },
];

const JOKES = [
  "Gathering embarrassing evidence…",
  "Preparing lyrical destruction…",
  "The group chat won't recover…",
  "Preparing emotional damage…",
  "Contacting the rap department…",
  "Your friend's reputation is loading…",
  "Sharpening the punchlines…",
  "Mixing pure disrespect…",
  "Calling the beat police…",
  "Printing the parental advisory sticker…",
];

/** Stage labels the backend writes into job.stage ("<label> · <detail>"), in run order. */
export const STEPS = {
  words: { label: "Writing the lyrics", emoji: "✍️" },
  vocals: { label: "Recording the vocals", emoji: "🎤" },
  beat: { label: "Building the beat", emoji: "🥁" },
  mix: { label: "Mixing the track", emoji: "🎚️" },
  cover: { label: "Designing the cover", emoji: "🖼️" },
  video: { label: "Rendering the video", emoji: "🎬" },
} as const;
export type StepId = keyof typeof STEPS;

/** Which stages a troll job will run, mirroring backend/services/troll_jobs.py. */
export function planSteps(kind: TrollKind, opts: { video?: boolean; cover?: boolean; reuseLyrics?: boolean; rewrite?: boolean } = {}): StepId[] {
  const steps: StepId[] = [];
  const beatOnly = kind === "funny_beat";
  if (!beatOnly && (!opts.reuseLyrics || opts.rewrite)) steps.push("words");
  if (!beatOnly) steps.push("vocals");
  steps.push("beat");
  if (!beatOnly) steps.push("mix");
  if (opts.cover !== false || beatOnly) steps.push("cover");
  if (kind === "meme_video" || opts.video) steps.push("video");
  return steps;
}

/** Real job progress as a timeline of stages, with jokes while it runs. */
export function TrollProgress({
  runner,
  steps,
  onRetried,
}: {
  runner: ReturnType<typeof useJobRunner>;
  steps: StepId[];
  /** Called with the finished job when the user retried a failed one. */
  onRetried?: (job: Job) => void;
}) {
  const [tick, setTick] = useState(0);
  const running = runner.busy;
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setTick((value) => value + 1), 2600);
    return () => clearInterval(timer);
  }, [running]);
  if (!running) return <JobStatus runner={runner} onRetried={onRetried} />;
  const job = runner.job;
  const stage = job?.stage ?? "";
  const current = steps.findIndex((id) => stage.startsWith(STEPS[id].label));
  const detail = stage.includes(" · ") ? stage.split(" · ").slice(1).join(" · ") : null;
  return (
    <Card className="overflow-hidden p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-3xl" aria-hidden>
          {current >= 0 ? STEPS[steps[current]].emoji : "⏳"}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-display text-lg font-bold leading-tight">{JOKES[tick % JOKES.length]}</p>
          <p className="truncate text-xs text-muted" role="status" aria-live="polite">
            {job ? (job.status === "queued" ? "Waiting in the queue" : detail ?? stage) : "Starting"}
            {job?.provider ? ` · ${job.provider}${job.model ? ` · ${job.model}` : ""}` : ""}
          </p>
        </div>
        <span className="font-mono text-sm text-muted">{Math.round((job?.progress ?? 0) * 100)}%</span>
        <Button size="sm" variant="ghost" onClick={runner.cancel} disabled={job?.stage === "Cancelling"}>
          Cancel
        </Button>
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-line" aria-hidden>
        <div
          className="h-full rounded-full bg-gradient-to-r from-grape to-volt transition-all duration-700"
          style={{ width: `${Math.max(3, (job?.progress ?? 0) * 100)}%` }}
        />
      </div>
      <ol className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6" aria-label="Generation steps">
        {steps.map((id, index) => {
          const state = current < 0 ? "todo" : index < current ? "done" : index === current ? "now" : "todo";
          return (
            <li
              key={id}
              aria-current={state === "now" ? "step" : undefined}
              className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-xs transition ${
                state === "done"
                  ? "border-volt/30 bg-volt/5 text-fg"
                  : state === "now"
                    ? "border-volt bg-volt/10 font-semibold text-fg shadow-[0_0_24px_-10px] shadow-volt"
                    : "border-line text-muted"
              }`}
            >
              <span aria-hidden className={state === "now" ? "animate-pulse" : ""}>
                {state === "done" ? "✅" : STEPS[id].emoji}
              </span>
              <span className="leading-tight">{STEPS[id].label}</span>
            </li>
          );
        })}
      </ol>
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

export type RemixChanges = Omit<RemixBody, "asset_id">;

/** Change the style, heat, delivery, rapper or voice and make it again, keeping the lyrics. */
function RemixPanel({ troll, onRemix, busy }: { troll: TrollMeta; onRemix: (changes: RemixChanges) => void; busy: boolean }) {
  const request = troll.request;
  const [style, setStyle] = useState(troll.style);
  const [intensity, setIntensity] = useState<Intensity>(troll.intensity);
  const [delivery, setDelivery] = useState(request?.delivery ?? "cocky");
  const [rapper, setRapper] = useState(troll.artist);
  const [instruction, setInstruction] = useState("");
  const beatOnly = troll.kind === "funny_beat";
  const changes: RemixChanges = {
    style: style !== troll.style ? style : null,
    intensity: !beatOnly && intensity !== troll.intensity ? intensity : null,
    delivery: !beatOnly && delivery !== (request?.delivery ?? "cocky") ? delivery : null,
    rapper_name: rapper.trim() && rapper.trim() !== troll.artist ? rapper.trim() : null,
    instruction: instruction.trim() || null,
  };
  const changed = Object.values(changes).some(Boolean);
  const rewrites = !!(changes.instruction || changes.delivery || changes.intensity);
  return (
    <Card className="space-y-4 p-4">
      <p className="flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wide">
        <Shuffle size={15} className="text-volt" /> Remix it
      </p>
      <div className="flex flex-wrap gap-1.5">
        {STYLES.filter((s) => beatOnly || !s.beatOnly).map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setStyle(s.id)}
            aria-pressed={style === s.id}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${style === s.id ? "border-volt bg-volt text-ink" : "border-line hover:border-grape/60"}`}
          >
            {s.emoji} {s.label}
          </button>
        ))}
      </div>
      {!beatOnly && (
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-xs text-muted">
            Heat
            <select className="control mt-1" value={intensity} onChange={(e) => setIntensity(e.target.value as Intensity)}>
              {INTENSITIES.map((i) => (
                <option key={i.id} value={i.id}>{`${i.emoji} ${i.label}`}</option>
              ))}
            </select>
          </label>
          <label className="block text-xs text-muted">
            Delivery
            <select className="control mt-1" value={delivery} onChange={(e) => setDelivery(e.target.value)}>
              {DELIVERIES.map((d) => (
                <option key={d.id} value={d.id}>{d.label}</option>
              ))}
            </select>
          </label>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs text-muted">
          Rapper name
          <input className="control mt-1" value={rapper} maxLength={40} onChange={(e) => setRapper(e.target.value)} />
        </label>
        {!beatOnly && (
          <label className="block text-xs text-muted">
            Add an inside joke or change
            <input
              className="control mt-1"
              value={instruction}
              maxLength={500}
              placeholder="Mention the kebab incident"
              onChange={(e) => setInstruction(e.target.value)}
            />
          </label>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" disabled={!changed} busy={busy} onClick={() => onRemix(changes)}>
          {!busy && <Shuffle size={14} />} Remix
        </Button>
        <p className="text-xs text-muted">
          {!changed
            ? "Change something above."
            : rewrites
              ? "The lyrics get rewritten for this (new version), then everything is re-performed."
              : beatOnly
                ? "New beat and cover. The original stays in My Trolls."
                : "Same lyrics, new beat, voice and cover. The original stays in My Trolls."}
        </p>
      </div>
    </Card>
  );
}

/** Redo one person's verse, the chorus or any single section; everything else stays word for word. */
function RedoParts({ lyrics, onRedo, busy }: { lyrics: Lyrics; onRedo: (sectionId: string, label: string) => void; busy: boolean }) {
  const seen = new Set<string>();
  const parts = lyrics.sections.filter((s) => {
    const key = s.type === "chorus" ? "chorus" : s.id; // every chorus repeat is redone together
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return (
    <Card className="p-4">
      <p className="mb-1 flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wide">
        <RefreshCw size={15} className="text-volt" /> Re-cook one part
      </p>
      <p className="mb-3 text-xs text-muted">Rewrites only that section, then re-performs the track. The rest stays word for word.</p>
      <div className="flex flex-wrap gap-2">
        {parts.map((section) => (
          <Button key={section.id} size="sm" disabled={busy} onClick={() => onRedo(section.id, section.label)}>
            {section.performer ? "🎤 " : section.type === "chorus" ? "🔁 " : ""}
            {section.label}
          </Button>
        ))}
      </div>
    </Card>
  );
}

function Settings({ troll }: { troll: TrollMeta }) {
  const request = troll.request;
  const rows: [string, string | null | undefined][] = [
    ["Type", troll.label],
    ["Style", STYLES.find((s) => s.id === troll.style)?.label ?? troll.style],
    ["Heat", troll.kind === "funny_beat" ? null : INTENSITIES.find((i) => i.id === troll.intensity)?.label],
    ["Delivery", troll.kind === "funny_beat" ? null : DELIVERIES.find((d) => d.id === request?.delivery)?.label],
    ["Rapper", troll.artist],
    ["Template", request?.template],
    ["Lyrics", troll.lyrics_reused ? "Reused from the original" : null],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
      {rows
        .filter(([, value]) => value)
        .map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="text-muted">{label}</dt>
            <dd className="truncate font-medium">{value}</dd>
          </div>
        ))}
    </dl>
  );
}

export function TrollResult({
  job,
  onRegenerate,
  onRemix,
  regenerating,
}: {
  job: Job;
  /** Make it again from the original request (passed when the result knows it). */
  onRegenerate: (original?: TrollRequest) => void;
  onRemix: (assetId: string, changes: RemixChanges, kind: TrollKind) => void;
  regenerating: boolean;
}) {
  const [remixOpen, setRemixOpen] = useState(false);
  const [redoOpen, setRedoOpen] = useState(false);
  const [awards, setAwards] = useState<Asset[]>([]);
  const awardsRunner = useJobRunner();
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
              {troll && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {[
                    STYLES.find((s) => s.id === troll.style)?.label,
                    troll.kind !== "funny_beat" ? INTENSITIES.find((i) => i.id === troll.intensity)?.label : null,
                    troll.kind !== "funny_beat" ? DELIVERIES.find((d) => d.id === troll.request?.delivery)?.label : null,
                    made.song?.duration_seconds ? formatTime(made.song.duration_seconds) : null,
                  ]
                    .filter(Boolean)
                    .map((chip) => (
                      <span key={chip} className="rounded-full border border-line bg-ink/50 px-2.5 py-1 text-[11px] font-medium text-muted">
                        {chip}
                      </span>
                    ))}
                </div>
              )}
            </div>
            {!made.video && made.song && (
              <TrackPlayer src={fileUrl(made.song)} label={title} knownDuration={made.song.duration_seconds} autoPlay onTime={setTime} />
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
        {media && <DownloadLink asset={media} label={made.video ? "Video (MP4)" : made.song?.kind === "beat" ? "Beat (MP3)" : "Song (MP3)"} />}
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
        <Button onClick={() => onRegenerate(troll?.request)} busy={regenerating}>
          {!regenerating && <RefreshCw size={14} />} Again, but different
        </Button>
        {troll?.request && (
          <Button onClick={() => setRemixOpen(!remixOpen)} aria-expanded={remixOpen}>
            <Shuffle size={14} /> Remix
          </Button>
        )}
        {troll?.request && made.lyrics?.content && (
          <Button onClick={() => setRedoOpen(!redoOpen)} aria-expanded={redoOpen}>
            <RefreshCw size={14} /> Re-cook a part
          </Button>
        )}
        {troll && made.song && (
          <Link href={`/factory?asset=${made.song.id}`} className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-raised px-4 py-2.5 text-sm hover:border-grape/60">
            <Factory size={14} /> Meme Factory
          </Link>
        )}
        {troll?.kind === "rap_battle" && made.song && (
          <Link href={`/battle?id=${made.song.id}`} className="inline-flex items-center gap-1.5 rounded-lg border border-volt/50 bg-volt/10 px-4 py-2.5 text-sm hover:border-volt">
            <Swords size={14} /> Judges & votes
          </Link>
        )}
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
      {remixOpen && troll && (
        <RemixPanel troll={troll} busy={regenerating} onRemix={(changes) => onRemix((made.song ?? made.main).id, changes, troll.kind)} />
      )}
      {redoOpen && troll && made.lyrics?.content && (
        <RedoParts
          lyrics={made.lyrics.content}
          busy={regenerating}
          onRedo={(sectionId) => onRemix((made.song ?? made.main).id, { regenerate_sections: [sectionId] }, troll.kind)}
        />
      )}
      {troll && made.lyrics && (
        <div className="space-y-3">
          <Button
            busy={awardsRunner.busy}
            onClick={async () => {
              const done = await awardsRunner.run(() => api.roastAwards((made.song ?? made.main).id));
              if (done) setAwards((await Promise.all(done.result_asset_ids.map((id) => api.asset(id)))).filter((a) => a.has_file));
            }}
          >
            🏆 Roast Awards
          </Button>
          {awardsRunner.error && <JobStatus runner={awardsRunner} />}
          {!!awards.length && (
            <div className="grid gap-3 sm:grid-cols-3">
              {awards.map((card) => (
                <a key={card.id} href={fileUrl(card, true)} title="Download award card" className="block">
                  {/* eslint-disable-next-line @next/next/no-img-element -- served by the API with a signed URL */}
                  <img src={fileUrl(card)} alt={card.title} className="w-full rounded-xl" />
                  <span className="mt-1 block text-xs text-muted">{card.is_mock ? "Mock judge" : "AI opinion"} · {String(card.meta?.award ?? "")}</span>
                </a>
              ))}
            </div>
          )}
        </div>
      )}
      {troll && <Settings troll={troll} />}
      <MadeWith made={made} />
    </section>
  );
}
