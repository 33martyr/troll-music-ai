"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { TrackPlayer } from "./player";
import { api, fileUrl } from "@/lib/api";
import type { Asset, TrollMeta } from "@/lib/types";
import { KINDS } from "./troll";
import { Badge } from "./ui";

interface Recent {
  track: Asset;
  troll: TrollMeta;
  cover: Asset | null;
}

/** The latest things made on the home page, newest first. */
export function RecentTrolls({ refreshKey }: { refreshKey: string | null }) {
  const [items, setItems] = useState<Recent[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    (async () => {
      const tracks = (await api.assets("kind=song,beat&limit=60")).filter((a) => a.meta?.troll).slice(0, 6);
      const covers = await Promise.all(
        tracks.map((t) => (t.meta!.troll!.cover_asset_id ? api.asset(t.meta!.troll!.cover_asset_id).catch(() => null) : null)),
      );
      if (live) setItems(tracks.map((track, i) => ({ track, troll: track.meta!.troll!, cover: covers[i] })));
    })().catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [refreshKey]);

  if (failed || (items && items.length === 0)) {
    return (
      <p className="rounded-2xl border border-dashed border-line px-5 py-8 text-center text-sm text-muted">
        {failed ? "Your trolls show up here once the backend is running." : "Nothing roasted yet. Somebody out there is getting away with it."}
      </p>
    );
  }
  if (!items) return <p className="text-sm text-muted">Loading your hall of shame…</p>;
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map(({ track, troll, cover }) => {
        const kind = KINDS.find((k) => k.id === troll.kind);
        return (
          <article key={track.id} className="group overflow-hidden rounded-2xl border border-line bg-panel/80 transition hover:border-grape/60">
            <div className="flex gap-3 p-3">
              {cover?.has_file ? (
                // eslint-disable-next-line @next/next/no-img-element -- served by the API with a signed URL
                <img src={fileUrl(cover)} alt="" className="h-20 w-20 shrink-0 rounded-xl object-cover" />
              ) : (
                <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-xl bg-grape/15 text-3xl">{kind?.emoji ?? "🎤"}</div>
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate font-display text-sm font-bold">{track.title}</p>
                <p className="truncate text-xs text-muted">
                  {troll.artist} · vs {troll.target}
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  <Badge>{kind?.label ?? troll.label}</Badge>
                  {track.is_mock && <Badge tone="mock">Mock</Badge>}
                </div>
              </div>
            </div>
            {track.has_file && (
              <div className="px-3">
                <TrackPlayer src={fileUrl(track)} label={track.title} knownDuration={track.duration_seconds} lazy compact />
              </div>
            )}
            <Link href={`/?track=${track.id}`} className="block px-3 pb-3 pt-2 text-xs font-medium text-muted hover:text-volt">
              Open, share or remix →
            </Link>
          </article>
        );
      })}
    </div>
  );
}
