"use client";

import { Crown, Dices, Paintbrush, Plus, Swords, Trash2, Users } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { TrackPlayer } from "@/components/player";
import { JobStatus, useJobRunner } from "@/components/studio";
import { DELIVERIES, INTENSITIES, STYLES } from "@/components/troll";
import { Badge, Button, ButtonLink, Card, Empty, Equalizer, Notice } from "@/components/ui";
import { api, errorMessage, fileUrl } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Intensity, Rapper, RapperStats, Rivalry } from "@/lib/types";

const STAT_KEYS: (keyof RapperStats)[] = ["punchline", "flow", "comedy", "creativity", "reputation"];
const SONG_STYLES = STYLES.filter((s) => !s.beatOnly);

function OriginLabel({ rapper }: { rapper: Rapper }) {
  if (rapper.is_mock) return <Badge tone="mock">Mock profile</Badge>;
  if (rapper.origin.startsWith("ai")) return <Badge tone="grape">Invented by {rapper.model ?? rapper.provider}{rapper.origin.endsWith("+edited") ? " · edited" : ""}</Badge>;
  if (rapper.origin.startsWith("builtin")) return <Badge>Built-in word lists, not AI</Badge>;
  return <Badge>Written by you</Badge>;
}

/** The collectible card PNG, or a placeholder while it is missing. */
function CardImage({ rapper, className = "" }: { rapper: Rapper; className?: string }) {
  return rapper.card?.has_file ? (
    // eslint-disable-next-line @next/next/no-img-element -- served by the API with a signed URL
    <img src={fileUrl(rapper.card)} alt={`${rapper.name} collectible card`} className={`aspect-[5/7] w-full rounded-2xl object-cover ${className}`} />
  ) : (
    <div className={`flex aspect-[5/7] w-full items-center justify-center rounded-2xl bg-grape/15 text-5xl ${className}`}>🎤</div>
  );
}

// ---------------------------------- roster --------------------------------- //

function NewRapper({ onMade }: { onMade: (rapper: Rapper) => void }) {
  const [idea, setIdea] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function invent(text: string | null) {
    setBusy(true);
    setError(null);
    try {
      onMade(await api.generateRapper(text));
      setIdea("");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card className="space-y-3 p-4">
      <p className="font-display text-sm font-bold uppercase tracking-wide">Sign a new rapper</p>
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          invent(idea.trim() || null);
        }}
      >
        <input className="control flex-1" value={idea} maxLength={300} onChange={(e) => setIdea(e.target.value)} placeholder="A nervous accountant who raps only about taxes" aria-label="Rapper idea" />
        <Button type="submit" variant="primary" busy={busy}>
          {!busy && <Plus size={15} />} Invent
        </Button>
        <Button onClick={() => invent(null)} disabled={busy}>
          <Dices size={15} /> Surprise me
        </Button>
      </form>
      {error && <Notice>{error}</Notice>}
      <p className="text-xs text-muted">Every rapper is fictional and stays private to this app. Edit anything afterwards.</p>
    </Card>
  );
}

function Roster({ rappers, onOpen, onMade }: { rappers: Rapper[]; onOpen: (id: string) => void; onMade: (r: Rapper) => void }) {
  return (
    <div className="space-y-6">
      <NewRapper onMade={onMade} />
      {!rappers.length ? (
        <Empty title="Your universe is empty">Invent a rapper above. Two rappers make a rivalry.</Empty>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {rappers.map((rapper) => (
            <button key={rapper.id} type="button" onClick={() => onOpen(rapper.id)} className="group text-left">
              <CardImage rapper={rapper} className="transition group-hover:-translate-y-1 group-hover:shadow-xl group-hover:shadow-grape/20" />
              <p className="mt-2 truncate font-display text-sm font-bold">{rapper.name}</p>
              <p className="text-xs text-muted">
                {rapper.overall} OVR · {rapper.wins}W {rapper.losses}L {rapper.draws}D {rapper.titles.length ? "· 👑" : ""}
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ------------------------------- rapper detail ----------------------------- //

function RapperDetail({ id, onBack, onChanged }: { id: string; onBack: () => void; onChanged: () => void }) {
  const [rapper, setRapper] = useState<Rapper | null>(null);
  const [draft, setDraft] = useState<Rapper | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const painter = useJobRunner();
  const stock = useLoad(api.stockVoices);

  useEffect(() => {
    let live = true;
    api.rapper(id).then((r) => live && (setRapper(r), setDraft(r)), (reason) => live && setError(errorMessage(reason)));
    return () => {
      live = false;
    };
  }, [id]);

  if (error && !rapper) return <Notice>{error}</Notice>;
  if (!rapper || !draft) return <p className="text-sm text-muted"><Equalizer /> Loading…</p>;
  const set = <K extends keyof Rapper>(key: K, value: Rapper[K]) => setDraft({ ...draft, [key]: value });
  const dirty = JSON.stringify(draft) !== JSON.stringify(rapper);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const { name, personality, style, delivery, catchphrase, bio, stats, voice } = draft!;
      const saved = await api.updateRapper(id, { name, personality, style, delivery, catchphrase, bio, stats, voice });
      setRapper(saved);
      setDraft(saved);
      onChanged();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <button type="button" onClick={onBack} className="text-sm text-muted hover:text-fg">← Back to the roster</button>
      <div className="grid gap-6 md:grid-cols-[minmax(0,320px)_1fr]">
        <div className="space-y-3">
          <CardImage rapper={rapper} />
          <div className="flex flex-wrap gap-2">
            <Button
              busy={painter.busy}
              onClick={async () => {
                const done = await painter.run(() => api.paintRapper(id));
                if (done) {
                  const fresh = await api.rapper(id);
                  setRapper(fresh);
                  setDraft(fresh);
                  onChanged();
                }
              }}
            >
              {!painter.busy && <Paintbrush size={14} />} {rapper.avatar ? "Repaint portrait" : "Paint portrait"}
            </Button>
            {rapper.card && (
              <a href={fileUrl(rapper.card, true)} className="inline-flex items-center rounded-lg border border-line bg-raised px-4 py-2.5 text-sm hover:border-grape/60">
                Download card
              </a>
            )}
          </div>
          <JobStatus runner={painter} />
          {rapper.avatar && !rapper.avatar.is_ai && <p className="text-xs text-muted">Portrait drawn by the built-in card renderer (no AI image model is set).</p>}
        </div>

        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <OriginLabel rapper={rapper} />
            <Badge>{rapper.wins}W {rapper.losses}L {rapper.draws}D</Badge>
            {rapper.titles.map((t) => (
              <Badge key={t} tone="live"><Crown size={11} /> {t}</Badge>
            ))}
          </div>
          <input className="control !text-2xl font-display font-black" value={draft.name} maxLength={40} onChange={(e) => set("name", e.target.value)} aria-label="Stage name" />
          <label className="block text-xs font-medium text-muted">
            Catchphrase
            <input className="control mt-1" value={draft.catchphrase} maxLength={120} onChange={(e) => set("catchphrase", e.target.value)} />
          </label>
          <label className="block text-xs font-medium text-muted">
            Personality
            <input className="control mt-1" value={draft.personality} maxLength={300} onChange={(e) => set("personality", e.target.value)} />
          </label>
          <label className="block text-xs font-medium text-muted">
            Biography
            <textarea className="control mt-1" rows={3} value={draft.bio} maxLength={800} onChange={(e) => set("bio", e.target.value)} />
          </label>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block text-xs font-medium text-muted">
              Genre
              <select className="control mt-1" value={draft.style} onChange={(e) => set("style", e.target.value)}>
                {SONG_STYLES.map((s) => <option key={s.id} value={s.id}>{s.emoji} {s.label}</option>)}
              </select>
            </label>
            <label className="block text-xs font-medium text-muted">
              Signature delivery
              <select className="control mt-1" value={draft.delivery} onChange={(e) => set("delivery", e.target.value)}>
                {DELIVERIES.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
              </select>
            </label>
            <label className="block text-xs font-medium text-muted">
              Voice
              <select className="control mt-1" value={draft.voice ?? ""} onChange={(e) => set("voice", e.target.value || null)}>
                <option value="">Default</option>
                {stock.data?.voices.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </label>
          </div>
          <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {STAT_KEYS.map((stat) => (
              <label key={stat} className="block text-xs font-medium capitalize text-muted">
                <span className="flex justify-between">{stat} <span className="font-mono text-fg">{draft.stats[stat]}</span></span>
                <input type="range" min={1} max={99} value={draft.stats[stat]} className="w-full accent-volt" onChange={(e) => set("stats", { ...draft.stats, [stat]: Number(e.target.value) })} />
              </label>
            ))}
          </div>
          <p className="text-xs text-muted">Stats are for fun and made up. Wins, losses and titles come from settled battles.</p>
          {error && <Notice>{error}</Notice>}
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" disabled={!dirty} busy={saving} onClick={save}>Save and reprint card</Button>
            <ButtonLink href={`/?rapper=${rapper.id}`}>Roast someone as {rapper.name}</ButtonLink>
            <Button
              variant="danger"
              onClick={async () => {
                if (!confirm(`Retire ${rapper.name}? Their rivalries go too; tracks already made stay in My Trolls.`)) return;
                await api.deleteRapper(id);
                onChanged();
                onBack();
              }}
            >
              <Trash2 size={14} /> Retire
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// --------------------------------- rivalries ------------------------------- //

function NewRivalry({ rappers, onMade }: { rappers: Rapper[]; onMade: (r: Rivalry) => void }) {
  const [a, setA] = useState(rappers[0]?.id ?? "");
  const [b, setB] = useState(rappers[1]?.id ?? "");
  const [tagline, setTagline] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (rappers.length < 2) return <Notice tone="info">Sign at least two rappers to start a rivalry.</Notice>;
  return (
    <Card className="space-y-3 p-4">
      <p className="font-display text-sm font-bold uppercase tracking-wide">Start a beef</p>
      <div className="grid gap-2 sm:grid-cols-[1fr_auto_1fr]">
        <select className="control" value={a} onChange={(e) => setA(e.target.value)} aria-label="First rapper">
          {rappers.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        <span className="self-center text-center font-display font-black text-volt">VS</span>
        <select className="control" value={b} onChange={(e) => setB(e.target.value)} aria-label="Second rapper">
          {rappers.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
      </div>
      <input className="control" value={tagline} maxLength={300} onChange={(e) => setTagline(e.target.value)} placeholder="What started it? “One of them returned a borrowed mic… broken.”" aria-label="Rivalry tagline" />
      {error && <Notice>{error}</Notice>}
      <Button
        variant="primary"
        disabled={!a || !b}
        onClick={async () => {
          setError(null);
          try {
            onMade(await api.createRivalry(a, b, tagline.trim()));
          } catch (reason) {
            setError(errorMessage(reason));
          }
        }}
      >
        <Swords size={15} /> Start the rivalry
      </Button>
    </Card>
  );
}

function RivalryDetail({ id, onBack, onChanged }: { id: string; onBack: () => void; onChanged: () => void }) {
  const [rivalry, setRivalry] = useState<Rivalry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [style, setStyle] = useState<string>("");
  const [intensity, setIntensity] = useState<Intensity>("savage");
  const [video, setVideo] = useState(false);
  const [posterUrl, setPosterUrl] = useState<string | null>(null);
  const runner = useJobRunner();

  const reload = () => api.rivalry(id).then(setRivalry, (reason) => setError(errorMessage(reason)));
  useEffect(() => {
    let live = true;
    api.rivalry(id).then((r) => live && setRivalry(r), (reason) => live && setError(errorMessage(reason)));
    return () => {
      live = false;
    };
  }, [id]);

  if (error && !rivalry) return <Notice>{error}</Notice>;
  if (!rivalry) return <p className="text-sm text-muted"><Equalizer /> Loading…</p>;
  const { rapper_a: a, rapper_b: b, record } = rivalry;
  const champion = rivalry.champion_id === a.id ? a : rivalry.champion_id === b.id ? b : null;
  const nameOf = (rapperId: string | null) => (rapperId === a.id ? a.name : rapperId === b.id ? b.name : "Draw");

  async function make(kind: "battle" | "diss", fromId?: string) {
    setError(null);
    const done = await runner.run(() => api.rivalryTrack(id, { kind, from_id: fromId ?? null, style: style || null, intensity, with_video: video }));
    if (done) {
      await reload();
      onChanged();
    }
  }

  async function settle(songId: string, winner: string | null) {
    setError(null);
    try {
      setRivalry(await api.settleBattle(id, songId, winner));
      onChanged();
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }

  return (
    <div className="space-y-8">
      <button type="button" onClick={onBack} className="text-sm text-muted hover:text-fg">← All rivalries</button>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 sm:gap-6">
        <div className="text-center">
          <CardImage rapper={a} className="mx-auto max-w-[220px]" />
          <p className="mt-2 font-display font-bold">{a.name} {champion?.id === a.id && "👑"}</p>
        </div>
        <div className="text-center">
          <p className="font-mono text-3xl font-black sm:text-5xl">{record.a}<span className="text-muted"> - </span>{record.b}</p>
          {record.draws > 0 && <p className="text-xs text-muted">{record.draws} draw{record.draws === 1 ? "" : "s"}</p>}
          <p className="mt-2 text-xs text-muted">{champion ? `${champion.name} is champion` : `First to ${rivalry.champion_wins_needed} wins is champion`}</p>
        </div>
        <div className="text-center">
          <CardImage rapper={b} className="mx-auto max-w-[220px]" />
          <p className="mt-2 font-display font-bold">{b.name} {champion?.id === b.id && "👑"}</p>
        </div>
      </div>
      {rivalry.tagline && <p className="text-center italic text-muted">“{rivalry.tagline}”</p>}

      <Card className="space-y-4 p-4">
        <p className="font-display text-sm font-bold uppercase tracking-wide">Next round</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => setStyle("")} aria-pressed={!style} className={`rounded-full border px-3 py-1.5 text-xs ${!style ? "border-volt bg-volt text-ink" : "border-line"}`}>
            {a.name}&apos;s genre
          </button>
          {SONG_STYLES.map((s) => (
            <button key={s.id} type="button" onClick={() => setStyle(s.id)} aria-pressed={style === s.id} className={`rounded-full border px-3 py-1.5 text-xs ${style === s.id ? "border-volt bg-volt text-ink" : "border-line"}`}>
              {s.emoji} {s.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {INTENSITIES.map((level) => (
            <button key={level.id} type="button" onClick={() => setIntensity(level.id)} aria-pressed={intensity === level.id} className={`rounded-xl border px-3 py-1.5 text-sm ${intensity === level.id ? "border-volt bg-volt/10" : "border-line"}`}>
              {level.emoji} {level.label}
            </button>
          ))}
          <label className="ml-2 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={video} onChange={(e) => setVideo(e.target.checked)} className="accent-volt" /> Battle video
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" disabled={runner.busy} onClick={() => make("battle")}><Swords size={15} /> Battle</Button>
          <Button disabled={runner.busy} onClick={() => make("diss", a.id)}>{a.name} disses {b.name}</Button>
          <Button disabled={runner.busy} onClick={() => make("diss", b.id)}>{b.name} disses {a.name}</Button>
          <Button
            onClick={async () => {
              try {
                setPosterUrl(fileUrl(await api.rivalryPoster(id)));
              } catch (reason) {
                setError(errorMessage(reason));
              }
            }}
          >
            Rivalry poster
          </Button>
        </div>
        <JobStatus runner={runner} />
        {/* eslint-disable-next-line @next/next/no-img-element -- served by the API with a signed URL */}
        {posterUrl && <img src={posterUrl} alt="Rivalry poster" className="max-h-[70vh] rounded-xl" />}
      </Card>

      {error && <Notice>{error}</Notice>}

      <section className="space-y-3">
        <h2 className="font-display text-xl font-black uppercase">Battle history</h2>
        {!rivalry.history.length && <p className="text-sm text-muted">No tracks yet. Start a battle above.</p>}
        {rivalry.history.map((item) => (
          <Card key={item.track.id} className="space-y-3 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <p className="min-w-0 flex-1 truncate font-semibold">{item.track.title}</p>
              <Badge>{item.kind === "rap_battle" ? "Battle" : "Diss track"}</Badge>
              {item.settled && <Badge tone="live">{item.winner_id ? `${nameOf(item.winner_id)} won` : "Draw"} · by {item.source}</Badge>}
            </div>
            {item.track.has_file && <TrackPlayer src={fileUrl(item.track)} label={item.track.title} knownDuration={item.track.duration_seconds} lazy />}
            {item.kind === "rap_battle" && (
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Link href={`/battle?id=${item.track.id}`} className="text-muted underline hover:text-fg">Judges & votes</Link>
                <span className="text-muted">·</span>
                <Button size="sm" onClick={() => settle(item.track.id, null)}>Settle by votes or judges</Button>
                <Button size="sm" variant="ghost" onClick={() => settle(item.track.id, a.id)}>{a.name} won</Button>
                <Button size="sm" variant="ghost" onClick={() => settle(item.track.id, "draw")}>Draw</Button>
                <Button size="sm" variant="ghost" onClick={() => settle(item.track.id, b.id)}>{b.name} won</Button>
              </div>
            )}
          </Card>
        ))}
      </section>

      <Button
        variant="danger"
        size="sm"
        onClick={async () => {
          if (!confirm("End this rivalry? Its record is deleted; tracks stay in My Trolls.")) return;
          await api.deleteRivalry(id);
          onChanged();
          onBack();
        }}
      >
        <Trash2 size={13} /> End rivalry
      </Button>
    </div>
  );
}

// ----------------------------------- page ---------------------------------- //

export default function UniversePage() {
  const params = useSearchParams();
  const router = useRouter();
  const rappers = useLoad(api.rappers);
  const rivalries = useLoad(api.rivalries);
  const rapperId = params.get("rapper");
  const rivalryId = params.get("rivalry");
  const tab = params.get("tab") === "rivalries" ? "rivalries" : "roster";
  const go = (query: string) => router.push(`/universe${query}`, { scroll: false });
  const refresh = () => {
    rappers.reload();
    rivalries.reload();
  };

  return (
    <div className="space-y-8">
      <header className="rise">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.25em] text-grape">Troll Universe</p>
        <h1 className="font-display text-4xl font-black tracking-tight sm:text-5xl">YOUR RAP CINEMATIC UNIVERSE.</h1>
        <p className="mt-3 max-w-xl text-muted">Invent fictional rappers, collect their cards, start rivalries and crown champions. Private to you.</p>
      </header>

      {rapperId ? (
        <RapperDetail key={rapperId} id={rapperId} onBack={() => go("")} onChanged={refresh} />
      ) : rivalryId ? (
        <RivalryDetail key={rivalryId} id={rivalryId} onBack={() => go("?tab=rivalries")} onChanged={refresh} />
      ) : (
        <>
          <div className="flex gap-2" role="tablist">
            <Button variant={tab === "roster" ? "primary" : "secondary"} onClick={() => go("")} role="tab" aria-selected={tab === "roster"}>
              <Users size={15} /> Roster {rappers.data ? `(${rappers.data.length})` : ""}
            </Button>
            <Button variant={tab === "rivalries" ? "primary" : "secondary"} onClick={() => go("?tab=rivalries")} role="tab" aria-selected={tab === "rivalries"}>
              <Swords size={15} /> Rivalries {rivalries.data ? `(${rivalries.data.length})` : ""}
            </Button>
          </div>
          {rappers.error && <Notice>{rappers.error}</Notice>}
          {tab === "roster" ? (
            <Roster rappers={rappers.data ?? []} onOpen={(id) => go(`?rapper=${id}`)} onMade={(r) => { refresh(); go(`?rapper=${r.id}`); }} />
          ) : (
            <div className="space-y-6">
              {rappers.data && <NewRivalry key={rappers.data.length} rappers={rappers.data} onMade={(r) => { refresh(); go(`?rivalry=${r.id}`); }} />}
              <div className="grid gap-3 sm:grid-cols-2">
                {rivalries.data?.map((r) => (
                  <button key={r.id} type="button" onClick={() => go(`?rivalry=${r.id}`)} className="rounded-2xl border border-line bg-panel/80 p-4 text-left transition hover:border-volt/60">
                    <p className="font-display font-bold">
                      {r.rapper_a.name} <span className="text-volt">vs</span> {r.rapper_b.name}
                    </p>
                    <p className="mt-1 font-mono text-sm">{r.record.a} - {r.record.b}{r.champion_id ? " · 👑 champion crowned" : ""}</p>
                    {r.tagline && <p className="mt-1 truncate text-xs text-muted">{r.tagline}</p>}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
