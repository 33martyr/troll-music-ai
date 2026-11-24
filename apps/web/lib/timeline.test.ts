// Run with: npm test   (Node's built-in runner; no extra dependencies)
import assert from "node:assert/strict";
import { test } from "node:test";
import { currentStep, exclusivePlayback, fellBackToSpoken, formatTime, planSteps, spokenSteps } from "./timeline.ts";

test("spoken pipeline: words, vocals, beat, mix, cover", () => {
  assert.deepEqual(planSteps("diss_track"), ["words", "vocals", "beat", "mix", "cover"]);
});

test("a singing model replaces vocals, beat and mix with one real stage", () => {
  assert.deepEqual(planSteps("diss_track", { sung: true }), ["words", "sing", "cover"]);
  assert.deepEqual(planSteps("meme_video", { sung: true }), ["words", "sing", "cover", "video"]);
});

test("a funny beat never sings and never writes lyrics", () => {
  assert.deepEqual(planSteps("funny_beat", { sung: true }), ["beat", "cover"]);
});

test("a remix that keeps the lyrics skips the words stage", () => {
  assert.deepEqual(planSteps("roast", { reuseLyrics: true, sung: true }), ["sing", "cover"]);
  assert.deepEqual(planSteps("roast", { reuseLyrics: true, rewrite: true }), ["words", "vocals", "beat", "mix", "cover"]);
});

test("when the singer fails, the timeline follows the spoken stages the job really runs", () => {
  const planned = planSteps("diss_track", { sung: true });
  assert.equal(fellBackToSpoken(planned, "Performing the song · The AI singer is performing it"), false);
  assert.equal(fellBackToSpoken(planned, "Recording the vocals · starting"), true);
  assert.equal(fellBackToSpoken(planSteps("diss_track"), "Recording the vocals · starting"), false);
  const steps = spokenSteps(planned);
  assert.deepEqual(steps, ["words", "vocals", "beat", "mix", "cover"]);
  assert.equal(currentStep(steps, "Building the beat · Generating the beat with procedural"), 2);
  assert.equal(currentStep(steps, "Starting"), -1);
});

test("times format as m:ss and bad input is 0:00", () => {
  assert.equal(formatTime(0), "0:00");
  assert.equal(formatTime(75.9), "1:15");
  assert.equal(formatTime(3600), "60:00");
  assert.equal(formatTime(Number.NaN), "0:00");
  assert.equal(formatTime(Infinity), "0:00");
  assert.equal(formatTime(-3), "0:00");
});

test("starting one player pauses the others", () => {
  const players = exclusivePlayback<{ paused: boolean; pause(): void }>();
  const make = () => ({ paused: false, pause() { this.paused = true; } });
  const a = make(), b = make();
  players.claim(a);
  players.claim(b);
  assert.equal(a.paused, true);
  assert.equal(b.paused, false);
  players.claim(b); // claiming again does not pause itself
  assert.equal(b.paused, false);
  players.release(a);
  assert.equal(players.size, 1);
});
