"use client";

import { Flame, Plus, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { INTENSITIES, STYLES, TrollProgress, TrollResult } from "@/components/troll";
import { useTrollSession } from "@/components/troll-session";
import { Button, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Intensity, Participant, TrollRequest } from "@/lib/types";

const EMPTY: Participant = { name: "", nickname: "", description: "", voice: "" };
const START: Participant[] = [
  { ...EMPTY, name: "" },
  { ...EMPTY, name: "" },
  { ...EMPTY, name: "" },
];

export default function GroupRoastPage() {
  const anchor = useRef<HTMLDivElement>(null);
  const session = useTrollSession(anchor);
  const stock = useLoad(api.stockVoices);
  const [groupName, setGroupName] = useState("");
  const [situation, setSituation] = useState("");
  const [jokes, setJokes] = useState("");
  const [people, setPeople] = useState<Participant[]>(START);
  const [style, setStyle] = useState("trap");
  const [intensity, setIntensity] = useState<Intensity>("savage");
  const [video, setVideo] = useState(false);

  const named = people.filter((p) => p.name.trim());
  const ready = named.length >= 2 && situation.trim().length >= 3 && !session.runner.busy;
  const update = (index: number, patch: Partial<Participant>) =>
    setPeople((list) => list.map((p, i) => (i === index ? { ...p, ...patch } : p)));

  function request(): TrollRequest {
    return {
      kind: "group_roast",
      situation: situation.trim(),
      style,
      intensity,
      delivery: "hype",
      group_name: groupName.trim() || null,
      inside_jokes: jokes.split("\n").map((j) => j.trim()).filter(Boolean).slice(0, 5),
      people: named.map((p) => ({
        name: p.name.trim(),
        nickname: p.nickname?.trim() || null,
        description: p.description?.trim() || null,
        voice: p.voice || null,
      })),
    };
  }

  return (
    <div className="space-y-10">
      <section className="rise">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.25em] text-grape">Group Chat Roast</p>
        <h1 className="font-display text-4xl font-black leading-[1.02] tracking-tight sm:text-6xl">
          EVERYONE
          <br />
          <span className="text-gradient">GETS COOKED.</span>
        </h1>
        <p className="mt-4 max-w-xl text-base text-muted sm:text-lg">
          One verse per person, a group anthem for the chorus, a fake album cover. Nobody in the chat is safe.
        </p>
      </section>

      <form
        className="space-y-8"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) session.generate(request(), { video, sameProject: !!session.result });
        }}
      >
        <div className="grid gap-3 sm:grid-cols-[1fr_2fr]">
          <label className="block text-xs font-medium text-muted">
            Group chat name
            <input className="control mt-1" value={groupName} maxLength={60} onChange={(e) => setGroupName(e.target.value)} placeholder="Lads Holiday 2021 (never happened)" />
          </label>
          <label className="block text-xs font-medium text-muted">
            What does this group do?
            <input
              className="control mt-1"
              value={situation}
              maxLength={600}
              onChange={(e) => setSituation(e.target.value)}
              placeholder="We've been 'planning' the same trip for three years"
            />
          </label>
        </div>

        <div>
          <p className="mb-3 font-display text-sm font-bold uppercase tracking-wide">The defendants</p>
          <div className="space-y-2">
            {people.map((person, index) => (
              <div key={index} className="grid gap-2 rounded-2xl border border-line bg-panel/70 p-3 sm:grid-cols-[1fr_1fr_2fr_1fr_auto]">
                <input className="control" aria-label={`Person ${index + 1} name`} placeholder="Name" maxLength={40} value={person.name} onChange={(e) => update(index, { name: e.target.value })} />
                <input className="control" aria-label={`Person ${index + 1} nickname`} placeholder="Nickname" maxLength={40} value={person.nickname ?? ""} onChange={(e) => update(index, { nickname: e.target.value })} />
                <input
                  className="control"
                  aria-label={`Person ${index + 1} description`}
                  placeholder="Their crime (optional): always late, never pays"
                  maxLength={200}
                  value={person.description ?? ""}
                  onChange={(e) => update(index, { description: e.target.value })}
                />
                <select className="control" aria-label={`Person ${index + 1} voice`} value={person.voice ?? ""} onChange={(e) => update(index, { voice: e.target.value })}>
                  <option value="">Default voice</option>
                  {stock.data?.voices.map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
                <Button variant="ghost" aria-label={`Remove person ${index + 1}`} disabled={people.length <= 2} onClick={() => setPeople((list) => list.filter((_, i) => i !== index))}>
                  <Trash2 size={14} />
                </Button>
              </div>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <Button size="sm" disabled={people.length >= 8} onClick={() => setPeople((list) => [...list, { ...EMPTY }])}>
              <Plus size={13} /> Add someone
            </Button>
            <p className="text-xs text-muted">
              2 to 8 people. {stock.data && stock.data.voices.length > 1 ? `Each can have their own voice (${stock.data.voices.length} available).` : "Only one voice is available, so everyone shares it."}
            </p>
          </div>
        </div>

        <label className="block text-xs font-medium text-muted">
          Inside jokes (one per line, up to 5)
          <textarea className="control mt-1" rows={2} value={jokes} onChange={(e) => setJokes(e.target.value)} placeholder={"the kebab incident\nDave's 'business idea'"} />
        </label>

        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {STYLES.filter((s) => !s.beatOnly).map((s) => (
              <button
                key={s.id}
                type="button"
                aria-pressed={style === s.id}
                onClick={() => setStyle(s.id)}
                className={`rounded-full border px-3.5 py-2 text-sm font-medium transition ${style === s.id ? "border-volt bg-volt text-ink" : "border-line bg-panel/80 hover:border-grape/60"}`}
              >
                {s.emoji} {s.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {INTENSITIES.map((level) => (
              <button
                key={level.id}
                type="button"
                aria-pressed={intensity === level.id}
                onClick={() => setIntensity(level.id)}
                className={`rounded-xl border px-3 py-2 text-sm transition ${intensity === level.id ? "border-volt bg-volt/10 font-semibold" : "border-line bg-panel/80 hover:border-grape/60"}`}
              >
                {level.emoji} {level.label}
              </button>
            ))}
            <label className="ml-2 flex items-center gap-2 text-sm">
              <input type="checkbox" checked={video} onChange={(e) => setVideo(e.target.checked)} className="accent-volt" />
              Also make a vertical meme video
            </label>
          </div>
        </div>

        {named.length < 2 && <Notice tone="info">Add at least two names. A group chat of one is just a diary.</Notice>}
        <button
          type="submit"
          disabled={!ready}
          className="flex w-full items-center justify-center gap-3 rounded-2xl bg-volt px-6 py-5 font-display text-xl font-black uppercase tracking-wide text-ink shadow-[0_0_40px_-10px] shadow-volt transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 sm:text-2xl"
        >
          <Flame size={26} /> {session.runner.busy ? "Cooking…" : session.result ? "Cook them again" : "Cook everyone"}
        </button>
        <p className="text-xs text-muted">
          Roasts what people do, never who they are. Only first names and what you type here are sent to the text model.
        </p>
      </form>

      <div ref={anchor} className="scroll-mt-20 space-y-4">
        {(session.runner.busy || session.runner.error) && <TrollProgress runner={session.runner} steps={session.steps} onRetried={session.retried} />}
        {session.result && !session.runner.busy && (
          <TrollResult
            job={session.result}
            regenerating={session.runner.busy}
            onRegenerate={() => session.generate(request(), { video, sameProject: true })}
            onRemix={session.remix}
          />
        )}
      </div>
    </div>
  );
}
