"use client";

import { ArrowDown, ChevronDown, Dices, Flame, Sparkles } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { TrackPlayer } from "@/components/player";
import { RecentTrolls } from "@/components/recent";
import { useCapability, useJobRunner } from "@/components/studio";
import {
  DELIVERIES,
  INTENSITIES,
  KINDS,
  LENGTHS,
  planSteps,
  type RemixChanges,
  STYLES,
  SUBGENRES,
  type StepId,
  TrollProgress,
  TrollResult,
  VOCAL_STYLES,
} from "@/components/troll";
import { Badge, Button, Notice } from "@/components/ui";
import { api, errorMessage, fileUrl } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Asset, Job, RoastTemplate, TrollKind, TrollRequest } from "@/lib/types";

const PLACEHOLDERS = [
  "He thinks he's rich but borrows money every Friday",
  "Replies 'on my way' while still in the shower",
  "Has been 'planning' the group holiday since 2021",
  "Explains crypto to everyone. Lost 94% of it.",
];

const DEFAULTS: TrollRequest = {
  situation: "",
  kind: "diss_track",
  style: "trap",
  subgenre: null,
  intensity: "savage",
  delivery: "cocky",
  length: "standard",
  target: "",
  names: [],
  rapper_name: "",
  explicit: false,
  instructions: "",
  vocal_style: "auto",
};

function Chip({ active, onClick, children, tone = "volt" }: { active: boolean; onClick: () => void; children: React.ReactNode; tone?: "volt" | "grape" }) {
  const on = tone === "volt" ? "border-volt bg-volt text-ink shadow-[0_0_20px_-8px] shadow-volt" : "border-grape bg-grape/25 text-fg";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-3.5 py-2 text-sm font-medium transition active:scale-95 ${active ? on : "border-line bg-panel/80 text-fg hover:border-grape/60"}`}
    >
      {children}
    </button>
  );
}

function Step({ n, title, hint, children }: { n: number; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wide">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-grape text-xs text-white">{n}</span>
          {title}
        </p>
        {hint && <p className="text-xs text-muted">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

/** One honest line about what will do the work, without the jargon. */
function Engines({ kind }: { kind: string }) {
  const text = useCapability("text");
  const voice = useCapability("voice");
  const music = useCapability("music");
  if (text.error) return <Notice>{text.error}</Notice>;
  const needsWords = kind !== "funny_beat";
  const words = text.capability;
  if (needsWords && words && !words.configured) {
    return (
      <Notice tone="info">
        <strong>No AI is writing jokes yet.</strong> Pick a text model in{" "}
        <Link href="/settings" className="underline">
          AI Settings
        </Link>{" "}
        (Pollinations is free and needs no key). Funny Beat works without one.
      </Notice>
    );
  }
  const singer = needsWords && music.capability?.sings ? music.capability : null;
  return (
    <p className="flex flex-wrap items-center justify-center gap-1.5 text-xs text-muted">
      {needsWords && words && (
        <>
          Jokes by <span className="font-mono text-fg">{words.model ?? words.provider}</span>
          {words.is_mock ? <Badge tone="mock">Mock, not real AI</Badge> : <Badge tone="grape">AI</Badge>}
        </>
      )}
      {singer && (
        <>
          · Sung by <span className="font-mono text-fg">{singer.model ?? singer.provider}</span>
          {singer.is_mock ? <Badge tone="mock">Mock, not real AI</Badge> : <Badge tone="grape">AI vocals + beat</Badge>}
        </>
      )}
      {!singer && music.capability && (
        <>
          · Beat by <span className="font-mono text-fg">{music.capability.provider}</span>
          {music.capability.is_ai ? <Badge tone="grape">AI</Badge> : <Badge>Built-in</Badge>}
        </>
      )}
      {needsWords && !singer && voice.capability && (
        <>
          · Voice by <span className="font-mono text-fg">{voice.capability.provider}</span>
          <Badge tone="mock">Spoken, not sung</Badge>
        </>
      )}
      <Link href="/settings" className="underline underline-offset-2 hover:text-fg">
        change
      </Link>
    </p>
  );
}

/** The newest real troll, as proof of what comes out. Nothing is shown if there is none yet. */
function Showcase() {
  const [track, setTrack] = useState<Asset | null>(null);
  const [cover, setCover] = useState<Asset | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let live = true;
    (async () => {
      const latest = (await api.assets("kind=song&limit=20")).find((a) => a.meta?.troll && a.has_file) ?? null;
      const coverId = latest?.meta?.troll?.cover_asset_id;
      const art = coverId ? await api.asset(coverId).catch(() => null) : null;
      if (live) {
        setTrack(latest);
        setCover(art);
      }
    })()
      .catch(() => undefined)
      .finally(() => live && setLoaded(true));
    return () => {
      live = false;
    };
  }, []);

  if (!loaded) return <div className="hidden aspect-square w-full animate-pulse rounded-3xl bg-panel lg:block" aria-hidden />;
  if (!track) {
    return (
      <ol className="space-y-3 rounded-3xl border border-line bg-panel/70 p-6">
        {[
          ["🎯", "Name the target", "First name or nickname. That's it."],
          ["🫖", "Spill the tea", "What did they do? The pettier the better."],
          ["🔥", "Pick the heat", "Friendly, Savage, Brutal or Nuclear."],
          ["📲", "Send it", "Song, cover and video, ready for the group chat."],
        ].map(([emoji, title, text]) => (
          <li key={title} className="flex gap-3">
            <span className="text-2xl" aria-hidden>{emoji}</span>
            <span>
              <span className="block font-display text-sm font-bold">{title}</span>
              <span className="block text-sm text-muted">{text}</span>
            </span>
          </li>
        ))}
      </ol>
    );
  }
  const troll = track.meta!.troll!;
  return (
    <figure className="overflow-hidden rounded-3xl border border-line bg-panel/80 shadow-2xl shadow-grape/10">
      {cover?.has_file ? (
        // eslint-disable-next-line @next/next/no-img-element -- served by the API with a signed URL
        <img src={fileUrl(cover)} alt={`Cover of ${track.title}`} className="aspect-square w-full object-cover" />
      ) : (
        <div className="flex aspect-square items-center justify-center bg-grape/15 text-7xl">🎤</div>
      )}
      <figcaption className="space-y-3 p-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-grape">Fresh from the lab · {troll.label}</p>
          <p className="truncate font-display text-lg font-bold">{track.title}</p>
          <p className="truncate text-sm text-muted">{troll.artist} · starring {troll.target}</p>
        </div>
        <TrackPlayer src={fileUrl(track)} label={track.title} knownDuration={track.duration_seconds} lazy compact />
      </figcaption>
    </figure>
  );
}

export default function RoastPage() {
  const [form, setForm] = useState<TrollRequest>(DEFAULTS);
  const [namesText, setNamesText] = useState("");
  const [withVideo, setWithVideo] = useState(false);
  const [more, setMore] = useState(false);
  const [result, setResult] = useState<Job | null>(null);
  const [lastProject, setLastProject] = useState<string | null>(null);
  const [helperError, setHelperError] = useState<string | null>(null);
  const [jokesText, setJokesText] = useState("");
  const [steps, setSteps] = useState<StepId[]>([]);
  const templates = useLoad(api.trollTemplates);
  const stock = useLoad(api.stockVoices);
  const rappers = useLoad(api.rappers);
  const params = useSearchParams();
  const [rapperId, setRapperId] = useState("");
  const runner = useJobRunner();
  const sung = !!useCapability("music").capability?.sings;
  const resultRef = useRef<HTMLDivElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  /** Perform as a Troll Universe rapper: their name, genre, delivery and voice. */
  function pickRapper(id: string, list = rappers.data) {
    setRapperId(id);
    const rapper = list?.find((r) => r.id === id);
    if (!rapper) return;
    setForm((f) => ({ ...f, rapper_name: rapper.name, delivery: rapper.delivery, style: rapper.style, subgenre: null, voice: rapper.voice ?? f.voice }));
    setMore(true);
  }

  // Arriving from a rapper page ("Roast someone as …") preselects that rapper.
  const wanted = params.get("rapper");
  useEffect(() => {
    if (!wanted) return;
    let live = true;
    api.rappers().then((list) => live && pickRapper(wanted, list), () => undefined);
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted]);

  // "Open" from Recent trolls or My Trolls (?track=<song id>) reopens that result here.
  const track = params.get("track");
  useEffect(() => {
    if (!track) return;
    let live = true;
    (async () => {
      const asset = await api.asset(track);
      const jobs = asset.project_id ? await api.projectJobs(asset.project_id) : [];
      const job = jobs.find((j) => j.status === "completed" && j.result_asset_ids.includes(track));
      if (!live) return;
      if (!job) throw new Error("This troll was made outside the one-button flow, so it opens in its project instead.");
      setResult(job);
      setLastProject(job.project_id);
      window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    })().catch((reason) => live && setHelperError(errorMessage(reason)));
    return () => {
      live = false;
    };
  }, [track]);

  // Rotates on the client only, so server and client render the same first placeholder.
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setPlaceholderIndex((i) => (i + 1) % PLACEHOLDERS.length), 4000);
    return () => clearInterval(timer);
  }, []);

  const set = <K extends keyof TrollRequest>(key: K, value: TrollRequest[K]) => setForm((f) => ({ ...f, [key]: value }));
  const beatOnly = form.kind === "funny_beat";
  const group = form.kind === "group_roast";
  const styles = STYLES.filter((s) => beatOnly || !s.beatOnly);
  const subgenres = SUBGENRES[form.style] ?? [];
  const ready = form.situation.trim().length >= 3 && (!group || namesText.split(",").some((n) => n.trim()));

  function startRoasting() {
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => nameRef.current?.focus({ preventScroll: true }), 400);
  }

  async function generate(projectId: string | null, original?: TrollRequest) {
    const request: TrollRequest = original ?? {
      ...form,
      situation: form.situation.trim(),
      target: form.target?.trim() || null,
      rapper_name: form.rapper_name?.trim() || null,
      instructions: form.instructions?.trim() || null,
      names: group ? namesText.split(",").map((n) => n.trim()).filter(Boolean) : [],
      style: !beatOnly && STYLES.find((s) => s.id === form.style)?.beatOnly ? "trap" : form.style,
      inside_jokes: jokesText.split("\n").map((j) => j.trim()).filter(Boolean).slice(0, 5),
      voice: form.voice || null,
      voice_b: form.voice_b || null,
    };
    const video = withVideo && request.kind !== "meme_video";
    setSteps(planSteps(request.kind, { video, sung }));
    setResult(null);
    resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    const done = await runner.run(() => api.troll(request, projectId, { with_video: video }));
    if (done) {
      setResult(done);
      setLastProject(done.project_id);
    }
  }

  async function remix(assetId: string, changes: RemixChanges, kind: TrollKind) {
    if (!result) return;
    const rewrite = !!(changes.instruction || changes.delivery || changes.intensity || changes.regenerate_sections?.length);
    setSteps(planSteps(kind, { reuseLyrics: kind !== "funny_beat", rewrite, sung }));
    setResult(null);
    resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    const done = await runner.run(() => api.remix({ asset_id: assetId, ...changes }));
    if (done) setResult(done);
  }

  function applyTemplate(template: RoastTemplate) {
    const who = form.target?.trim() || "my friend";
    setForm((f) => ({
      ...f,
      template: template.id,
      situation: template.scenario.replaceAll("{name}", who),
      kind: template.kind,
      style: template.style,
      subgenre: null,
      intensity: template.intensity,
      delivery: template.delivery,
    }));
    setResult(null);
  }

  async function randomize() {
    setHelperError(null);
    try {
      const idea = await api.randomTroll();
      setForm((f) => ({ ...f, ...idea, subgenre: null, target: idea.target ?? "", rapper_name: idea.rapper_name ?? "" }));
      setResult(null);
    } catch (reason) {
      setHelperError(errorMessage(reason));
    }
  }

  async function newRapperName() {
    setHelperError(null);
    try {
      set("rapper_name", (await api.rapperName()).name);
    } catch (reason) {
      setHelperError(errorMessage(reason));
    }
  }

  return (
    <div className="space-y-14">
      <section className="rise grid items-center gap-10 lg:grid-cols-[1.25fr_1fr]">
        <div>
          <p className="mb-4 text-xs font-semibold uppercase tracking-[0.25em] text-grape">Roast it. Rap it. Release it.</p>
          <h1 className="font-display text-[2.6rem] font-black leading-[0.98] tracking-tight sm:text-6xl xl:text-7xl">
            YOUR FRIENDS ARE ABOUT TO BECOME <span className="text-gradient">A SONG</span> <span aria-hidden>💀</span>
          </h1>
          <p className="mt-5 max-w-xl text-base text-muted sm:text-lg">
            Turn embarrassing stories, inside jokes and savage roasts into AI-powered diss tracks, covers and meme videos for the group chat.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={startRoasting}
              className="inline-flex items-center gap-2 rounded-2xl bg-volt px-6 py-4 font-display text-base font-black uppercase tracking-wide text-ink shadow-[0_0_40px_-10px] shadow-volt transition hover:brightness-110 active:scale-[0.98]"
            >
              <Flame size={20} /> Roast someone
            </button>
            <a
              href="#recent"
              className="inline-flex items-center gap-2 rounded-2xl border border-line bg-panel/80 px-6 py-4 font-display text-base font-bold uppercase tracking-wide transition hover:border-grape/60"
            >
              Explore the chaos <ArrowDown size={18} />
            </a>
          </div>
        </div>
        <Showcase />
      </section>

      <form
        ref={formRef}
        className="scroll-mt-20 space-y-9 rounded-3xl border border-line bg-panel/40 p-4 sm:p-7"
        onSubmit={(event) => {
          event.preventDefault();
          if (ready && !runner.busy) generate(null);
        }}
      >
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="font-display text-2xl font-black uppercase tracking-tight sm:text-3xl">Who are we roasting?</h2>
          <Button size="sm" onClick={randomize}>
            <Dices size={14} /> Random roast
          </Button>
        </div>

        <Step n={1} title={group ? "Who's in the chat?" : "Name the target"} hint={group ? "Separate names with commas" : "First name or nickname"}>
          {group ? (
            <input
              value={namesText}
              onChange={(e) => setNamesText(e.target.value)}
              placeholder="Dave, Sam, Priya"
              aria-label="Names in the group chat"
              className="control !rounded-2xl !p-4 !text-lg"
            />
          ) : (
            <input
              ref={nameRef}
              value={form.target ?? ""}
              onChange={(e) => set("target", e.target.value)}
              placeholder="Dave"
              aria-label="Who are we roasting?"
              maxLength={40}
              className="control !rounded-2xl !p-4 !text-lg font-semibold"
            />
          )}
          <textarea
            value={form.situation}
            onChange={(e) => set("situation", e.target.value)}
            placeholder={PLACEHOLDERS[placeholderIndex]}
            aria-label="What did they do?"
            rows={3}
            maxLength={600}
            className="control !rounded-2xl !p-4 !text-base leading-snug"
          />
          <p className="flex justify-between text-xs text-muted">
            <span>The story, the crime, the inside joke. Roast what they did, not who they are.</span>
            <span className="tabular-nums">{form.situation.length}/600</span>
          </p>
          {group && (
            <p className="text-xs text-muted">
              Want nicknames, a crime and a voice per person?{" "}
              <Link href="/group" className="underline">Open the full Group Chat Roast</Link>.
            </p>
          )}
          {!!templates.data?.length && (
            <div>
              <p className="mb-2 text-xs font-medium text-muted">Or start from a classic</p>
              <div className="-mx-4 flex snap-x gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0">
                {templates.data.map((template) => (
                  <button
                    key={template.id}
                    type="button"
                    onClick={() => applyTemplate(template)}
                    aria-pressed={form.template === template.id}
                    title={template.examples.map((e) => e.replaceAll("{name}", form.target?.trim() || "they")).join(" · ")}
                    className={`shrink-0 snap-start rounded-full border px-3 py-1.5 text-sm transition ${
                      form.template === template.id ? "border-grape bg-grape/20 text-fg" : "border-line bg-panel/60 text-muted hover:border-grape/60 hover:text-fg"
                    }`}
                  >
                    <span aria-hidden>{template.emoji}</span> {template.name}
                  </button>
                ))}
              </div>
              {form.template && (
                <p className="mt-1 text-xs text-muted">
                  Template on: edit anything above before you hit Generate.{" "}
                  <button type="button" className="underline" onClick={() => set("template", null)}>
                    Turn off
                  </button>
                </p>
              )}
            </div>
          )}
        </Step>

        <Step n={2} title="Pick your weapon">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {KINDS.map((kind) => {
              const active = form.kind === kind.id;
              return (
                <button
                  key={kind.id}
                  type="button"
                  onClick={() => set("kind", kind.id)}
                  aria-pressed={active}
                  className={`rounded-2xl border p-3 text-left transition active:scale-[0.98] sm:p-4 ${
                    active ? "border-volt bg-volt/10 shadow-[0_0_30px_-12px] shadow-volt" : "border-line bg-panel/80 hover:border-grape/60"
                  }`}
                >
                  <span className="text-2xl" aria-hidden>{kind.emoji}</span>
                  <span className="mt-1 block font-display text-sm font-bold">{kind.label}</span>
                  <span className="mt-0.5 block text-xs leading-snug text-muted">{kind.blurb}</span>
                </button>
              );
            })}
          </div>
        </Step>

        <Step n={3} title="Set the vibe">
          <div className="flex flex-wrap gap-2">
            {styles.map((style) => (
              <Chip key={style.id} active={form.style === style.id} onClick={() => setForm((f) => ({ ...f, style: style.id, subgenre: null }))}>
                <span aria-hidden>{style.emoji}</span> {style.label}
              </Chip>
            ))}
          </div>
          {subgenres.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted">Flavour:</span>
              <Chip tone="grape" active={!form.subgenre} onClick={() => set("subgenre", null)}>Classic</Chip>
              {subgenres.map((sub) => (
                <Chip key={sub.id} tone="grape" active={form.subgenre === sub.id} onClick={() => set("subgenre", sub.id)}>
                  {sub.label}
                </Chip>
              ))}
            </div>
          )}
          {!beatOnly && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {INTENSITIES.map((level) => {
                const active = form.intensity === level.id;
                const hot = level.id === "brutal" || level.id === "nuclear";
                return (
                  <button
                    key={level.id}
                    type="button"
                    onClick={() => set("intensity", level.id)}
                    aria-pressed={active}
                    className={`rounded-xl border px-2 py-3 text-center transition active:scale-[0.98] ${
                      active ? (hot ? "border-danger bg-danger/15" : "border-volt bg-volt/10") : "border-line bg-panel/80 hover:border-grape/60"
                    }`}
                  >
                    <span className="block text-xl" aria-hidden>{level.emoji}</span>
                    <span className="block text-sm font-bold">{level.label}</span>
                    <span className="block text-[11px] text-muted">{level.blurb}</span>
                  </button>
                );
              })}
            </div>
          )}
        </Step>

        {!beatOnly && (
          <Step n={4} title="Vocal personality" hint="How it's written and performed">
            <div className="flex flex-wrap gap-2">
              {DELIVERIES.map((d) => (
                <Chip key={d.id} tone="grape" active={form.delivery === d.id} onClick={() => set("delivery", d.id)}>
                  {d.label}
                </Chip>
              ))}
            </div>
            {sung && (
              <div className="space-y-2">
                <p className="text-xs text-muted">Singing voice: a direction for the AI singer, not a guarantee. Always an original voice.</p>
                <div className="flex flex-wrap gap-2">
                  {VOCAL_STYLES.map((v) => (
                    <Chip key={v.id} tone="grape" active={(form.vocal_style ?? "auto") === v.id} onClick={() => set("vocal_style", v.id)}>
                      {v.label}
                    </Chip>
                  ))}
                </div>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted">Length:</span>
              {LENGTHS.map((length) => (
                <Chip key={length.id} tone="grape" active={(form.length ?? "standard") === length.id} onClick={() => set("length", length.id)}>
                  {length.label}
                </Chip>
              ))}
            </div>
          </Step>
        )}

        <div>
          <button
            type="button"
            onClick={() => setMore(!more)}
            aria-expanded={more}
            className="inline-flex items-center gap-1 text-sm text-muted hover:text-fg"
          >
            <ChevronDown size={15} className={`transition ${more ? "rotate-180" : ""}`} /> More options: rapper, voice, inside jokes, instructions
          </button>
          {more && (
            <div className="mt-3 grid gap-4 rounded-2xl border border-line bg-panel/60 p-4 md:grid-cols-2">
              {!!rappers.data?.length && (
                <label className="block text-xs font-medium text-muted">
                  Perform as a rapper from your Troll Universe
                  <select className="control mt-1" value={rapperId} onChange={(e) => (e.target.value ? pickRapper(e.target.value) : setRapperId(""))}>
                    <option value="">Nobody in particular</option>
                    {rappers.data.map((r) => (
                      <option key={r.id} value={r.id}>{r.name} · {r.overall} OVR</option>
                    ))}
                  </select>
                </label>
              )}
              <div className="text-xs font-medium text-muted">
                Your rapper name
                <div className="mt-1 flex gap-2">
                  <input
                    value={form.rapper_name ?? ""}
                    onChange={(e) => set("rapper_name", e.target.value)}
                    placeholder="Leave empty for a surprise"
                    maxLength={40}
                    aria-label="Your rapper name"
                    className="control min-w-0 flex-1"
                  />
                  <Button onClick={newRapperName}>
                    <Dices size={15} /> Name me
                  </Button>
                </div>
              </div>
              {!beatOnly && !!stock.data?.voices.length && (
                <label className="block text-xs font-medium text-muted">
                  {form.kind === "rap_battle" ? "Your voice" : "Voice"}
                  <select className="control mt-1" value={form.voice ?? ""} onChange={(e) => set("voice", e.target.value || null)}>
                    <option value="">Default</option>
                    {stock.data.voices.map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </label>
              )}
              {form.kind === "rap_battle" && !!stock.data?.voices.length && (
                <label className="block text-xs font-medium text-muted">
                  Their voice
                  <select className="control mt-1" value={form.voice_b ?? ""} onChange={(e) => set("voice_b", e.target.value || null)}>
                    <option value="">Pick a different one for me</option>
                    {stock.data.voices.map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </label>
              )}
              {!beatOnly && (
                <label className="block text-xs font-medium text-muted">
                  Inside jokes (one per line, up to 5)
                  <textarea
                    value={jokesText}
                    onChange={(e) => setJokesText(e.target.value)}
                    rows={2}
                    placeholder={"the kebab incident\nthat time with the karaoke machine"}
                    className="control mt-1"
                  />
                </label>
              )}
              {!beatOnly && (
                <label className="block text-xs font-medium text-muted">
                  Custom instructions
                  <textarea
                    value={form.instructions ?? ""}
                    onChange={(e) => set("instructions", e.target.value)}
                    rows={2}
                    maxLength={300}
                    placeholder="Rhyme everything with 'Friday'. End on a cliffhanger."
                    className="control mt-1"
                  />
                </label>
              )}
              {!beatOnly && (
                <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm md:col-span-2">
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={!!form.explicit} onChange={(e) => set("explicit", e.target.checked)} className="accent-volt" />
                    Uncensored (swearing allowed)
                  </label>
                  {form.kind !== "meme_video" && (
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={withVideo} onChange={(e) => setWithVideo(e.target.checked)} className="accent-volt" />
                      Also make a vertical meme video
                    </label>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {helperError && <Notice>{helperError}</Notice>}

        <div className="space-y-3">
          <button
            type="submit"
            disabled={!ready || runner.busy}
            className="group flex w-full items-center justify-center gap-3 rounded-2xl bg-volt px-6 py-5 font-display text-xl font-black uppercase tracking-wide text-ink shadow-[0_0_40px_-10px] shadow-volt transition hover:brightness-110 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40 sm:text-2xl"
          >
            <Flame size={26} className="transition group-hover:rotate-12" />
            {runner.busy ? "Cooking…" : form.intensity === "nuclear" && !beatOnly ? "Launch the nuke" : "Generate"}
          </button>
          {!ready && !runner.busy && (
            <p className="text-center text-xs text-muted">
              {group ? "Add at least one name and what the group did." : "Tell us what they did (a few words is enough)."}
            </p>
          )}
          <Engines kind={form.kind} />
        </div>
      </form>

      <div ref={resultRef} className="scroll-mt-20 space-y-4">
        {(runner.busy || runner.error) && (
          <TrollProgress
            runner={runner}
            steps={steps}
            onRetried={(done) => {
              setResult(done);
              setLastProject(done.project_id);
            }}
          />
        )}
        {result && !runner.busy && (
          <TrollResult job={result} regenerating={runner.busy} onRegenerate={(original) => generate(lastProject, original)} onRemix={remix} />
        )}
      </div>

      <section id="recent" className="scroll-mt-20">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 className="flex items-center gap-2 font-display text-xl font-black uppercase tracking-tight">
            <Sparkles size={18} className="text-volt" /> The chaos so far
          </h2>
          <Link href="/projects" className="text-sm text-muted hover:text-fg">
            All my trolls →
          </Link>
        </div>
        <RecentTrolls refreshKey={result?.id ?? null} />
      </section>
    </div>
  );
}
