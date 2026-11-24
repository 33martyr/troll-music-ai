/**
 * Pure helpers behind the generation timeline and the audio player. No React
 * here, so they run under Node's own test runner (see lib/timeline.test.ts).
 */

export type TrollKindLike = string;

/** Stage labels the backend writes into job.stage ("<label> · <detail>"), in run order. */
export const STEPS = {
  words: { label: "Writing the lyrics", emoji: "✍️" },
  vocals: { label: "Recording the vocals", emoji: "🎤" },
  sing: { label: "Performing the song", emoji: "🎙️" },
  beat: { label: "Building the beat", emoji: "🥁" },
  mix: { label: "Mixing the track", emoji: "🎚️" },
  cover: { label: "Designing the cover", emoji: "🖼️" },
  video: { label: "Rendering the video", emoji: "🎬" },
} as const;
export type StepId = keyof typeof STEPS;

const SPOKEN: StepId[] = ["vocals", "beat", "mix"];

/** Which stages a troll job will run, mirroring backend/services/troll_jobs.py. */
export function planSteps(
  kind: TrollKindLike,
  opts: { video?: boolean; cover?: boolean; reuseLyrics?: boolean; rewrite?: boolean; sung?: boolean } = {},
): StepId[] {
  const steps: StepId[] = [];
  const beatOnly = kind === "funny_beat";
  if (!beatOnly && (!opts.reuseLyrics || opts.rewrite)) steps.push("words");
  if (!beatOnly && opts.sung) {
    // A music model that sings returns the finished song in one call: no separate beat or mix.
    steps.push("sing");
  } else {
    if (!beatOnly) steps.push("vocals");
    steps.push("beat");
    if (!beatOnly) steps.push("mix");
  }
  if (opts.cover !== false || beatOnly) steps.push("cover");
  if (kind === "meme_video" || opts.video) steps.push("video");
  return steps;
}

/** True when the job reports a spoken-pipeline stage although singing was planned (the singer failed). */
export function fellBackToSpoken(planned: StepId[], stage: string): boolean {
  return planned.includes("sing") && SPOKEN.some((id) => stage.startsWith(STEPS[id].label));
}

/** The planned steps with "sing" replaced by the spoken pipeline's stages. */
export function spokenSteps(planned: StepId[]): StepId[] {
  return planned.flatMap((id) => (id === "sing" ? SPOKEN : [id]));
}

/** Index of the step the job's stage line belongs to, or -1. */
export function currentStep(steps: StepId[], stage: string): number {
  return steps.findIndex((id) => stage.startsWith(STEPS[id].label));
}

/** 75 -> "1:15". Anything that is not a finite, non-negative number shows as 0:00. */
export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** Something that can be paused: an <audio> element, or a stand-in in tests. */
export interface Pausable {
  pause(): void;
}

/** Only one track plays at a time: claiming one pauses every other claimed player. */
export function exclusivePlayback<T extends Pausable>() {
  const playing = new Set<T>();
  return {
    claim(player: T) {
      for (const other of playing) if (other !== player) other.pause();
      playing.add(player);
    },
    release(player: T) {
      playing.delete(player);
    },
    get size() {
      return playing.size;
    },
  };
}
