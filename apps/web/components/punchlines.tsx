"use client";

import { Crosshair, X } from "lucide-react";
import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { PunchlineOptions } from "@/lib/types";
import { Badge, Button, Equalizer } from "./ui";

/**
 * PUNCHLINE MODE for one section: pick a line, get five alternatives from the
 * text model, choose one. Choosing hands the new line back to the editor,
 * which saves it as a new version.
 */
export function PunchlinePanel({
  lines,
  prepare,
  onChoose,
  onClose,
  disabled,
}: {
  lines: string[];
  /** Saves pending edits and returns the asset and section id to ask about. */
  prepare: () => Promise<{ assetId: string; sectionId: string }>;
  onChoose: (lineIndex: number, line: string) => Promise<void>;
  onClose: () => void;
  disabled?: boolean;
}) {
  const [picked, setPicked] = useState<number | null>(null);
  const [reply, setReply] = useState<PunchlineOptions | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(index: number) {
    setPicked(index);
    setReply(null);
    setError(null);
    setBusy(true);
    try {
      const { assetId, sectionId } = await prepare();
      setReply(await api.punchlines(assetId, sectionId, index, 5));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 rounded-xl border border-volt/40 bg-volt/5 p-3">
      <div className="mb-2 flex items-center gap-2">
        <Crosshair size={14} className="text-volt" />
        <p className="text-xs font-semibold uppercase tracking-wide">Punchline mode</p>
        <span className="text-xs text-muted">Tap a line for 5 alternatives</span>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onClose} aria-label="Close punchline mode">
          <X size={13} />
        </Button>
      </div>
      <ol className="space-y-1">
        {lines.map((line, index) => (
          <li key={`${index}-${line}`}>
            <button
              type="button"
              disabled={disabled || busy}
              onClick={() => ask(index)}
              aria-pressed={picked === index}
              className={`w-full rounded-lg px-2.5 py-1.5 text-left text-sm transition disabled:opacity-60 ${
                picked === index ? "bg-volt/15 text-fg" : "hover:bg-white/5"
              }`}
            >
              {line}
            </button>
            {picked === index && (
              <div className="ml-3 mt-1 space-y-1 border-l border-volt/40 pl-3">
                {busy && (
                  <p className="flex items-center gap-2 py-1 text-xs text-muted">
                    <Equalizer /> Sharpening five punchlines…
                  </p>
                )}
                {error && <p className="py-1 text-xs text-danger">{error}</p>}
                {reply?.is_mock && <Badge tone="mock">Mock provider: placeholders, not AI</Badge>}
                {reply?.options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    disabled={disabled}
                    onClick={async () => {
                      setError(null);
                      try {
                        await onChoose(index, option);
                        setPicked(null);
                        setReply(null);
                      } catch (reason) {
                        setError(errorMessage(reason));
                      }
                    }}
                    className="block w-full rounded-lg border border-line bg-panel/80 px-2.5 py-1.5 text-left text-sm transition hover:border-volt"
                  >
                    {option}
                  </button>
                ))}
                {reply && <p className="text-[11px] text-muted">By {reply.model ?? reply.provider}. Choosing one saves a new version; the old one stays in history.</p>}
              </div>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
