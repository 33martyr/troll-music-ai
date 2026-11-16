"use client";

import {
  Check,
  Copy,
  Download,
  Drum,
  Flame,
  History,
  Laugh,
  Mic,
  Music,
  PenLine,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
  Upload,
  Wand2,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ProviderBanner, useTextProvider } from "@/components/ProviderBanner";
import { Badge, Button, ButtonLink, Card, Empty, Equalizer, Field, Notice, PageHeader } from "@/components/ui";
import { api, download, errorMessage, waitForJob } from "@/lib/api";
import { formatWhen, humanize, useLoad } from "@/lib/hooks";
import type { Asset, Job, Lyrics, LyricsAsset, LyricsRequest, SectionType } from "@/lib/types";

const DEFAULT_REQUEST: LyricsRequest = {
  prompt: "",
  genre: "trap",
  mood: "playful",
  language: "English",
  style: "troll",
  troll_intensity: 3,
  explicit: false,
  length: "medium",
  verses: 2,
  chorus_style: "catchy",
  rhyme_complexity: "moderate",
  include_bridge: false,
  persona: null,
};

const INTENSITY = ["", "Gentle tease", "Cheeky", "Proper roast", "Heavy roast", "Maximum troll"];

interface DraftSection {
  id: string;
  type: SectionType;
  label: string;
  text: string;
}
interface Draft {
  title: string;
  sections: DraftSection[];
}

const toDraft = (lyrics: Lyrics): Draft => ({
  title: lyrics.title,
  sections: lyrics.sections.map((s) => ({ id: s.id, type: s.type, label: s.label, text: s.lines.join("\n") })),
});
const toLines = (text: string) => text.split("\n").map((line) => line.trim()).filter(Boolean);
const fingerprint = (draft: Draft) =>
  JSON.stringify([draft.title.trim(), draft.sections.map((s) => [s.label.trim(), toLines(s.text)])]);

export default function LyricsPage() {
  const router = useRouter();
  const params = useSearchParams();
  const assetParam = params.get("asset");

  const options = useLoad(api.lyricsOptions);
  const projects = useLoad(api.projects);
  const provider = useTextProvider();

  const [form, setForm] = useState<LyricsRequest>({ ...DEFAULT_REQUEST, prompt: params.get("prompt") ?? "" });
  const [projectId, setProjectId] = useState(params.get("project") ?? "");
  const [asset, setAsset] = useState<LyricsAsset | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [history, setHistory] = useState<Asset[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [rhymeScheme, setRhymeScheme] = useState("ABAB");
  const [instruction, setInstruction] = useState("");
  const [importTitle, setImportTitle] = useState("");
  const [importText, setImportText] = useState("");

  const set = <K extends keyof LyricsRequest>(key: K, value: LyricsRequest[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  function show(next: LyricsAsset, syncUrl = true) {
    setAsset(next);
    setDraft(next.content ? toDraft(next.content) : null);
    api.assetHistory(next.id).then(setHistory, () => setHistory([]));
    if (syncUrl) router.replace(`/lyrics?asset=${next.id}`, { scroll: false });
  }

  // Open the lyrics named in the URL (links from projects, reloads, back/forward).
  useEffect(() => {
    if (!assetParam || assetParam === asset?.id) return;
    let alive = true;
    api.asset<Lyrics>(assetParam).then(
      (loaded) => {
        if (!alive) return;
        show(loaded, false);
        if (loaded.params) setForm({ ...DEFAULT_REQUEST, ...(loaded.params as Partial<LyricsRequest>) });
        setProjectId(loaded.project_id ?? "");
      },
      (reason) => alive && setError(errorMessage(reason)),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetParam]);

  const dirty = !!(asset?.content && draft && fingerprint(draft) !== fingerprint(toDraft(asset.content)));
  const canGenerate = !!provider.text?.configured;
  const working = busy !== null;

  /** Persist unsaved edits first so AI actions build on what the user sees. */
  async function ensureSaved(): Promise<LyricsAsset> {
    if (!asset || !draft) throw new Error("Nothing to save.");
    if (!dirty) return asset;
    const saved = await api.saveLyrics(
      asset.id,
      draft.title,
      draft.sections.map((s) => ({ id: s.id, type: s.type, label: s.label, lines: toLines(s.text) })),
    );
    show(saved);
    return saved;
  }

  async function act(tag: string, action: () => Promise<void>) {
    setBusy(tag);
    setError(null);
    try {
      await action();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
      setJob(null);
    }
  }

  const runJob = (tag: string, start: () => Promise<Job>) =>
    act(tag, async () => {
      const finished = await waitForJob(await start(), setJob);
      show(await api.asset<Lyrics>(finished.result_asset_id!));
    });

  const generate = () =>
    runJob("generate", () =>
      api.generateLyrics({ ...form, prompt: form.prompt.trim(), persona: form.persona?.trim() || null }, projectId || null),
    );
  const regenerateSection = (sectionId: string) =>
    runJob(`section:${sectionId}`, async () => api.regenerateSection((await ensureSaved()).id, sectionId));
  const rewrite = (mode: string, extra: { rhyme_scheme?: string; instruction?: string } = {}) =>
    runJob(`rewrite:${mode}`, async () => api.rewriteLyrics((await ensureSaved()).id, { mode, ...extra }));
  const exportAs = (format: "txt" | "md") =>
    act(`export:${format}`, async () => {
      const saved = await ensureSaved();
      await download(`/api/assets/${saved.id}/export?format=${format}`, `lyrics.${format}`);
    });

  const updateSection = (id: string, patch: Partial<DraftSection>) =>
    setDraft((current) =>
      current && { ...current, sections: current.sections.map((s) => (s.id === id ? { ...s, ...patch } : s)) },
    );

  return (
    <>
      <PageHeader eyebrow="Generator" title="Generate Lyrics">
        Describe the song. You get a title, verses, a chorus and beat suggestions, and you can rewrite any part
        without losing the rest.
      </PageHeader>

      <div className="mb-6">
        <ProviderBanner {...provider} />
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
        {/* ------------------------------ form ------------------------------ */}
        <Card className="p-5 lg:sticky lg:top-6">
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              generate();
            }}
          >
            <Field label="What's the song about?">
              <textarea
                className="control min-h-28 resize-y"
                value={form.prompt}
                onChange={(event) => set("prompt", event.target.value)}
                placeholder="A funny diss track about a fake millionaire who rents a Lambo for Instagram…"
                maxLength={2000}
                required
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Genre">
                <input className="control" list="genres" value={form.genre} onChange={(e) => set("genre", e.target.value)} />
                <datalist id="genres">{options.data?.genres.map((g) => <option key={g} value={g} />)}</datalist>
              </Field>
              <Field label="Mood">
                <input className="control" list="moods" value={form.mood} onChange={(e) => set("mood", e.target.value)} />
                <datalist id="moods">{options.data?.moods.map((m) => <option key={m} value={m} />)}</datalist>
              </Field>
              <Field label="Lyric style">
                <select className="control" value={form.style} onChange={(e) => set("style", e.target.value)}>
                  {(options.data?.styles ?? [form.style]).map((s) => (
                    <option key={s} value={s}>{humanize(s)}</option>
                  ))}
                </select>
              </Field>
              <Field label="Language">
                <input className="control" value={form.language} onChange={(e) => set("language", e.target.value)} />
              </Field>
            </div>

            <Field label="Troll intensity" hint={INTENSITY[form.troll_intensity]}>
              <input
                type="range"
                min={1}
                max={5}
                value={form.troll_intensity}
                onChange={(e) => set("troll_intensity", Number(e.target.value))}
                className="w-full accent-volt"
              />
            </Field>

            <details className="group rounded-xl border border-line">
              <summary className="cursor-pointer select-none px-3 py-2.5 text-sm text-muted hover:text-fg">
                Structure and rhymes
              </summary>
              <div className="grid grid-cols-2 gap-3 border-t border-line p-3">
                <Field label="Length">
                  <select className="control" value={form.length} onChange={(e) => set("length", e.target.value)}>
                    {(options.data?.lengths ?? [form.length]).map((v) => <option key={v} value={v}>{humanize(v)}</option>)}
                  </select>
                </Field>
                <Field label="Verses">
                  <select className="control" value={form.verses} onChange={(e) => set("verses", Number(e.target.value))}>
                    {[1, 2, 3, 4].map((n) => <option key={n}>{n}</option>)}
                  </select>
                </Field>
                <Field label="Chorus">
                  <select className="control" value={form.chorus_style} onChange={(e) => set("chorus_style", e.target.value)}>
                    {(options.data?.chorus_styles ?? [form.chorus_style]).map((v) => <option key={v} value={v}>{humanize(v)}</option>)}
                  </select>
                </Field>
                <Field label="Rhymes">
                  <select className="control" value={form.rhyme_complexity} onChange={(e) => set("rhyme_complexity", e.target.value)}>
                    {(options.data?.rhyme_complexities ?? [form.rhyme_complexity]).map((v) => <option key={v} value={v}>{humanize(v)}</option>)}
                  </select>
                </Field>
                <div className="col-span-2">
                  <Field label="Persona" hint="optional, fictional">
                    <input
                      className="control"
                      value={form.persona ?? ""}
                      onChange={(e) => set("persona", e.target.value)}
                      placeholder="e.g. DJ Budget, a broke hype man"
                      maxLength={200}
                    />
                  </Field>
                </div>
                <label className="flex items-center gap-2 text-sm text-muted">
                  <input type="checkbox" className="accent-volt" checked={form.include_bridge} onChange={(e) => set("include_bridge", e.target.checked)} />
                  Add a bridge
                </label>
                <label className="flex items-center gap-2 text-sm text-muted">
                  <input type="checkbox" className="accent-volt" checked={form.explicit} onChange={(e) => set("explicit", e.target.checked)} />
                  Explicit language
                </label>
              </div>
            </details>

            <Field label="Save to">
              <select className="control" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                <option value="">No project (library)</option>
                {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>

            <Button
              type="submit"
              variant="primary"
              className="w-full"
              busy={busy === "generate"}
              disabled={!canGenerate || working || form.prompt.trim().length < 3}
            >
              {busy !== "generate" && <Sparkles size={16} />}
              {asset ? "Generate new lyrics" : "Generate lyrics"}
            </Button>
            {!canGenerate && !provider.error && provider.text && (
              <p className="text-center text-xs text-muted">Needs a text provider. See the note above.</p>
            )}
          </form>

          <details className="mt-5 rounded-xl border border-line" open={!canGenerate && !!provider.text}>
            <summary className="cursor-pointer select-none px-3 py-2.5 text-sm text-muted hover:text-fg">
              Already have lyrics? Paste them
            </summary>
            <form
              className="space-y-3 border-t border-line p-3"
              onSubmit={(event) => {
                event.preventDefault();
                act("import", async () => {
                  const imported = await api.importLyrics(importTitle.trim() || "Untitled", importText, projectId || null);
                  setImportText("");
                  setImportTitle("");
                  show(imported);
                });
              }}
            >
              <input aria-label="Title" className="control" value={importTitle} maxLength={120} placeholder="Title" onChange={(e) => setImportTitle(e.target.value)} />
              <textarea
                aria-label="Your lyrics"
                className="control min-h-32 resize-y"
                value={importText}
                maxLength={20000}
                placeholder={"[Verse 1]\nFirst line\nSecond line\n\n[Chorus]\nHook line"}
                onChange={(e) => setImportText(e.target.value)}
              />
              <Button type="submit" size="sm" busy={busy === "import"} disabled={working || importText.trim().length < 3}>
                <Upload size={13} /> Import lyrics
              </Button>
              <p className="text-xs text-muted">Headers in square brackets mark sections. No AI is used.</p>
            </form>
          </details>
        </Card>

        {/* ----------------------------- result ----------------------------- */}
        <div className="min-w-0 space-y-4">
          {error && <Notice>{error}</Notice>}

          {job && (
            <Card className="p-5" aria-live="polite">
              <div className="mb-3 flex items-center justify-between text-sm">
                <span className="flex items-center gap-3">
                  <Equalizer /> {job.stage}
                </span>
                <span className="font-mono text-xs text-muted">{Math.round(job.progress * 100)}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-line">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-grape to-volt transition-all duration-500"
                  style={{ width: `${Math.max(4, job.progress * 100)}%` }}
                />
              </div>
            </Card>
          )}

          {!asset && !job && (
            <Empty title="Your lyrics will appear here">
              <PenLine size={22} className="mx-auto mb-3 text-grape" />
              Fill in the idea on the left and generate. Everything you generate is saved, with its full version
              history.
            </Empty>
          )}

          {asset && draft && (
            <>
              <Card className="rise p-5">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  {asset.is_mock && <Badge tone="mock">Mock output · not AI</Badge>}
                  <Badge tone="grape">v{asset.version}</Badge>
                  <Badge>{humanize(asset.origin)}</Badge>
                  {!asset.is_latest && <Badge tone="danger">Older version</Badge>}
                  {dirty && <Badge tone="mock">Unsaved edits</Badge>}
                  {asset.approved && <Badge tone="live"><Check size={11} /> Approved</Badge>}
                  <span className="ml-auto text-xs text-muted">{formatWhen(asset.created_at)}</span>
                </div>
                <input
                  aria-label="Song title"
                  value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                  maxLength={120}
                  className="w-full rounded-lg bg-transparent font-display text-2xl font-extrabold tracking-tight outline-none focus:bg-white/5 sm:text-3xl"
                />
                <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted">
                  {asset.content?.suggested_bpm && <div><dt className="inline">BPM </dt><dd className="inline font-mono text-fg">{asset.content.suggested_bpm}</dd></div>}
                  {asset.content?.suggested_genre && <div><dt className="inline">Genre </dt><dd className="inline text-fg">{asset.content.suggested_genre}</dd></div>}
                  {asset.provider && <div><dt className="inline">Written by </dt><dd className="inline text-fg">{asset.is_mock ? "mock provider" : `${asset.model ?? asset.provider}`}</dd></div>}
                </dl>

                <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">
                  <Button size="sm" variant={dirty ? "primary" : "secondary"} disabled={!dirty || working} busy={busy === "save"} onClick={() => act("save", async () => void (await ensureSaved()))}>
                    <Save size={13} /> Save edits
                  </Button>
                  <Button
                    size="sm"
                    disabled={working}
                    onClick={() => act("approve", async () => {
                      const updated = await api.updateAsset(asset.id, { approved: !asset.approved });
                      setAsset({ ...asset, approved: updated.approved });
                    })}
                  >
                    <Check size={13} /> {asset.approved ? "Unapprove" : "Approve"}
                  </Button>
                  <Button size="sm" disabled={working} onClick={() => exportAs("txt")}><Download size={13} /> TXT</Button>
                  <Button size="sm" disabled={working} onClick={() => exportAs("md")}><Download size={13} /> Markdown</Button>
                  <Button
                    size="sm"
                    onClick={async () => {
                      const text = [draft.title, ...draft.sections.map((s) => `[${s.label}]\n${toLines(s.text).join("\n")}`)].join("\n\n");
                      await navigator.clipboard.writeText(text);
                      setCopied(true);
                      setTimeout(() => setCopied(false), 1500);
                    }}
                  >
                    <Copy size={13} /> {copied ? "Copied" : "Copy"}
                  </Button>
                  {history.length > 1 && (
                    <label className="ml-auto flex items-center gap-2 text-xs text-muted">
                      <History size={13} />
                      <select
                        aria-label="Version history"
                        className="control !w-auto !py-1.5 !text-xs"
                        value={asset.id}
                        disabled={working}
                        onChange={(e) => act("load", async () => show(await api.asset<Lyrics>(e.target.value)))}
                      >
                        {history.map((v) => (
                          <option key={v.id} value={v.id}>v{v.version} · {humanize(v.origin)}</option>
                        ))}
                      </select>
                    </label>
                  )}
                </div>
              </Card>

              <Card className="p-4">
                <p className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted">
                  <Wand2 size={13} className="text-grape" /> Rewrite the whole song
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <Button size="sm" disabled={!canGenerate || working} busy={busy === "rewrite:funnier"} onClick={() => rewrite("funnier")}>
                    <Laugh size={13} /> Funnier
                  </Button>
                  <Button size="sm" disabled={!canGenerate || working} busy={busy === "rewrite:more_savage"} onClick={() => rewrite("more_savage")}>
                    <Flame size={13} /> More savage
                  </Button>
                  <span className="flex items-center gap-1">
                    <select aria-label="Rhyme scheme" className="control !w-auto !py-1.5 !text-xs" value={rhymeScheme} onChange={(e) => setRhymeScheme(e.target.value)}>
                      {(options.data?.rhyme_schemes ?? [rhymeScheme]).map((s) => <option key={s}>{s}</option>)}
                    </select>
                    <Button size="sm" disabled={!canGenerate || working} busy={busy === "rewrite:rhyme_scheme"} onClick={() => rewrite("rhyme_scheme", { rhyme_scheme: rhymeScheme })}>
                      Change rhyme scheme
                    </Button>
                  </span>
                </div>
                <form
                  className="mt-3 flex gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (instruction.trim()) rewrite("custom", { instruction: instruction.trim() });
                  }}
                >
                  <input
                    className="control !py-1.5 !text-xs"
                    value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                    placeholder="Or tell it what to change: “more football references”"
                    maxLength={500}
                  />
                  <Button type="submit" size="sm" disabled={!canGenerate || working || !instruction.trim()} busy={busy === "rewrite:custom"}>
                    Rewrite
                  </Button>
                </form>
              </Card>

              {draft.sections.map((section) => (
                <Card key={section.id} className="p-4">
                  <div className="mb-2 flex items-center gap-2">
                    <input
                      aria-label="Section name"
                      value={section.label}
                      onChange={(e) => updateSection(section.id, { label: e.target.value })}
                      maxLength={60}
                      className={`w-32 rounded bg-transparent font-display text-xs font-semibold uppercase tracking-wide outline-none focus:bg-white/5 ${
                        section.type === "chorus" ? "text-volt" : "text-grape"
                      }`}
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      className="ml-auto"
                      disabled={!canGenerate || working}
                      busy={busy === `section:${section.id}`}
                      onClick={() => regenerateSection(section.id)}
                    >
                      {busy !== `section:${section.id}` && <RefreshCw size={12} />}
                      {section.type === "chorus" ? "Rewrite chorus" : "Regenerate"}
                    </Button>
                  </div>
                  <textarea
                    aria-label={`${section.label} lyrics`}
                    value={section.text}
                    onChange={(e) => updateSection(section.id, { text: e.target.value })}
                    rows={Math.max(2, section.text.split("\n").length)}
                    className="w-full resize-none overflow-hidden rounded-lg bg-transparent text-[15px] leading-7 outline-none [field-sizing:content] focus:bg-white/[0.03]"
                  />
                </Card>
              ))}

              {!!asset.content?.beat_notes.length && (
                <Card className="p-4">
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Suggested beat</p>
                  <div className="flex flex-wrap gap-2">
                    {asset.content.beat_notes.map((note) => (
                      <span key={note} className="rounded-full border border-line bg-ink/50 px-3 py-1 text-xs text-muted">{note}</span>
                    ))}
                  </div>
                </Card>
              )}

              <Card className="p-4">
                <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">Next</p>
                <div className="flex flex-wrap gap-2">
                  <ButtonLink
                    size="sm"
                    href={`/beat?lyrics=${asset.id}${asset.content?.suggested_bpm ? `&bpm=${asset.content.suggested_bpm}` : ""}${asset.content?.suggested_genre ? `&genre=${encodeURIComponent(asset.content.suggested_genre)}` : ""}${asset.project_id ? `&project=${asset.project_id}` : ""}`}
                  >
                    <Drum size={13} /> Make a beat for it
                  </ButtonLink>
                  <ButtonLink size="sm" href={`/voice?lyrics=${asset.id}`}><Mic size={13} /> Hear it performed</ButtonLink>
                  <ButtonLink size="sm" variant="primary" href={`/song?lyrics=${asset.id}`}><Music size={13} /> Make it a song</ButtonLink>
                </div>
                {dirty && <p className="mt-2 text-xs text-amber">Save your edits first; the next steps use the saved version.</p>}
              </Card>

              <div className="flex justify-end">
                <Button
                  size="sm"
                  variant="danger"
                  disabled={working}
                  onClick={() => {
                    if (!confirm(`Delete “${asset.title}” and all ${history.length || 1} version(s)? This can't be undone.`)) return;
                    act("delete", async () => {
                      await api.deleteAsset(asset.id);
                      setAsset(null);
                      setDraft(null);
                      setHistory([]);
                      router.replace("/lyrics", { scroll: false });
                    });
                  }}
                >
                  <Trash2 size={13} /> Delete lyrics
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
