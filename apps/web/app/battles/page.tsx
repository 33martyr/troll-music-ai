"use client";

import { Lightbulb, Music, PenLine, Sparkles } from "lucide-react";
import { useState } from "react";
import { JobStatus, OriginBadge, PoweredBy, ProjectSelect, useCapability, useJobRunner } from "@/components/studio";
import { Button, ButtonLink, Card, Field, Notice, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { BattleCharacter, BattleRequest, LyricsAsset } from "@/lib/types";

const INTENSITY = ["", "Gentle tease", "Cheeky", "Proper roast", "Heavy roast", "Maximum troll"];
const blank = (): BattleCharacter => ({ name: "", personality: "", style: "" });

function CharacterForm({ label, tone, value, onChange }: { label: string; tone: string; value: BattleCharacter; onChange: (c: BattleCharacter) => void }) {
  return (
    <fieldset className={`space-y-2.5 rounded-xl border p-3 ${tone}`}>
      <legend className="px-1.5 text-xs font-semibold uppercase tracking-wide">{label}</legend>
      <input aria-label={`${label} name`} className="control" placeholder="Name (fictional)" maxLength={60} value={value.name} onChange={(e) => onChange({ ...value, name: e.target.value })} />
      <input aria-label={`${label} personality`} className="control" placeholder="Personality, e.g. smug sourdough baker" maxLength={300} value={value.personality} onChange={(e) => onChange({ ...value, personality: e.target.value })} />
      <input aria-label={`${label} rap style`} className="control" placeholder="Rap style, e.g. fast and technical" maxLength={120} value={value.style} onChange={(e) => onChange({ ...value, style: e.target.value })} />
    </fieldset>
  );
}

export default function BattlesPage() {
  const options = useLoad(api.options);
  const text = useCapability("text");
  const runner = useJobRunner();
  const [topic, setTopic] = useState("");
  const [a, setA] = useState(blank);
  const [b, setB] = useState(blank);
  const [rounds, setRounds] = useState(2);
  const [genre, setGenre] = useState("boom bap");
  const [intensity, setIntensity] = useState(3);
  const [explicit, setExplicit] = useState(false);
  const [projectId, setProjectId] = useState("");
  const [battle, setBattle] = useState<LyricsAsset | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready = topic.trim().length >= 3 && a.name.trim() && b.name.trim() && text.capability?.configured;

  async function suggest() {
    setSuggesting(true);
    setError(null);
    try {
      const { characters } = await api.suggestCharacters(topic);
      if (characters[0]) setA({ ...blank(), ...characters[0] });
      if (characters[1]) setB({ ...blank(), ...characters[1] });
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSuggesting(false);
    }
  }

  async function generate() {
    setBattle(null);
    const request: BattleRequest = { topic, character_a: a, character_b: b, rounds, genre, language: "English", troll_intensity: intensity, explicit };
    const job = await runner.run(() => api.generateBattle(request, projectId || null));
    if (job) setBattle(await api.asset(job.result_asset_id!));
  }

  const first = battle?.content?.sections.find((s) => s.performer)?.performer;

  return (
    <>
      <PageHeader eyebrow="Workshop" title="Battle Builder">
        Two fictional characters trade verses about a topic. The battle is saved as lyrics, so you can edit it, give
        each character a voice and turn it into a song or video.
      </PageHeader>

      <div className="mb-6">
        <PoweredBy {...text} what="battle lyrics" />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,26rem)_1fr]">
        <Card className="space-y-4 p-5">
          <Field label="What are they battling about?">
            <textarea className="control [field-sizing:content]" rows={2} maxLength={1000} value={topic} placeholder="e.g. who makes the better sandwich" onChange={(e) => setTopic(e.target.value)} />
          </Field>
          <Button size="sm" busy={suggesting} disabled={topic.trim().length < 3 || !text.capability?.configured} onClick={suggest}>
            {!suggesting && <Lightbulb size={13} />} Suggest two characters
          </Button>
          <CharacterForm label="Character A" tone="border-volt/30" value={a} onChange={setA} />
          <CharacterForm label="Character B" tone="border-cyber/30" value={b} onChange={setB} />
          <p className="text-xs text-muted">Characters must be made up. Battles about real people are not what this is for.</p>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Rounds">
              <select className="control" value={rounds} onChange={(e) => setRounds(Number(e.target.value))}>
                {[1, 2, 3, 4].map((n) => <option key={n}>{n}</option>)}
              </select>
            </Field>
            <Field label="Genre">
              <input className="control" list="battle-genres" value={genre} maxLength={60} onChange={(e) => setGenre(e.target.value)} />
              <datalist id="battle-genres">{options.data?.genres.map((g) => <option key={g} value={g} />)}</datalist>
            </Field>
          </div>
          <Field label="Troll intensity" hint={INTENSITY[intensity]}>
            <input type="range" min={1} max={5} value={intensity} onChange={(e) => setIntensity(Number(e.target.value))} className="w-full accent-[var(--color-volt)]" />
          </Field>
          <label className="flex items-center gap-2.5 text-sm">
            <input type="checkbox" checked={explicit} onChange={(e) => setExplicit(e.target.checked)} className="h-4 w-4 accent-[var(--color-volt)]" />
            Allow explicit language
          </label>
          <ProjectSelect value={projectId} onChange={setProjectId} />
          <Button variant="primary" busy={runner.busy} disabled={!ready} onClick={generate}>
            {!runner.busy && <Sparkles size={15} />} Start the battle
          </Button>
        </Card>

        <div className="space-y-4">
          {error && <Notice>{error}</Notice>}
          <JobStatus runner={runner} onRetried={async (job) => setBattle(await api.asset(job.result_asset_id!))} />
          {battle?.content && (
            <Card className="p-5">
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <h2 className="min-w-0 flex-1 font-display text-lg font-bold">{battle.content.title}</h2>
                <OriginBadge asset={battle} />
              </div>
              <div className="space-y-5">
                {battle.content.sections.map((section) => {
                  const isA = section.performer === first;
                  return (
                    <div key={section.id} className={section.performer ? `border-l-2 pl-3 ${isA ? "border-volt/60" : "border-cyber/60"}` : ""}>
                      <p className={`mb-1 text-xs font-semibold uppercase tracking-wide ${section.performer ? (isA ? "text-volt" : "text-cyber") : "text-muted"}`}>
                        {section.label}
                      </p>
                      {section.lines.map((line, index) => <p key={index} className="text-sm leading-relaxed">{line}</p>)}
                    </div>
                  );
                })}
              </div>
              <div className="mt-5 flex flex-wrap gap-2">
                <ButtonLink size="sm" href={`/lyrics?asset=${battle.id}`}><PenLine size={13} /> Edit</ButtonLink>
                <ButtonLink size="sm" href={`/beat?lyrics=${battle.id}&genre=${encodeURIComponent(genre)}${battle.content.suggested_bpm ? `&bpm=${battle.content.suggested_bpm}` : ""}`}>Make a beat</ButtonLink>
                <ButtonLink size="sm" variant="primary" href={`/song?lyrics=${battle.id}`}><Music size={13} /> Make it a song</ButtonLink>
              </div>
            </Card>
          )}
          {!battle && !runner.busy && !runner.error && (
            <div className="rounded-2xl border border-dashed border-line px-6 py-12 text-center text-sm text-muted">
              The battle will appear here. On the Song page each character can have their own voice.
            </div>
          )}
        </div>
      </div>
    </>
  );
}
