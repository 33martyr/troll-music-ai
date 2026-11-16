"use client";

import { Cpu, KeyRound, PlugZap, RotateCcw, Save } from "lucide-react";
import { useState, useSyncExternalStore } from "react";
import { Badge, Button, Card, Field, Notice, PageHeader } from "@/components/ui";
import { API_URL, api, errorMessage, getApiKey, setApiKey } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { ProviderCheck, ProviderState } from "@/lib/types";

const noSubscribe = () => () => undefined;

interface Draft {
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
  enabled: boolean;
}

const toDraft = (state: ProviderState): Draft => ({
  provider: state.provider,
  model: state.model ?? "",
  base_url: state.base_url ?? "",
  api_key: "",
  enabled: state.enabled,
});

function ProviderPanel({ state, onSaved }: { state: ProviderState; onSaved: (state: ProviderState) => void }) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(state));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [check, setCheck] = useState<ProviderCheck | null>(null);

  const option = state.options.find((o) => o.name === draft.provider);
  const switching = draft.provider !== state.provider;
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  function choose(name: string) {
    const next = state.options.find((o) => o.name === name);
    // A new provider starts from its own defaults, not the previous provider's values.
    setDraft({ provider: name, model: next?.default_model ?? "", base_url: next?.default_base_url ?? "", api_key: "", enabled: true });
    setCheck(null);
    setError(null);
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
    }
  }

  const save = () =>
    act("save", async () => {
      const saved = await api.updateProvider(state.kind, {
        provider: draft.provider,
        model: draft.model.trim() || null,
        base_url: draft.base_url.trim() || null,
        // Blank keeps the stored key. The key is never sent back to this page.
        api_key: draft.api_key ? draft.api_key : undefined,
        enabled: draft.enabled,
      });
      setCheck(null);
      onSaved(saved);
    });

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1 basis-60">
          <h2 className="font-display text-base font-semibold">{state.label}</h2>
          <p className="mt-0.5 text-xs text-muted">
            {state.configured ? (
              <>
                Active: <span className="font-mono text-fg">{state.provider}</span>
                {state.model && <span className="font-mono"> · {state.model}</span>}
              </>
            ) : (
              "Nothing is active."
            )}{" "}
            · from {state.source === "settings" ? "these settings" : state.source === "override" ? "a test override" : "the environment (.env)"}
          </p>
        </div>
        {state.is_mock ? (
          <Badge tone="mock">Mock</Badge>
        ) : state.configured ? (
          <Badge tone={state.is_ai ? "grape" : "live"}>{state.is_ai ? "AI model" : "Built-in engine"}</Badge>
        ) : (
          <Badge tone="danger">Not configured</Badge>
        )}
      </div>

      {state.error && <div className="mb-4"><Notice>{state.error}</Notice></div>}

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Provider">
          <select className="control" value={draft.provider} onChange={(e) => choose(e.target.value)}>
            <option value="none">None</option>
            {state.options.map((o) => (
              <option key={o.name} value={o.name}>
                {o.label}
                {!o.verified ? " (untested)" : ""}
              </option>
            ))}
          </select>
        </Field>
        {option && (option.needs_model || option.default_model || option.suggested_models.length > 0) && (
          <Field label="Model" hint={option.needs_model ? "required" : undefined}>
            <input className="control font-mono" list={`models-${state.kind}`} value={draft.model} placeholder={option.default_model ?? ""} onChange={(e) => set("model", e.target.value)} />
            <datalist id={`models-${state.kind}`}>{option.suggested_models.map((m) => <option key={m} value={m} />)}</datalist>
          </Field>
        )}
        {option && (option.needs_base_url || option.default_base_url) && (
          <Field label="Server URL" hint={option.needs_base_url ? "required" : undefined}>
            <input className="control font-mono" value={draft.base_url} placeholder={option.default_base_url ?? "https://…/v1"} onChange={(e) => set("base_url", e.target.value)} />
          </Field>
        )}
        {option && (option.needs_api_key || !option.local) && (
          <Field label="API key" hint={option.needs_api_key ? "required" : "optional"}>
            <input
              className="control font-mono"
              type="password"
              autoComplete="off"
              value={draft.api_key}
              placeholder={state.has_api_key && !switching ? "•••••••• saved, leave blank to keep" : "Paste key"}
              onChange={(e) => set("api_key", e.target.value)}
            />
          </Field>
        )}
      </div>

      {option && (
        <div className="mt-4 space-y-1.5 rounded-xl border border-line bg-ink/40 p-3 text-xs leading-relaxed text-muted">
          <p className="text-fg">{option.description}</p>
          <p>
            <span className="text-fg">Runs:</span> {option.local ? "on this machine or a server you run" : "on a hosted service (your prompts leave this machine)"}
            {" · "}
            <span className="text-fg">Hardware:</span> {option.hardware}
          </p>
          {option.license && (
            <p>
              <span className="text-fg">Licence:</span> {option.license}
              {option.commercial_use === false && <span className="text-amber"> Not for commercial use.</span>}
            </p>
          )}
          {option.params.length > 0 && <p><span className="text-fg">Honours:</span> {option.params.join(", ")}</p>}
          {option.setup && <p><span className="text-fg">Setup:</span> <span className="font-mono">{option.setup}</span></p>}
          {!option.verified && (
            <p className="text-amber">This adapter is written to the provider&apos;s documented API but has not been tested against the real service yet.</p>
          )}
          {option.missing_packages.length > 0 && (
            <p className="text-danger">Missing Python packages on the backend: {option.missing_packages.join(", ")}</p>
          )}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" size="sm" busy={busy === "save"} onClick={save}>
          {busy !== "save" && <Save size={13} />} Save
        </Button>
        <Button
          size="sm"
          busy={busy === "check"}
          disabled={!state.configured || switching}
          onClick={() => act("check", async () => setCheck(await api.checkProvider(state.kind)))}
        >
          {busy !== "check" && <PlugZap size={13} />} Test connection
        </Button>
        {state.source === "settings" && (
          <Button size="sm" variant="ghost" busy={busy === "reset"} onClick={() => act("reset", async () => onSaved(await api.resetProvider(state.kind)))}>
            {busy !== "reset" && <RotateCcw size={13} />} Use .env instead
          </Button>
        )}
        {state.source === "settings" && state.provider !== "none" && (
          <label className="ml-auto flex items-center gap-2 text-xs text-muted">
            <input type="checkbox" checked={draft.enabled} onChange={(e) => set("enabled", e.target.checked)} className="h-3.5 w-3.5 accent-[var(--color-volt)]" />
            Enabled
          </label>
        )}
      </div>
      {switching && <p className="mt-2 text-xs text-muted">Save to switch; the connection test runs against the active provider.</p>}
      {error && <div className="mt-3"><Notice>{error}</Notice></div>}
      {check && (
        <div className="mt-3">
          <Notice tone={check.ok ? "info" : "danger"}>
            {check.ok ? "Connection OK. " : "Connection failed. "}
            {check.detail}
            {check.models.length > 0 && <span className="mt-1 block text-xs opacity-80">Models there: {check.models.slice(0, 12).join(", ")}</span>}
          </Notice>
        </div>
      )}
    </Card>
  );
}

function ApiKeyCard() {
  const health = useLoad(api.health);
  const stored = useSyncExternalStore(noSubscribe, getApiKey, () => "");
  const [draft, setDraft] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const key = draft ?? stored;
  if (!health.data?.auth_required && !stored) return null;
  return (
    <Card className="mb-6 p-5">
      <h2 className="mb-1 flex items-center gap-2 font-display text-base font-semibold"><KeyRound size={16} className="text-volt" /> Studio API key</h2>
      <p className="mb-3 text-sm text-muted">This backend requires its API key (TROLL_API_KEY). It is stored in this browser only.</p>
      <div className="flex flex-wrap gap-2">
        <input className="control max-w-sm font-mono" type="password" autoComplete="off" value={key} onChange={(e) => { setDraft(e.target.value); setSaved(false); }} />
        <Button size="md" onClick={() => { setApiKey(key.trim()); setSaved(true); }}>Save</Button>
      </div>
      {saved && <p className="mt-2 text-xs text-volt">Saved. Reload the page to use it everywhere.</p>}
    </Card>
  );
}

function HardwareCard() {
  const hw = useLoad(api.hardware);
  if (!hw.data) return null;
  const { ffmpeg, gpus, packages, platform, python } = hw.data;
  return (
    <Card className="p-5">
      <h2 className="mb-3 flex items-center gap-2 font-display text-base font-semibold"><Cpu size={16} className="text-volt" /> Backend machine</h2>
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        <div><dt className="text-xs text-muted">System</dt><dd>{platform} · Python {python}</dd></div>
        <div>
          <dt className="text-xs text-muted">FFmpeg</dt>
          <dd className={ffmpeg.ok ? "" : "text-danger"}>{ffmpeg.ok ? ffmpeg.detail.split(" Copyright")[0] : `Missing: ${ffmpeg.detail}`}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">GPU</dt>
          <dd>
            {gpus.length
              ? gpus.map((g) => `${g.name} (${(g.memory_total_mb / 1024).toFixed(0)} GB${g.memory_used_mb !== null ? `, ${(g.memory_used_mb / 1024).toFixed(1)} GB used` : ""})`).join(", ")
              : "No NVIDIA GPU detected. Local AI models will run on CPU, slowly."}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Python packages</dt>
          <dd className="flex flex-wrap gap-1">
            {Object.entries(packages).map(([name, ok]) => <Badge key={name} tone={ok ? "live" : "planned"}>{name}</Badge>)}
          </dd>
        </div>
      </dl>
    </Card>
  );
}

export default function SettingsPage() {
  const providers = useLoad(api.providers);
  // States returned by a save replace the loaded ones until the next load.
  const [savedStates, setSavedStates] = useState<Record<string, ProviderState>>({});
  const states = providers.data?.map((state) => savedStates[state.kind] ?? state) ?? null;

  return (
    <>
      <PageHeader eyebrow="Configuration" title="Model Settings">
        Choose which provider and model does each job. Changes apply immediately, override{" "}
        <code className="font-mono text-fg">.env</code>, and are stored on the backend at{" "}
        <code className="font-mono text-fg">{API_URL}</code>. API keys are never sent back to the browser.
      </PageHeader>

      <ApiKeyCard />
      {providers.error && <div className="mb-6"><Notice>{providers.error}</Notice></div>}
      {!states && !providers.error && <p className="text-sm text-muted">Loading…</p>}

      <div className="grid gap-4 xl:grid-cols-2">
        {states?.map((state) => (
          // Keyed by content so the form resets to whatever the backend now reports.
          <ProviderPanel key={JSON.stringify(state)} state={state} onSaved={(next) => setSavedStates((all) => ({ ...all, [next.kind]: next }))} />
        ))}
      </div>

      <div className="mt-6 space-y-4">
        <Notice tone="info">
          Video animation: no AI video model is integrated. Music videos are rendered from scene images with FFmpeg.
          Model weights are never downloaded automatically; for MusicGen run{" "}
          <code className="font-mono">python scripts/download_models.py musicgen</code> (about 2.4 GB).
        </Notice>
        <HardwareCard />
      </div>
    </>
  );
}
