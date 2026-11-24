"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Capability } from "@/lib/types";
import { Notice } from "./ui";

/** State of the text provider: `undefined` while loading or when the backend is down. */
export function useTextProvider(): { text: Capability | undefined; error: string | null } {
  const { data, error } = useLoad(api.capabilities);
  return { text: data?.find((c) => c.kind === "text"), error };
}

/** Says, where it matters, when lyrics can't be generated or are placeholder text. */
export function ProviderBanner({ text, error }: { text: Capability | undefined; error: string | null }) {
  if (error) return <Notice>{error}</Notice>;
  if (!text) return null;
  if (!text.configured) {
    return (
      <Notice tone="info">
        <strong>No AI text provider is configured, so lyrics can&apos;t be generated yet.</strong>{" "}
        {text.note}{" "}
        <Link href="/settings" className="underline decoration-grape underline-offset-2">
          Open AI Settings
        </Link>{" "}
        to choose one (Pollinations works without a key; Ollama runs locally). You can still import lyrics you
        wrote yourself.
      </Notice>
    );
  }
  if (text.is_mock) {
    return (
      <Notice tone="mock">
        <strong>Mock provider active.</strong> Generated lyrics are placeholder text, not AI output. Choose a real
        provider in{" "}
        <Link href="/settings" className="underline decoration-grape underline-offset-2">
          AI Settings
        </Link>{" "}
        to write actual songs.
      </Notice>
    );
  }
  return null;
}
