"use client";

import { Download, Factory, PackageOpen } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { JobStatus, OriginBadge, useJobRunner } from "@/components/studio";
import { Badge, Button, ButtonLink, Card, Empty, Notice } from "@/components/ui";
import { api, downloadZip, errorMessage, fileUrl } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Asset, FactoryItem, Lyrics } from "@/lib/types";

const VIDEOS: { id: FactoryItem; label: string; hint: string }[] = [
  { id: "vertical_video", label: "Vertical video 9:16", hint: "Instagram Story · TikTok · YouTube Shorts" },
  { id: "square_video", label: "Square video 1:1", hint: "Feeds and group chats" },
  { id: "wide_video", label: "Wide video 16:9", hint: "YouTube, laptops, the big screen" },
];
const IMAGES: { id: FactoryItem; label: string; hint: string }[] = [
  { id: "square_cover", label: "Album cover 1:1", hint: "Reuses this troll's cover" },
  { id: "concert_poster", label: "Fake concert poster", hint: "9:16, the world tour nobody asked for" },
  { id: "award_card", label: "Fake award", hint: "1:1, from 'The Trollies'" },
  { id: "streaming_card", label: "Now playing card", hint: "9:16, generic parody player" },
  { id: "reaction_meme", label: "Reaction meme", hint: "1:1, top text / bottom text" },
];
const THEMES = [
  { id: "neon", label: "Neon", swatch: "from-[#0e061e] to-[#c8ff3e]" },
  { id: "gold", label: "Gold", swatch: "from-[#140e04] to-[#ffcc4d]" },
  { id: "vaporwave", label: "Vaporwave", swatch: "from-[#ff5cc8] to-[#38e1ff]" },
  { id: "grunge", label: "Grunge", swatch: "from-[#181614] to-[#ff5c3c]" },
  { id: "comic", label: "Comic", swatch: "from-[#ffdc3c] to-[#e61e3c]" },
];
const AWARDS = [
  "Best Punchline", "Most Emotional Damage", "Funniest Chorus", "Best Flow", "Most Creative Diss",
  "Worst Friend of the Year", "Most Likely to End a Friendship", "Legendary Roast",
];

function Option({ item, checked, onToggle }: { item: { id: FactoryItem; label: string; hint: string }; checked: boolean; onToggle: () => void }) {
  return (
    <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition ${checked ? "border-volt bg-volt/5" : "border-line hover:border-grape/60"}`}>
      <input type="checkbox" checked={checked} onChange={onToggle} className="mt-1 accent-volt" />
      <span>
        <span className="block text-sm font-semibold">{item.label}</span>
        <span className="block text-xs text-muted">{item.hint}</span>
      </span>
    </label>
  );
}

export default function MemeFactoryPage() {
  const params = useSearchParams();
  const tracks = useLoad(() => api.assets("kind=song,beat&limit=100"));
  const trolls = (tracks.data ?? []).filter((a) => a.meta?.troll);
  const [picked, setPicked] = useState(params.get("asset") ?? "");
  const [items, setItems] = useState<FactoryItem[]>(["vertical_video", "concert_poster", "reaction_meme"]);
  const [theme, setTheme] = useState("neon");
  const [award, setAward] = useState(AWARDS[1]);
  const [line, setLine] = useState("");
  const [lines, setLines] = useState<string[]>([]);
  const [results, setResults] = useState<Asset[]>([]);
  const [zipError, setZipError] = useState<string | null>(null);
  const runner = useJobRunner();

  const assetId = picked || trolls[0]?.id || "";
  const track = trolls.find((t) => t.id === assetId) ?? null;
  const lyricsId = track?.meta?.troll?.lyrics_asset_id ?? null;

  useEffect(() => {
    let live = true;
    if (!lyricsId) return;
    api.asset<Lyrics>(lyricsId).then(
      (lyrics) => live && setLines(Array.from(new Set(lyrics.content?.sections.flatMap((s) => s.lines) ?? []))),
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, [lyricsId]);

  const toggle = (id: FactoryItem) => setItems((list) => (list.includes(id) ? list.filter((i) => i !== id) : [...list, id]));

  async function make() {
    if (!assetId) return;
    setResults([]);
    const done = await runner.run(() =>
      api.memeFactory({ asset_id: assetId, items, theme, award: items.includes("award_card") ? award : null, line: line || null }),
    );
    if (done) setResults((await Promise.all(done.result_asset_ids.map((id) => api.asset(id)))).filter((a) => a.has_file));
  }

  return (
    <div className="space-y-8">
      <header className="rise">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.25em] text-grape">Meme Factory</p>
        <h1 className="font-display text-4xl font-black tracking-tight sm:text-5xl">MAKE IT VIRAL-ISH.</h1>
        <p className="mt-3 max-w-xl text-muted">Turn a troll into Stories, TikToks, Shorts, posters, awards and memes. Download one or grab the whole pack.</p>
      </header>

      {tracks.error && <Notice>{tracks.error}</Notice>}
      {!tracks.loading && !trolls.length && (
        <Empty title="Nothing to turn into memes yet">
          <p>Make a troll on the home page first.</p>
          <ButtonLink href="/" variant="primary" className="mt-4">Roast someone</ButtonLink>
        </Empty>
      )}

      {!!trolls.length && (
        <>
          <label className="block text-xs font-medium text-muted">
            Which troll?
            <select className="control mt-1" value={assetId} onChange={(e) => { setPicked(e.target.value); setLine(""); setLines([]); }}>
              {trolls.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title} · {t.meta?.troll?.label} · {t.meta?.troll?.artist}
                </option>
              ))}
            </select>
          </label>

          <div className="grid gap-6 lg:grid-cols-2">
            <section>
              <p className="mb-2 font-display text-sm font-bold uppercase tracking-wide">Videos</p>
              <div className="space-y-2">{VIDEOS.map((item) => <Option key={item.id} item={item} checked={items.includes(item.id)} onToggle={() => toggle(item.id)} />)}</div>
              <p className="mt-2 text-xs text-muted">Still images with motion, synced subtitles and a dramatic intro card. No AI video model.</p>
            </section>
            <section>
              <p className="mb-2 font-display text-sm font-bold uppercase tracking-wide">Images</p>
              <div className="space-y-2">{IMAGES.map((item) => <Option key={item.id} item={item} checked={items.includes(item.id)} onToggle={() => toggle(item.id)} />)}</div>
            </section>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-2 text-xs font-medium text-muted">Theme</p>
              <div className="flex flex-wrap gap-2">
                {THEMES.map((t) => (
                  <button key={t.id} type="button" aria-pressed={theme === t.id} onClick={() => setTheme(t.id)} className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition ${theme === t.id ? "border-volt" : "border-line hover:border-grape/60"}`}>
                    <span className={`h-4 w-4 rounded-full bg-gradient-to-br ${t.swatch}`} aria-hidden /> {t.label}
                  </button>
                ))}
              </div>
            </div>
            {items.includes("award_card") && (
              <label className="block text-xs font-medium text-muted">
                Award
                <select className="control mt-1" value={award} onChange={(e) => setAward(e.target.value)}>
                  {AWARDS.map((a) => <option key={a}>{a}</option>)}
                </select>
              </label>
            )}
          </div>
          {!!lines.length && (
            <label className="block text-xs font-medium text-muted">
              Featured line (posters, cards and memes)
              <select className="control mt-1" value={line} onChange={(e) => setLine(e.target.value)}>
                <option value="">The chorus&apos;s biggest line</option>
                {lines.map((l) => <option key={l}>{l}</option>)}
              </select>
            </label>
          )}

          <Button variant="primary" className="w-full !py-4 font-display text-lg" disabled={!items.length || runner.busy} busy={runner.busy} onClick={make}>
            {!runner.busy && <Factory size={18} />} {runner.busy ? "Manufacturing memes…" : `Make ${items.length} thing${items.length === 1 ? "" : "s"}`}
          </Button>
          <JobStatus runner={runner} />
        </>
      )}

      {!!results.length && (
        <section className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-display text-xl font-black uppercase">Fresh off the line</h2>
            <Button
              onClick={async () => {
                setZipError(null);
                try {
                  await downloadZip(results.map((r) => r.id), `${track?.title ?? "troll"} meme pack`);
                } catch (reason) {
                  setZipError(errorMessage(reason));
                }
              }}
            >
              <PackageOpen size={15} /> Download all (ZIP)
            </Button>
          </div>
          {zipError && <Notice>{zipError}</Notice>}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {results.map((asset) => (
              <Card key={asset.id} className="overflow-hidden">
                <div className="flex aspect-square items-center justify-center bg-black/40">
                  {asset.mime_type?.startsWith("video/") ? (
                    <video controls playsInline preload="metadata" src={fileUrl(asset)} className="max-h-full max-w-full" />
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element -- served by the API with a signed URL
                    <img src={fileUrl(asset)} alt={asset.title} className="max-h-full max-w-full object-contain" />
                  )}
                </div>
                <div className="space-y-2 p-3">
                  <p className="truncate text-sm font-semibold">{asset.title}</p>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {asset.meta?.parody ? <Badge>Parody · built-in design</Badge> : <OriginBadge asset={asset} />}
                    {asset.meta?.aspect && <Badge>{asset.meta.aspect}</Badge>}
                  </div>
                  <a href={fileUrl(asset, true)} className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-fg">
                    <Download size={12} /> Download
                  </a>
                </div>
              </Card>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
