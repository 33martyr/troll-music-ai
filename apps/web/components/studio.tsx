"use client";

import { Download, RefreshCw, Trash2, Upload, X } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useRef, useState } from "react";
import { TrackPlayer } from "./player";
import { api, errorMessage, fileUrl, isActive, waitForJob } from "@/lib/api";
import { formatWhen, useLoad } from "@/lib/hooks";
import type { Asset, Capability, Job } from "@/lib/types";
import { Badge, Button, Card, Equalizer, Field, Notice } from "./ui";

// ------------------------------- providers --------------------------------- //

/** The provider serving one capability: `undefined` while loading. */
export function useCapability(kind: string): { capability: Capability | undefined; error: string | null } {
  const { data, error } = useLoad(api.capabilities);
  return { capability: data?.find((c) => c.kind === kind), error };
}

/** Says plainly what will do the work: an AI model, a built-in engine, a mock, or nothing. */
export function PoweredBy({ capability, error, what }: { capability: Capability | undefined; error: string | null; what: string }) {
  if (error) return <Notice>{error}</Notice>;
  if (!capability) return null;
  const settings = (
    <Link href="/settings" className="underline decoration-grape underline-offset-2">
      AI Settings
    </Link>
  );
  if (!capability.configured) {
    return (
      <Notice tone="info">
        <strong>No provider is configured for {what}.</strong> {capability.note} Choose one in {settings}.
      </Notice>
    );
  }
  if (capability.is_mock) {
    return (
      <Notice tone="mock">
        <strong>Mock provider active.</strong> Output is placeholder content, not AI-generated. Choose a real provider in{" "}
        {settings}.
      </Notice>
    );
  }
  return (
    <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
      <span>
        {what[0].toUpperCase() + what.slice(1)} by <span className="font-mono text-fg">{capability.provider}</span>
        {capability.model && <span className="font-mono"> · {capability.model}</span>}
      </span>
      {capability.is_ai ? <Badge tone="grape">AI model</Badge> : <Badge>Built-in engine, not AI</Badge>}
      <Link href="/settings" className="underline underline-offset-2 hover:text-fg">
        change
      </Link>
    </p>
  );
}

/** Where an asset came from, in one badge. */
export function OriginBadge({ asset }: { asset: Asset<unknown> }) {
  if (asset.is_mock) return <Badge tone="mock">Mock</Badge>;
  if (asset.origin === "uploaded") return <Badge>Uploaded</Badge>;
  if (asset.origin === "imported") return <Badge>Written by you</Badge>;
  if (asset.is_ai) return <Badge tone="grape">AI · {asset.provider}</Badge>;
  return <Badge>{asset.provider === "ffmpeg-mix" ? "Mixed" : "Built-in engine"}</Badge>;
}

// ---------------------------------- jobs ----------------------------------- //

export interface JobRunner {
  job: Job | null;
  error: string | null;
  busy: boolean;
  /** Start a job and follow it. Resolves with the finished job, or null if it failed or was cancelled. */
  run: (start: () => Promise<Job>) => Promise<Job | null>;
  cancel: () => void;
  retry: () => Promise<Job | null>;
}

export function useJobRunner(): JobRunner {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  async function run(start: () => Promise<Job>): Promise<Job | null> {
    setError(null);
    setStarting(true);
    try {
      const created = await start();
      setStarting(false);
      return await waitForJob(created, setJob);
    } catch (reason) {
      setError(errorMessage(reason));
      return null;
    } finally {
      setStarting(false);
    }
  }

  return {
    job,
    error,
    busy: starting || isActive(job),
    run,
    cancel: () => {
      if (job) api.cancelJob(job.id).catch(() => undefined);
    },
    retry: () => (job ? run(() => api.retryJob(job.id)) : Promise.resolve(null)),
  };
}

/** Live progress while a job runs; the error with a retry button when it fails. */
export function JobStatus({ runner, onRetried }: { runner: JobRunner; onRetried?: (job: Job) => void }) {
  const { job, error } = runner;
  if (job && isActive(job)) {
    return (
      <Card className="p-4" >
        <div className="flex items-center gap-3" role="status" aria-live="polite">
          <Equalizer />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{job.status === "queued" ? "Queued" : job.stage}</p>
            {job.provider && (
              <p className="truncate font-mono text-xs text-muted">
                {job.provider}
                {job.model ? ` · ${job.model}` : ""}
              </p>
            )}
          </div>
          <span className="font-mono text-xs text-muted">{Math.round(job.progress * 100)}%</span>
          <Button size="sm" variant="ghost" onClick={runner.cancel} disabled={job.stage === "Cancelling"}>
            <X size={13} /> Cancel
          </Button>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-line" aria-hidden>
          <div className="h-full rounded-full bg-volt transition-all duration-500" style={{ width: `${Math.max(3, job.progress * 100)}%` }} />
        </div>
      </Card>
    );
  }
  if (!error) return null;
  const retryable = job?.status === "failed" || job?.status === "cancelled";
  return (
    <Notice tone={job?.status === "cancelled" ? "info" : "danger"}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="min-w-0 flex-1">{error}</span>
        {retryable && (
          <Button size="sm" onClick={async () => { const done = await runner.retry(); if (done) onRetried?.(done); }}>
            <RefreshCw size={13} /> Retry
          </Button>
        )}
      </div>
    </Notice>
  );
}

// --------------------------------- pickers --------------------------------- //

export function ProjectSelect({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const projects = useLoad(api.projects);
  return (
    <Field label="Save to project" hint="optional">
      <select className="control" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">No project (library)</option>
        {projects.data?.map((project) => (
          <option key={project.id} value={project.id}>
            {project.name}
          </option>
        ))}
      </select>
    </Field>
  );
}

const describe = (asset: Asset) => {
  const parts = [asset.title];
  if (asset.meta?.bpm) parts.push(`${asset.meta.bpm} BPM`);
  if (asset.duration_seconds) parts.push(formatDuration(asset.duration_seconds));
  return parts.join(" · ");
};

/** Choose one of the user's saved assets of the given kinds. */
export function AssetSelect({
  label,
  hint,
  assets,
  value,
  onChange,
  empty,
  none,
}: {
  label: string;
  hint?: string;
  assets: Asset[] | null;
  value: string;
  onChange: (id: string) => void;
  empty: ReactNode;
  none?: string;
}) {
  return (
    <Field label={label} hint={hint}>
      <select className="control" value={value} onChange={(e) => onChange(e.target.value)} disabled={!assets}>
        {none !== undefined ? <option value="">{none}</option> : !value && <option value="">Choose…</option>}
        {assets?.map((asset) => (
          <option key={asset.id} value={asset.id}>
            {describe(asset)}
          </option>
        ))}
      </select>
      {assets?.length === 0 && <span className="mt-1.5 block text-xs text-muted">{empty}</span>}
    </Field>
  );
}

export function UploadButton({
  label,
  accept = "audio/*,.wav,.mp3,.m4a,.flac,.ogg",
  busy,
  onFile,
}: {
  label: string;
  accept?: string;
  busy?: boolean;
  onFile: (file: File) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onFile(file);
        }}
      />
      <Button busy={busy} onClick={() => input.current?.click()}>
        {!busy && <Upload size={14} />} {label}
      </Button>
    </>
  );
}

// ---------------------------------- media ---------------------------------- //

export function formatDuration(seconds: number): string {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

const formatSize = (bytes: number) => (bytes > 1e6 ? `${(bytes / 1e6).toFixed(1)} MB` : `${Math.round(bytes / 1e3)} kB`);

/** A saved media asset with its player, facts, download and delete. */
export function MediaCard({
  asset,
  onDeleted,
  actions,
  children,
}: {
  asset: Asset;
  onDeleted?: () => void;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  const [error, setError] = useState<string | null>(null);
  const meta = asset.meta ?? {};
  const facts = [
    asset.duration_seconds ? formatDuration(asset.duration_seconds) : null,
    meta.bpm ? `${meta.bpm} BPM${meta.bpm_exact === false ? " (requested)" : ""}` : null,
    meta.key || null,
    meta.width ? `${meta.width}×${meta.height}` : null,
    asset.size_bytes ? formatSize(asset.size_bytes) : null,
    formatWhen(asset.created_at),
  ].filter(Boolean);

  return (
    <Card className="min-w-0 p-4">
      <div className="mb-3 flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1 basis-48">
          <p className="truncate font-medium">{asset.title}</p>
          <p className="mt-0.5 text-xs text-muted">{facts.join(" · ")}</p>
        </div>
        <OriginBadge asset={asset} />
        {meta.delivery === "spoken" && <Badge tone="mock">Spoken, not sung</Badge>}
        {meta.looped && <Badge>Looped</Badge>}
      </div>

      {asset.has_file && asset.mime_type?.startsWith("audio/") && (
        <TrackPlayer src={fileUrl(asset)} label={asset.title} knownDuration={asset.duration_seconds} lazy />
      )}
      {asset.has_file && asset.mime_type?.startsWith("video/") && (
        <video controls preload="metadata" src={fileUrl(asset)} className="max-h-[70vh] w-full rounded-lg bg-black" />
      )}
      {asset.has_file && asset.mime_type?.startsWith("image/") && (
        // eslint-disable-next-line @next/next/no-img-element -- served by the API with a signed URL
        <img src={fileUrl(asset)} alt={asset.title} className="w-full max-w-md rounded-lg" />
      )}
      {children}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {actions}
        <span className="flex-1" />
        {asset.has_file && (
          <a
            href={fileUrl(asset, true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-raised px-2.5 py-1.5 text-xs hover:border-grape/60"
          >
            <Download size={13} /> Download
          </a>
        )}
        {onDeleted && (
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Delete ${asset.title}`}
            onClick={async () => {
              if (!confirm(`Delete “${asset.title}”? This can't be undone.`)) return;
              try {
                await api.deleteAsset(asset.id);
                onDeleted();
              } catch (reason) {
                setError(errorMessage(reason));
              }
            }}
          >
            <Trash2 size={13} />
          </Button>
        )}
      </div>
    </Card>
  );
}

/** A list of saved assets of some kinds, newest first. */
export function Library({
  title,
  assets,
  loading,
  empty,
  onChanged,
  actions,
}: {
  title: string;
  assets: Asset[] | null;
  loading: boolean;
  empty: string;
  onChanged: () => void;
  actions?: (asset: Asset) => ReactNode;
}) {
  return (
    <section className="mt-10">
      <h2 className="mb-4 font-display text-lg font-semibold">{title}</h2>
      {!assets?.length ? (
        <p className="text-sm text-muted">{loading ? "Loading…" : empty}</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {assets.map((asset) => (
            <MediaCard key={asset.id} asset={asset} onDeleted={onChanged} actions={actions?.(asset)} />
          ))}
        </div>
      )}
    </section>
  );
}
