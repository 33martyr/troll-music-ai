"use client";

import { Check, Gavel, Link2, Swords } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { TrackPlayer } from "@/components/player";
import { Badge, Button, ButtonLink, Card, Empty, Equalizer, Notice } from "@/components/ui";
import { api, errorMessage, fileUrl } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Asset, BattleInfo, BattleScore, Scorecard, VoteTally } from "@/lib/types";

const CATEGORIES: (keyof Omit<BattleScore, "comment">)[] = ["punchlines", "flow", "creativity", "humor", "entertainment"];
const VOTER_KEY = "troll_voter_id";

/** A random id this browser keeps so a vote can be changed rather than repeated. */
function voterId(): string {
  try {
    let id = window.localStorage.getItem(VOTER_KEY);
    if (!id) {
      id = `v-${crypto.randomUUID()}`;
      window.localStorage.setItem(VOTER_KEY, id);
    }
    return id;
  } catch {
    return `v-${Math.random().toString(36).slice(2)}-${Date.now()}`;
  }
}

function BattleList() {
  const songs = useLoad(() => api.assets("kind=song&limit=100"));
  const battles = (songs.data ?? []).filter((a) => a.meta?.troll?.kind === "rap_battle");
  return (
    <div className="space-y-8">
      <header>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.25em] text-grape">Roast Battles</p>
        <h1 className="font-display text-4xl font-black tracking-tight sm:text-5xl">WHO WON?</h1>
        <p className="mt-3 max-w-xl text-muted">Every battle you made. Open one to get the AI judges&apos; scorecard and let your friends vote.</p>
      </header>
      {songs.loading && <p className="text-sm text-muted">Loading battles…</p>}
      {songs.error && <Notice>{songs.error}</Notice>}
      {!songs.loading && !battles.length && (
        <Empty title="No battles yet">
          <p>Pick &quot;Rap Battle&quot; on the home page to start one.</p>
          <ButtonLink href="/" variant="primary" className="mt-4">
            <Swords size={15} /> Start a battle
          </ButtonLink>
        </Empty>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {battles.map((song) => (
          <Link key={song.id} href={`/battle?id=${song.id}`} className="rounded-2xl border border-line bg-panel/80 p-4 transition hover:border-volt/60">
            <p className="font-display font-bold">{song.title}</p>
            <p className="mt-1 text-sm text-muted">
              {song.meta?.troll?.artist} <span className="text-volt">vs</span> {song.meta?.troll?.target}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}

function ScoreBars({ name, score, overall, winner, side }: { name: string; score: BattleScore; overall: number; winner: boolean; side: "a" | "b" }) {
  const colour = side === "a" ? "bg-volt" : "bg-grape";
  return (
    <div className={`rounded-2xl border p-4 ${winner ? "border-volt shadow-[0_0_30px_-12px] shadow-volt" : "border-line"}`}>
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <p className="font-display text-lg font-bold">
          {name} {winner && <span aria-label="judges' pick">👑</span>}
        </p>
        <p className="font-mono text-2xl font-bold">{overall.toFixed(1)}</p>
      </div>
      <dl className="space-y-2">
        {CATEGORIES.map((category) => (
          <div key={category}>
            <div className="flex justify-between text-xs">
              <dt className="capitalize text-muted">{category}</dt>
              <dd className="font-mono">{score[category]}/10</dd>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-line" aria-hidden>
              <div className={`h-full rounded-full ${colour}`} style={{ width: `${score[category] * 10}%` }} />
            </div>
          </div>
        ))}
      </dl>
      {score.comment && <p className="mt-3 text-sm italic text-muted">{score.comment}</p>}
    </div>
  );
}

function Judges({ card, rappers }: { card: Asset<Scorecard>; rappers: [string, string] }) {
  const content = card.content!;
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-display text-xl font-black uppercase">The judges&apos; scorecard</h2>
        {card.is_mock ? <Badge tone="mock">Mock: no AI judged this</Badge> : <Badge tone="grape">AI opinion · {card.model ?? card.provider}</Badge>}
      </div>
      <Card className="p-5">
        <p className="text-xs font-semibold uppercase tracking-widest text-grape">{content.winner ? `The judges pick ${content.winner}` : "The judges call it a draw"}</p>
        <p className="mt-2 text-lg leading-relaxed">{content.announcement}</p>
        {content.best_line && <p className="mt-3 text-sm text-muted">Line of the night: <span className="text-fg">“{content.best_line}”</span></p>}
      </Card>
      <div className="grid gap-3 md:grid-cols-2">
        {rappers.map((name, index) => (
          <ScoreBars
            key={name}
            name={name}
            score={content.scores[name]}
            overall={content.overall?.[name] ?? 0}
            winner={content.winner === name}
            side={index === 0 ? "a" : "b"}
          />
        ))}
      </div>
      <p className="text-xs text-muted">
        These marks are one AI model&apos;s taste, not a measurement. Ask again and they may change. Your friends&apos; votes below are the
        real verdict.
      </p>
    </section>
  );
}

function Votes({ battleAsset, rappers, initial }: { battleAsset: string; rappers: [string, string]; initial: VoteTally }) {
  const [tally, setTally] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const choices = [rappers[0], "draw", rappers[1]];
  async function cast(choice: string) {
    setError(null);
    try {
      setTally(await api.vote(battleAsset, choice, voterId()));
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }
  return (
    <section className="space-y-3">
      <h2 className="font-display text-xl font-black uppercase">Who actually won?</h2>
      <div className="grid grid-cols-3 gap-2">
        {choices.map((choice) => {
          const count = tally.counts[choice] ?? 0;
          const share = tally.total ? Math.round((count / tally.total) * 100) : 0;
          const mine = tally.your_vote === choice;
          return (
            <button
              key={choice}
              type="button"
              onClick={() => cast(choice)}
              aria-pressed={mine}
              className={`relative overflow-hidden rounded-2xl border p-3 text-center transition ${mine ? "border-volt" : "border-line hover:border-grape/60"}`}
            >
              <span className="absolute inset-y-0 left-0 bg-volt/10 transition-all" style={{ width: `${share}%` }} aria-hidden />
              <span className="relative block truncate font-display text-sm font-bold">{choice === "draw" ? "🤝 Draw" : choice}</span>
              <span className="relative block font-mono text-xs text-muted">
                {count} vote{count === 1 ? "" : "s"} · {share}% {mine && <Check size={11} className="inline" />}
              </span>
            </button>
          );
        })}
      </div>
      {error && <Notice>{error}</Notice>}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          onClick={async () => {
            await navigator.clipboard?.writeText(window.location.href);
            setCopied(true);
          }}
        >
          <Link2 size={13} /> {copied ? "Link copied" : "Copy link to invite voters"}
        </Button>
        <p className="text-xs text-muted">
          Friends can vote from this link if they can reach this app (same network or a hosted deployment). One vote per browser; it
          stops accidents, not determined cheaters.
        </p>
      </div>
    </section>
  );
}

function BattlePage({ id }: { id: string }) {
  const [info, setInfo] = useState<BattleInfo | null>(null);
  const [song, setSong] = useState<Asset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [judging, setJudging] = useState(false);

  useEffect(() => {
    let live = true;
    Promise.all([api.battle(id, voterId()), api.asset(id)])
      .then(([battle, asset]) => live && (setInfo(battle), setSong(asset)))
      .catch((reason) => live && setError(errorMessage(reason)));
    return () => {
      live = false;
    };
  }, [id]);

  if (error) return <Notice>{error}</Notice>;
  if (!info) return <p className="text-sm text-muted"><Equalizer /> Loading the battle…</p>;
  const [a, b] = info.rappers;
  const lyrics = info.lyrics.content;

  async function judge() {
    setJudging(true);
    setError(null);
    try {
      const card = await api.scoreBattle(id);
      setInfo((current) => (current ? { ...current, scorecard: card } : current));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setJudging(false);
    }
  }

  return (
    <div className="space-y-10">
      <header className="rise text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-grape">Roast Battle</p>
        <h1 className="mt-3 font-display text-3xl font-black leading-tight sm:text-5xl">
          <span className="text-volt">{a}</span>
          <span className="mx-3 text-muted">vs</span>
          <span className="text-grape">{b}</span>
        </h1>
        {lyrics && <p className="mt-2 text-muted">“{lyrics.title}”</p>}
      </header>

      {song?.has_file && (
        <Card className="p-4">
          <TrackPlayer src={fileUrl(song)} label={song.title} knownDuration={song.duration_seconds} />
          <div className="mt-3 flex flex-wrap gap-2">
            <ButtonLink size="sm" href={`/factory?asset=${song.id}`}>Meme Factory</ButtonLink>
            {song.project_id && <ButtonLink size="sm" href={`/projects/${song.project_id}`}>Files</ButtonLink>}
          </div>
        </Card>
      )}

      {lyrics && (
        <section className="grid gap-3 md:grid-cols-2">
          {lyrics.sections.map((section) => {
            const side = section.performer === a ? "a" : section.performer === b ? "b" : null;
            return (
              <Card
                key={section.id}
                className={`p-4 ${side === null ? "md:col-span-2 text-center" : side === "b" ? "md:col-start-2" : "md:col-start-1"} ${
                  side === "a" ? "border-volt/40" : side === "b" ? "border-grape/40" : ""
                }`}
              >
                <p className={`mb-1 text-[11px] font-semibold uppercase tracking-widest ${side === "a" ? "text-volt" : side === "b" ? "text-grape" : "text-muted"}`}>
                  {section.label}
                </p>
                {section.lines.map((line, index) => (
                  <p key={index} className="leading-7">{line}</p>
                ))}
              </Card>
            );
          })}
        </section>
      )}

      {info.scorecard?.content ? (
        <>
          <Judges card={info.scorecard} rappers={info.rappers} />
          <Button onClick={judge} busy={judging}>
            <Gavel size={14} /> Ask the judges again
          </Button>
        </>
      ) : (
        <Card className="flex flex-wrap items-center gap-4 p-5">
          <div className="min-w-0 flex-1">
            <p className="font-display text-lg font-bold">Bring in the judges</p>
            <p className="text-sm text-muted">An AI panel scores punchlines, flow, creativity, humor and entertainment, and explains its pick from the actual lines. It&apos;s an opinion.</p>
          </div>
          <Button variant="primary" onClick={judge} busy={judging}>
            {!judging && <Gavel size={15} />} {judging ? "Deliberating…" : "Judge this battle"}
          </Button>
        </Card>
      )}

      <Votes battleAsset={id} rappers={info.rappers} initial={info.votes} />
    </div>
  );
}

export default function BattleRoute() {
  const id = useSearchParams().get("id");
  return id ? <BattlePage key={id} id={id} /> : <BattleList />;
}
