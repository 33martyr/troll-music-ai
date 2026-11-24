"use client";

import { AlertTriangle, Loader2, Pause, Play, RotateCcw, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/** Only one track plays at a time across the app: starting one pauses the rest. */
const playing = new Set<HTMLAudioElement>();
function claim(audio: HTMLAudioElement) {
  for (const other of playing) if (other !== audio) other.pause();
  playing.add(audio);
}

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/**
 * The app's audio player: play/pause, seekable progress with time, mute and
 * volume, buffering and error states. It only ever plays the real file at
 * `src`; if that fails to load it says so instead of pretending.
 */
export function TrackPlayer({
  src,
  label,
  autoPlay = false,
  compact = false,
  knownDuration,
  lazy = false,
  onTime,
}: {
  src: string;
  /** Accessible name, e.g. the track title. */
  label: string;
  autoPlay?: boolean;
  compact?: boolean;
  /** Duration from the asset's metadata, shown before the file loads. */
  knownDuration?: number | null;
  /** In long lists: fetch nothing until the user presses play. */
  lazy?: boolean;
  onTime?: (seconds: number) => void;
}) {
  const audio = useRef<HTMLAudioElement>(null);
  const [isPlaying, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(knownDuration ?? 0);
  const [buffering, setBuffering] = useState(false);
  const [failed, setFailed] = useState(false);
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(1);

  useEffect(() => {
    const element = audio.current;
    return () => {
      if (element) {
        element.pause();
        playing.delete(element);
      }
    };
  }, []);

  async function toggle() {
    const element = audio.current;
    if (!element) return;
    if (!element.paused) {
      element.pause();
      return;
    }
    claim(element);
    try {
      await element.play();
    } catch (reason) {
      // Autoplay blocked or aborted by a newer play(): not an error worth showing.
      if ((reason as Error)?.name !== "AbortError" && (reason as Error)?.name !== "NotAllowedError") setFailed(true);
    }
  }

  function seek(value: number) {
    const element = audio.current;
    if (!element || !Number.isFinite(value)) return;
    element.currentTime = value;
    setTime(value);
    onTime?.(value);
  }

  const progress = duration > 0 ? Math.min(100, (time / duration) * 100) : 0;

  if (failed) {
    return (
      <div role="alert" className="flex items-center gap-3 rounded-2xl border border-danger/40 bg-danger/10 px-4 py-3 text-sm">
        <AlertTriangle size={16} className="shrink-0 text-danger" />
        <span className="min-w-0 flex-1">This audio couldn&apos;t be loaded. The backend may be offline or the file was deleted.</span>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs hover:bg-white/10"
          onClick={() => {
            setFailed(false);
            audio.current?.load();
          }}
        >
          <RotateCcw size={12} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-3 rounded-2xl border border-line bg-ink/60 ${compact ? "px-2.5 py-2" : "px-3 py-2.5"}`}>
      <audio
        ref={audio}
        src={src}
        preload={lazy ? "none" : "metadata"}
        autoPlay={autoPlay}
        onPlay={(e) => {
          claim(e.currentTarget);
          setPlaying(true);
        }}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onLoadedMetadata={(e) => Number.isFinite(e.currentTarget.duration) && setDuration(e.currentTarget.duration)}
        onDurationChange={(e) => Number.isFinite(e.currentTarget.duration) && setDuration(e.currentTarget.duration)}
        onTimeUpdate={(e) => {
          setTime(e.currentTarget.currentTime);
          onTime?.(e.currentTarget.currentTime);
        }}
        onWaiting={() => setBuffering(true)}
        onPlaying={() => setBuffering(false)}
        onCanPlay={() => setBuffering(false)}
        onError={() => setFailed(true)}
        className="hidden"
      />
      <button
        type="button"
        onClick={toggle}
        aria-label={`${isPlaying ? "Pause" : "Play"} ${label}`}
        className={`flex shrink-0 items-center justify-center rounded-full bg-volt text-ink shadow-[0_0_20px_-6px] shadow-volt transition hover:brightness-110 active:scale-95 ${
          compact ? "h-9 w-9" : "h-11 w-11"
        }`}
      >
        {buffering && isPlaying ? (
          <Loader2 size={compact ? 15 : 18} className="animate-spin" />
        ) : isPlaying ? (
          <Pause size={compact ? 15 : 18} fill="currentColor" />
        ) : (
          <Play size={compact ? 15 : 18} fill="currentColor" className="translate-x-px" />
        )}
      </button>
      <span className="w-10 shrink-0 text-right font-mono text-[11px] tabular-nums text-muted">{formatTime(time)}</span>
      <div className="relative h-5 min-w-0 flex-1">
        <div className="pointer-events-none absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 overflow-hidden rounded-full bg-line">
          <div className="h-full rounded-full bg-gradient-to-r from-grape to-volt" style={{ width: `${progress}%` }} />
        </div>
        <input
          type="range"
          min={0}
          max={duration || 0}
          step={0.1}
          value={Math.min(time, duration || 0)}
          disabled={!duration || (lazy && !isPlaying && time === 0)}
          onChange={(e) => seek(Number(e.target.value))}
          aria-label={`Seek in ${label}`}
          aria-valuetext={`${formatTime(time)} of ${formatTime(duration)}`}
          className="player-range absolute inset-0 w-full cursor-pointer"
        />
      </div>
      <span className="w-10 shrink-0 font-mono text-[11px] tabular-nums text-muted">{formatTime(duration)}</span>
      {!compact && (
        <div className="hidden items-center gap-1.5 sm:flex">
          <button
            type="button"
            onClick={() => {
              const next = !muted;
              setMuted(next);
              if (audio.current) audio.current.muted = next;
            }}
            aria-label={muted ? "Unmute" : "Mute"}
            className="rounded-lg p-1 text-muted hover:text-fg"
          >
            {muted || volume === 0 ? <VolumeX size={16} /> : <Volume2 size={16} />}
          </button>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={muted ? 0 : volume}
            onChange={(e) => {
              const value = Number(e.target.value);
              setVolume(value);
              setMuted(value === 0);
              if (audio.current) {
                audio.current.volume = value;
                audio.current.muted = value === 0;
              }
            }}
            aria-label="Volume"
            className="player-range w-16 cursor-pointer"
          />
        </div>
      )}
    </div>
  );
}
