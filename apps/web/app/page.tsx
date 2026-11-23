"use client";

import { ChevronDown, Dices, Flame } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { RecentTrolls } from "@/components/recent";
import { useCapability, useJobRunner } from "@/components/studio";
import {
  DELIVERIES,
  INTENSITIES,
  KINDS,
  planSteps,
  type RemixChanges,
  STYLES,
  type StepId,
  TrollProgress,
  TrollResult,
} from "@/components/troll";
import { Badge, Button, Notice } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Job, RoastTemplate, TrollRequest } from "@/lib/types";

const PLACEHOLDERS = [
  "My friend Dave thinks he's rich but borrows money every Friday",
  "Sam replies 'on my way' while still in the shower",
  "Our group chat has been 'planning' a trip since 2021",
];

const DEFAULTS: TrollRequest = {
  situation: "",
  kind: "diss_track",
  style: "trap",
  intensity: "savage",
  delivery: "cocky",
  target: "",
  names: [],
  rapper_name: "",
  explicit: false,
};

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-3.5 py-2 text-sm font-medium transition ${
        active ? "border-volt bg-volt text-ink shadow-[0_0_20px_-6px] shadow-volt" : "border-line bg-panel/80 text-fg hover:border-grape/60"
      }`}
    >
      {children}
    </button>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-3 flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wide">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-grape text-xs text-white">{n}</span>
        {title}
      </p>
      {children}
    </div>
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
  return (
    <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
      {needsWords && words && (
        <>
          Jokes by <span className="font-mono text-fg">{words.model ?? words.provider}</span>
          {words.is_mock ? <Badge tone="mock">Mock, not real AI</Badge> : <Badge tone="grape">AI</Badge>}
        </>
      )}
      {music.capability && (
        <>
          · Beat by <span className="font-mono text-fg">{music.capability.provider}</span>
          {music.capability.is_ai ? <Badge tone="grape">AI</Badge> : <Badge>Built-in</Badge>}
        </>
      )}
      {needsWords && voice.capability && (
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

  /** Perform as a Troll Universe rapper: their name, genre, delivery and voice. */
  function pickRapper(id: string, list = rappers.data) {
    setRapperId(id);
    const rapper = list?.find((r) => r.id === id);
    if (!rapper) return;
    setForm((f) => ({ ...f, rapper_name: rapper.name, delivery: rapper.delivery, style: rapper.style, voice: rapper.voice ?? f.voice }));
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
  // Rotates on the client only, so server and client render the same first placeholder.
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setPlaceholderIndex((i) => (i + 1) % PLACEHOLDERS.length), 4000);
    return () => clearInterval(timer);
  }, []);
  const placeholder = PLACEHOLDERS[placeholderIndex];
  const runner = useJobRunner();
  const resultRef = useRef<HTMLDivElement>(null);

  const set = <K extends keyof TrollRequest>(key: K, value: TrollRequest[K]) => setForm((f) => ({ ...f, [key]: value }));
  const beatOnly = form.kind === "funny_beat";
  const styles = STYLES.filter((s) => beatOnly || !s.beatOnly);
  const ready = form.situation.trim().length >= 3 && (form.kind !== "group_roast" || namesText.split(",").some((n) => n.trim()));

  async function generate(projectId: string | null) {
    const request: TrollRequest = {
      ...form,
      situation: form.situation.trim(),
      target: form.target?.trim() || null,
      rapper_name: form.rapper_name?.trim() || null,
      names: form.kind === "group_roast" ? namesText.split(",").map((n) => n.trim()).filter(Boolean) : [],
      style: !beatOnly && STYLES.find((s) => s.id === form.style)?.beatOnly ? "trap" : form.style,
      inside_jokes: jokesText.split("\n").map((j) => j.trim()).filter(Boolean).slice(0, 5),
      voice: form.voice || null,
      voice_b: form.voice_b || null,
    };
    setSteps(planSteps(request.kind, { video: withVideo }));
    setResult(null);
    resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    const done = await runner.run(() => api.troll(request, projectId, { with_video: withVideo && form.kind !== "meme_video" }));
    if (done) {
      setResult(done);
      setLastProject(done.project_id);
    }
  }

  async function remix(assetId: string, changes: RemixChanges) {
    if (!result) return;
    const kind = KINDS.find((k) => k.id === form.kind)?.id ?? "diss_track";
    setSteps(planSteps(kind, { reuseLyrics: kind !== "funny_beat", rewrite: !!(changes.instruction || changes.delivery || changes.intensity || changes.regenerate_sections?.length) }));
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
      intensity: template.intensity,
      delivery: template.delivery,
    }));
    setResult(null);
  }

  async function randomize() {
    setHelperError(null);
    try {
      const idea = await api.randomTroll();
      setForm((f) => ({ ...f, ...idea, target: idea.target ?? "", rapper_name: idea.rapper_name ?? "" }));
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
    <div className="space-y-10">
      <section className="rise">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.25em] text-grape">Roast it. Rap it. Release it.</p>
        <h1 className="font-display text-4xl font-black leading-[1.02] tracking-tight sm:text-6xl">
          WHO ARE WE
          <br />
          <span className="text-gradient">ROASTING?</span>
        </h1>
        <p className="mt-4 max-w-xl text-base text-muted sm:text-lg">
          Type what your friend did. Pick a vibe. Hit the button. Send the result to the group chat.
        </p>
      </section>

      <form
        className="space-y-8"
        onSubmit={(event) => {
          event.preventDefault();
          if (ready && !runner.busy) generate(null);
        }}
      >
        <Step n={1} title="Spill the tea">
          <textarea
            value={form.situation}
            onChange={(e) => set("situation", e.target.value)}
            placeholder={placeholder}
            aria-label="What did they do?"
            rows={3}
            maxLength={600}
            className="control !rounded-2xl !p-4 !text-lg leading-snug"
          />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              value={form.target ?? ""}
              onChange={(e) => set("target", e.target.value)}
              placeholder="Their name (optional)"
              aria-label="Their name"
              maxLength={40}
              className="control !w-auto min-w-0 flex-1 sm:max-w-xs"
            />
            <Button onClick={randomize}>
              <Dices size={16} /> Random troll
            </Button>
          </div>
          {form.kind === "group_roast" && (
            <input
              value={namesText}
              onChange={(e) => setNamesText(e.target.value)}
              placeholder="Everyone in the chat, separated by commas: Dave, Sam, Priya"
              aria-label="Names in the group chat"
              className="control mt-2"
            />
          )}
        </Step>

        {!!templates.data?.length && (
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted">Or start from a classic</p>
            <div className="-mx-4 flex snap-x gap-2 overflow-x-auto px-4 pb-2 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0">
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

        <Step n={2} title="What are we making?">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {KINDS.map((kind) => {
              const active = form.kind === kind.id;
              return (
                <button
                  key={kind.id}
                  type="button"
                  onClick={() => set("kind", kind.id)}
                  aria-pressed={active}
                  className={`rounded-2xl border p-3 text-left transition sm:p-4 ${
                    active ? "border-volt bg-volt/10 shadow-[0_0_30px_-12px] shadow-volt" : "border-line bg-panel/80 hover:border-grape/60"
                  }`}
                >
                  <span className="text-2xl" aria-hidden>
                    {kind.emoji}
                  </span>
                  <span className="mt-1 block font-display text-sm font-bold">{kind.label}</span>
                  <span className="mt-0.5 block text-xs leading-snug text-muted">{kind.blurb}</span>
                </button>
              );
            })}
          </div>
        </Step>

        <Step n={3} title="Pick the vibe">
          <div className="flex flex-wrap gap-2">
            {styles.map((style) => (
              <Chip key={style.id} active={form.style === style.id} onClick={() => set("style", style.id)}>
                <span aria-hidden>{style.emoji}</span> {style.label}
              </Chip>
            ))}
          </div>
          {!beatOnly && (
            <div className="mt-4 grid grid-cols-3 gap-2 sm:max-w-lg">
              {INTENSITIES.map((level) => {
                const active = form.intensity === level.id;
                return (
                  <button
                    key={level.id}
                    type="button"
                    onClick={() => set("intensity", level.id)}
                    aria-pressed={active}
                    className={`rounded-xl border px-2 py-2.5 text-center transition ${
                      active
                        ? level.id === "brutal"
                          ? "border-danger bg-danger/15"
                          : "border-volt bg-volt/10"
                        : "border-line bg-panel/80 hover:border-grape/60"
                    }`}
                  >
                    <span className="block text-xl" aria-hidden>
                      {level.emoji}
                    </span>
                    <span className="block text-sm font-bold">{level.label}</span>
                    <span className="block text-[11px] text-muted">{level.blurb}</span>
                  </button>
                );
              })}
            </div>
          )}

          <button
            type="button"
            onClick={() => setMore(!more)}
            aria-expanded={more}
            className="mt-4 inline-flex items-center gap-1 text-sm text-muted hover:text-fg"
          >
            <ChevronDown size={15} className={`transition ${more ? "rotate-180" : ""}`} /> More fun settings
          </button>
          {more && (
            <div className="mt-3 space-y-4 rounded-2xl border border-line bg-panel/60 p-4">
              {!beatOnly && (
                <div>
                  <p className="mb-2 text-xs font-medium text-muted">Delivery</p>
                  <div className="flex flex-wrap gap-2">
                    {DELIVERIES.map((d) => (
                      <Chip key={d.id} active={form.delivery === d.id} onClick={() => set("delivery", d.id)}>
                        {d.label}
                      </Chip>
                    ))}
                  </div>
                </div>
              )}
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
              <div>
                <p className="mb-2 text-xs font-medium text-muted">Your rapper name</p>
                <div className="flex flex-wrap gap-2">
                  <input
                    value={form.rapper_name ?? ""}
                    onChange={(e) => set("rapper_name", e.target.value)}
                    placeholder="Leave empty for a surprise"
                    maxLength={40}
                    aria-label="Your rapper name"
                    className="control !w-auto min-w-0 flex-1 sm:max-w-xs"
                  />
                  <Button onClick={newRapperName}>
                    <Dices size={15} /> Name me
                  </Button>
                </div>
              </div>
              {!beatOnly && (
                <div>
                  <p className="mb-2 text-xs font-medium text-muted">Inside jokes (one per line, up to 5)</p>
                  <textarea
                    value={jokesText}
                    onChange={(e) => setJokesText(e.target.value)}
                    rows={2}
                    placeholder={"the kebab incident\nthat time with the karaoke machine"}
                    aria-label="Inside jokes"
                    className="control"
                  />
                </div>
              )}
              {!beatOnly && !!stock.data?.voices.length && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block text-xs font-medium text-muted">
                    {form.kind === "rap_battle" ? "Your voice" : "Voice"}
                    <select className="control mt-1" value={form.voice ?? ""} onChange={(e) => set("voice", e.target.value || null)}>
                      <option value="">Default</option>
                      {stock.data.voices.map((v) => (
                        <option key={v} value={v}>{v}</option>
                      ))}
                    </select>
                  </label>
                  {form.kind === "rap_battle" && (
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
                </div>
              )}
              {!beatOnly && (
                <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={!!form.explicit} onChange={(e) => set("explicit", e.target.checked)} className="accent-volt" />
                    Uncensored (swearing allowed)
                  </label>
                  {form.kind !== "meme_video" && (
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={withVideo} onChange={(e) => setWithVideo(e.target.checked)} className="accent-volt" />
                      Also make a meme video
                    </label>
                  )}
                </div>
              )}
            </div>
          )}
        </Step>

        {helperError && <Notice>{helperError}</Notice>}

        <div className="space-y-3">
          <button
            type="submit"
            disabled={!ready || runner.busy}
            className="group flex w-full items-center justify-center gap-3 rounded-2xl bg-volt px-6 py-5 font-display text-xl font-black uppercase tracking-wide text-ink shadow-[0_0_40px_-10px] shadow-volt transition hover:scale-[1.01] hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100 sm:text-2xl"
          >
            <Flame size={26} className="transition group-hover:rotate-12" />
            {runner.busy ? "Cooking…" : "Generate"}
          </button>
          <Engines kind={form.kind} />
        </div>
      </form>

      <div ref={resultRef} className="scroll-mt-20 space-y-4">
        {(runner.busy || runner.error) && <TrollProgress runner={runner} steps={steps} />}
        {result && !runner.busy && (
          <TrollResult job={result} regenerating={runner.busy} onRegenerate={() => generate(lastProject)} onRemix={remix} />
        )}
      </div>

      <section>
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 className="font-display text-xl font-black uppercase tracking-tight">Recent trolls</h2>
          <Link href="/projects" className="text-sm text-muted hover:text-fg">
            My Trolls →
          </Link>
        </div>
        <RecentTrolls refreshKey={result?.id ?? null} />
      </section>
    </div>
  );
}
