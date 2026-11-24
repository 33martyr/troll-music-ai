"use client";

import { Mic, ShieldCheck, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { TrackPlayer } from "@/components/player";
import { AssetSelect, JobStatus, Library, MediaCard, PoweredBy, useCapability, useJobRunner } from "@/components/studio";
import { Badge, Button, ButtonLink, Card, Field, Notice, PageHeader } from "@/components/ui";
import { api, errorMessage, voiceSampleUrl } from "@/lib/api";
import { formatWhen, useLoad } from "@/lib/hooks";
import type { Asset } from "@/lib/types";

export default function VoicePage() {
  const params = useSearchParams();
  const voice = useCapability("voice");
  const stock = useLoad(api.stockVoices);
  const profiles = useLoad(api.voices);
  const lyricsList = useLoad(() => api.assets("kind=lyrics&limit=100"));
  const takes = useLoad(() => api.assets("kind=vocals&limit=30"));
  const runner = useJobRunner();

  // Try a voice
  const [lyricsId, setLyricsId] = useState(params.get("lyrics") ?? "");
  const [voiceChoice, setVoiceChoice] = useState("");
  const [bpm, setBpm] = useState(120);
  const [take, setTake] = useState<Asset | null>(null);

  // New profile
  const fileInput = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [owner, setOwner] = useState("");
  const [statement, setStatement] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const canClone = !!stock.data?.cloning;
  const usable = profiles.data?.filter((p) => p.usable) ?? [];
  const consentReady = name.trim() && owner.trim().length >= 2 && statement.trim().length >= 10 && confirmed && file;

  async function perform() {
    setTake(null);
    const profileId = voiceChoice.startsWith("profile:") ? voiceChoice.slice(8) : null;
    const job = await runner.run(() =>
      api.generateVocals({ lyrics_asset_id: lyricsId, bpm, voice: profileId ? null : voiceChoice || null, voice_profile_id: profileId }),
    );
    if (job) {
      setTake(await api.asset(job.result_asset_id!));
      takes.reload();
    }
  }

  async function createProfile() {
    if (!file) return;
    setSaving(true);
    setError(null);
    setNote(null);
    try {
      const profile = await api.createVoice({ name, owner_name: owner, consent_statement: statement, consent_confirmed: confirmed, file });
      setNote(
        profile.usable
          ? `“${profile.name}” is ready to use.`
          : `“${profile.name}” was saved with its consent record, but the active voice provider cannot clone voices, so it can't be used for vocals yet.`,
      );
      setName(""); setStatement(""); setConfirmed(false); setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      profiles.reload();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  const songLink = (asset: Asset) => <ButtonLink size="sm" href={`/song?vocals=${asset.id}`}>Use in a song</ButtonLink>;

  return (
    <>
      <PageHeader eyebrow="Workshop" title="Voices">
        Hear your lyrics performed, and manage voice profiles. A voice profile is only for a voice you own or have
        explicit permission to use.
      </PageHeader>

      <div className="mb-6 space-y-3">
        <PoweredBy {...voice} what="vocals" />
        {stock.data?.provider && (
          <div className="flex flex-wrap gap-1.5">
            <Badge tone="live">Speech</Badge>
            <Badge tone={stock.data.singing ? "live" : "planned"}>{stock.data.singing ? "Singing" : "No singing"}</Badge>
            <Badge tone={stock.data.cloning ? "live" : "planned"}>{stock.data.cloning ? "Voice cloning" : "No voice cloning"}</Badge>
            <Badge tone={stock.data.conversion ? "live" : "planned"}>{stock.data.conversion ? "Voice conversion" : "No voice conversion"}</Badge>
          </div>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="space-y-4 p-5">
          <h2 className="font-display text-base font-semibold">Perform lyrics</h2>
          <AssetSelect label="Lyrics" assets={lyricsList.data} value={lyricsId} onChange={setLyricsId} empty={<>No lyrics yet. <Link href="/lyrics" className="underline">Write some first</Link>.</>} />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Voice">
              <select className="control" value={voiceChoice} onChange={(e) => setVoiceChoice(e.target.value)}>
                <option value="">Default</option>
                {stock.data?.voices.map((v) => <option key={v}>{v}</option>)}
                {usable.map((p) => <option key={p.id} value={`profile:${p.id}`}>{p.name} (voice profile)</option>)}
              </select>
            </Field>
            <Field label="Tempo" hint="BPM">
              <input className="control" type="number" min={50} max={220} value={bpm} onChange={(e) => setBpm(Number(e.target.value) || 120)} />
            </Field>
          </div>
          {stock.data && !stock.data.singing && stock.data.provider && (
            <p className="text-xs leading-relaxed text-amber">{stock.data.note} Each line is placed on a bar at this tempo.</p>
          )}
          <Button variant="primary" busy={runner.busy} disabled={!lyricsId || !voice.capability?.configured} onClick={perform}>
            {!runner.busy && <Sparkles size={15} />} Generate vocals
          </Button>
          <JobStatus runner={runner} />
          {take && <MediaCard asset={take} actions={songLink(take)} />}
        </Card>

        <Card className="space-y-4 p-5">
          <h2 className="flex items-center gap-2 font-display text-base font-semibold">
            <ShieldCheck size={17} className="text-volt" /> New voice profile
          </h2>
          {stock.data && !canClone && (
            <Notice tone="info">
              The active voice provider can&apos;t clone voices. You can still save a profile and its consent record now;
              to use it, choose a cloning provider (ElevenLabs or Chatterbox) in{" "}
              <Link href="/settings" className="underline">AI Settings</Link> and create the profile again.
            </Notice>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Profile name">
              <input className="control" value={name} maxLength={120} placeholder="My voice" onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Voice owner's full name">
              <input className="control" value={owner} maxLength={120} onChange={(e) => setOwner(e.target.value)} />
            </Field>
          </div>
          <Field label="Recording" hint="5 seconds to 5 minutes of clean speech">
            <input ref={fileInput} type="file" accept="audio/*,.wav,.mp3,.m4a,.flac,.ogg" className="control file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-2 file:py-1 file:text-fg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Field>
          <Field label="Consent statement" hint="in the owner's words">
            <textarea className="control [field-sizing:content]" rows={2} maxLength={1000} value={statement} placeholder="I, <name>, am the owner of this voice and give permission to clone it in this app." onChange={(e) => setStatement(e.target.value)} />
          </Field>
          <label className="flex items-start gap-2.5 text-sm">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--color-volt)]" />
            <span>
              I confirm this is my own voice, or I have the owner&apos;s explicit permission to clone it. I will not use it
              to impersonate anyone.
            </span>
          </label>
          <Button variant="primary" busy={saving} disabled={!consentReady} onClick={createProfile}>
            {!saving && <Mic size={15} />} Create voice profile
          </Button>
          {error && <Notice>{error}</Notice>}
          {note && <Notice tone="info">{note}</Notice>}
          <p className="text-xs leading-relaxed text-muted">
            The recording is stored privately on the backend and is never listed publicly. With a hosted cloning
            provider it is also sent to that provider. Deleting a profile removes both copies.
          </p>
        </Card>
      </div>

      <section className="mt-10">
        <h2 className="mb-4 font-display text-lg font-semibold">Voice profiles</h2>
        {!profiles.data?.length ? (
          <p className="text-sm text-muted">{profiles.loading ? "Loading…" : "No voice profiles yet."}</p>
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {profiles.data.map((profile) => (
              <Card key={profile.id} className="p-4">
                <div className="mb-2 flex flex-wrap items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{profile.name}</p>
                    <p className="text-xs text-muted">
                      Consent from {profile.owner_name} · {formatWhen(profile.consent_given_at)}
                    </p>
                  </div>
                  {profile.usable ? <Badge tone="live">Ready · {profile.provider}</Badge> : <Badge tone="planned">Not registered with a provider</Badge>}
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Delete ${profile.name}`}
                    onClick={async () => {
                      if (!confirm(`Delete the voice profile “${profile.name}” and its recording?`)) return;
                      try {
                        const done = await api.deleteVoice(profile.id);
                        setNote(done.note || null);
                        profiles.reload();
                      } catch (reason) {
                        setError(errorMessage(reason));
                      }
                    }}
                  >
                    <Trash2 size={13} />
                  </Button>
                </div>
                <TrackPlayer src={voiceSampleUrl(profile)} label={`${profile.name} voice sample`} lazy compact />
                <p className="mt-2 text-xs italic text-muted">“{profile.consent_statement}”</p>
                {profile.meta?.warnings?.map((warning) => <p key={warning} className="mt-1 text-xs text-amber">{warning}</p>)}
              </Card>
            ))}
          </div>
        )}
      </section>

      <Library title="Vocal takes" assets={takes.data} loading={takes.loading} empty="No vocal takes yet." onChanged={takes.reload} actions={songLink} />
    </>
  );
}
