"""Built-in procedural beat engine.

This is a drum machine and synthesizer written with NumPy, not an AI model.
It exists so the studio produces real, playable instrumentals on any machine,
with no GPU, download or API key. Tempo and duration are exact.

Every asset it makes is labelled as built-in (``ProviderInfo.is_ai = False``).
"""

from __future__ import annotations

import asyncio
import re
import wave
from pathlib import Path

import numpy as np

from ..types import BeatRequest
from .base import MusicCapabilities, MusicGenerationProvider, ProviderInfo, ProviderKind, ProviderStatus

SR = 44100
SCALES = {
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "major": [0, 2, 4, 5, 7, 9, 11],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
}
PROGRESSIONS = {
    "minor": [[0, 5, 2, 6], [0, 3, 5, 4], [0, 0, 5, 6], [0, 6, 5, 4]],
    "phrygian": [[0, 1, 0, 6], [0, 0, 1, 0], [0, 5, 1, 0]],
    "major": [[0, 4, 5, 3], [0, 3, 4, 4], [0, 5, 3, 4], [3, 4, 0, 5]],
}
# 16 steps per bar. x = hit. Each preset: tempo, drum patterns, swing, scale and layer levels.
PRESETS: dict[str, dict] = {
    "trap": dict(bpm=140, kick="x.....x...x.....", snare="........x.......", hat="x.x.x.x.x.x.x.x.", rolls=0.35, scale="minor", bass=1.0, pad=0.35, lead=0.5),
    "drill": dict(bpm=142, kick="x..x..x...x.x...", snare="....x.........x.", hat="x..x..x.x..x..x.", rolls=0.25, scale="phrygian", bass=1.0, pad=0.3, lead=0.45),
    "hiphop": dict(bpm=92, kick="x.....x.x.......", snare="....x.......x...", hat="x.x.x.x.x.x.x.x.", swing=0.12, scale="minor", bass=0.8, pad=0.45, lead=0.4),
    "boombap": dict(bpm=90, kick="x......x.x......", snare="....x.......x...", hat="x.x.x.x.x.x.x.x.", swing=0.18, scale="minor", bass=0.8, pad=0.4, lead=0.45),
    "phonk": dict(bpm=130, kick="x...x...x...x...", snare="....x.......x...", hat="..x...x...x...x.", scale="phrygian", bass=1.0, pad=0.2, lead=0.7, lead_wave="square"),
    "afrobeats": dict(bpm=108, kick="x..x..x...x..x..", snare="....x..x....x...", hat="x.xxx.xxx.xxx.xx", scale="major", bass=0.7, pad=0.4, lead=0.55),
    "reggaeton": dict(bpm=95, kick="x...x...x...x...", snare="...x..x....x..x.", hat="x.x.x.x.x.x.x.x.", scale="minor", bass=0.85, pad=0.35, lead=0.5),
    "edm": dict(bpm=128, kick="x...x...x...x...", snare="....x.......x...", hat="..x...x...x...x.", scale="minor", bass=0.8, pad=0.55, lead=0.65, lead_wave="square"),
    "lofi": dict(bpm=78, kick="x.....x...x.....", snare="....x.......x...", hat="x.x.x.x.x.x.x.x.", swing=0.2, scale="major", bass=0.6, pad=0.7, lead=0.4, soft=True),
    "pop": dict(bpm=116, kick="x.....x.x.....x.", snare="....x.......x...", hat="x.x.x.x.x.x.x.x.", scale="major", bass=0.7, pad=0.5, lead=0.5),
    "rock": dict(bpm=124, kick="x.....x.x...x...", snare="....x.......x...", hat="x.x.x.x.x.x.x.x.", scale="minor", bass=0.8, pad=0.7, lead=0.4, drive=True),
    "jazz": dict(bpm=120, kick="x.........x.....", snare="......x.......x.", hat="x..xx.x..xx.x..x", swing=0.3, scale="major", bass=0.7, pad=0.45, lead=0.5, walking=True, soft=True),
    "experimental": dict(bpm=110, kick="", snare="", hat="", scale="phrygian", bass=0.8, pad=0.5, lead=0.6, random=True),
}
NOTE_NAMES = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
HAPPY_MOODS = ("playful", "triumphant", "happy", "hype", "upbeat", "bright")
DARK_MOODS = ("dark", "aggressive", "melanchol", "petty", "sad", "menacing", "smug")


def preset_for(genre: str) -> dict:
    return PRESETS.get(re.sub(r"[^a-z]", "", genre.lower()), PRESETS["hiphop"])


def _parse_key(key: str | None) -> tuple[int | None, str | None]:
    match = re.match(r"\s*([a-gA-G])([#b]?)\s*(m(?:in(?:or)?)?|maj(?:or)?)?", key or "")
    if not match:
        return None, None
    root = (NOTE_NAMES[match[1].lower()] + {"#": 1, "b": -1, "": 0}[match[2]]) % 12
    quality = match[3] or ""
    return root, ("minor" if quality.lower().startswith("m") and not quality.lower().startswith("maj") else "major" if quality else None)


def _env(length: int, decay: float) -> np.ndarray:
    return np.exp(-np.arange(length) / (SR * decay))


def _kick() -> np.ndarray:
    n = int(SR * 0.4)
    freq = 45 + 110 * np.exp(-np.arange(n) / (SR * 0.035))
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * _env(n, 0.13)


def _snare(rng: np.random.Generator, soft: bool) -> np.ndarray:
    n = int(SR * 0.25)
    noise = rng.uniform(-1, 1, n) * _env(n, 0.03 if soft else 0.06)
    tone = np.sin(2 * np.pi * 185 * np.arange(n) / SR) * _env(n, 0.04)
    return 0.7 * noise + 0.5 * tone


def _hat(rng: np.random.Generator, decay: float) -> np.ndarray:
    n = int(SR * decay * 6)
    noise = np.diff(rng.uniform(-1, 1, n + 1))  # crude high-pass
    return noise * _env(n, decay) * 0.5


def _tone(midi: float, seconds: float, wave_shape: str, decay: float) -> np.ndarray:
    n = int(SR * seconds)
    phase = 2 * np.pi * 440 * 2 ** ((midi - 69) / 12) * np.arange(n) / SR
    if wave_shape == "square":
        signal = np.sign(np.sin(phase)) * 0.5
    elif wave_shape == "pad":
        signal = sum(np.sin(phase * h + h) / h for h in (1, 2, 3, 4)) * 0.5
    else:  # pluck
        signal = np.sin(phase) + 0.35 * np.sin(2 * phase) + 0.15 * np.sin(3 * phase)
    envelope = _env(n, decay)
    attack = min(n, int(SR * (0.08 if wave_shape == "pad" else 0.004)))
    envelope[:attack] *= np.linspace(0, 1, attack)
    release = min(n, int(SR * 0.02))
    envelope[-release:] *= np.linspace(1, 0, release)
    return signal * envelope


def _add(buffer: np.ndarray, start: int, sample: np.ndarray, gain: float) -> None:
    if 0 <= start < len(buffer):
        end = min(len(buffer), start + len(sample))
        buffer[start:end] += sample[: end - start] * gain


def render_beat(request: BeatRequest, seed: int = 0) -> tuple[np.ndarray, int]:
    """Return ``(stereo float array, bpm)`` for the request."""
    preset = preset_for(request.genre)
    rng = np.random.default_rng(seed)
    bpm = request.bpm or preset["bpm"]
    step = 60 / bpm / 4
    total = int(SR * request.duration_seconds)
    bars = int(np.ceil(request.duration_seconds / (step * 16)))
    energy = request.energy
    soft = preset.get("soft", False)

    key_root, key_scale = _parse_key(request.key)
    mood = (request.mood or "").lower()
    scale_name = key_scale or (
        "major" if any(m in mood for m in HAPPY_MOODS) and preset["scale"] != "phrygian"
        else "minor" if any(m in mood for m in DARK_MOODS) and preset["scale"] == "major"
        else preset["scale"]
    )
    scale = SCALES[scale_name]
    root = 36 + (key_root if key_root is not None else int(rng.integers(0, 12)))
    progression = PROGRESSIONS[scale_name][int(rng.integers(len(PROGRESSIONS[scale_name])))]

    def degree(index: int, octave: int = 0) -> int:
        return root + 12 * (octave + index // 7) + scale[index % 7]

    patterns = {name: preset[name] for name in ("kick", "snare", "hat")}
    if preset.get("random"):
        patterns = {
            "kick": "".join("x" if rng.random() < 0.28 or i == 0 else "." for i in range(16)),
            "snare": "".join("x" if rng.random() < 0.18 else "." for i in range(16)),
            "hat": "".join("x" if rng.random() < 0.5 else "." for i in range(16)),
        }

    wanted = " ".join(request.instruments).lower()
    lead_wave = preset.get("lead_wave", "pluck")
    if any(word in wanted for word in ("synth", "brass")):
        lead_wave = "square"
    pad_level = preset["pad"] * (1.5 if any(w in wanted for w in ("pad", "string")) else 1.0)
    lead_level = preset["lead"] * (1.4 if any(w in wanted for w in ("piano", "bell", "guitar", "flute", "lead")) else 1.0)
    bass_level = preset["bass"] * (1.25 if "808" in wanted or "bass" in wanted else 1.0)

    kick, snare = _kick(), _snare(rng, soft)
    closed_hat, open_hat = _hat(rng, 0.012), _hat(rng, 0.05)
    drums, bass, music = (np.zeros(total) for _ in range(3))
    arp = [int(x) for x in rng.permutation([0, 2, 4, 7, 4, 2, 9, 4])]
    intro_bars = 2 if bars >= 8 else 0
    swing = preset.get("swing", 0.0)

    for bar in range(bars):
        chord = progression[bar % 4]
        bar_start = bar * 16 * step
        full_drums = bar >= intro_bars
        fill = bar % 4 == 3 and energy >= 3
        _add(music, int(bar_start * SR), sum(_tone(degree(chord + d, 1), step * 16, "pad", 1.2) for d in (0, 2, 4)), 0.09 * pad_level)
        if preset.get("drive"):
            _add(music, int(bar_start * SR), np.tanh(4 * _tone(degree(chord, 0) + 7, step * 16, "pad", 0.9)), 0.05 * pad_level)

        for index in range(16):
            when = bar_start + index * step + (swing * step if index % 2 else 0)
            at = int(when * SR)
            if full_drums:
                if patterns["kick"][index : index + 1] == "x":
                    _add(drums, at, kick, 0.95)
                    if not preset.get("walking"):
                        _add(bass, at, np.tanh(2.2 * _tone(degree(chord, 0) - 12, step * (6 if index == 0 else 3), "sine", 0.35)), 0.5 * bass_level)
                if patterns["snare"][index : index + 1] == "x":
                    _add(drums, at, snare, 0.55 if soft else 0.75)
                if patterns["hat"][index : index + 1] == "x" and energy >= 2:
                    _add(drums, at, open_hat if index == 14 and energy >= 4 else closed_hat, 0.35 + 0.1 * (index % 4 == 0))
                    if rng.random() < preset.get("rolls", 0) * energy / 3:  # 32nd-note hat rolls
                        for sub in (1, 2, 3):
                            _add(drums, at + int(sub * step * SR / 4), closed_hat, 0.25)
                if fill and index >= 12 and rng.random() < 0.6:
                    _add(drums, at, snare, 0.4)
            if preset.get("walking") and index % 4 == 0:
                _add(bass, at, _tone(degree(chord + [0, 2, 4, 5][index // 4], 0) - 12, step * 4, "sine", 0.3), 0.55 * bass_level)
            density = (2 if energy <= 2 else 1) * (2 if soft else 1)
            if index % density == 0 and rng.random() < 0.35 + 0.1 * energy:
                note = degree(chord + arp[(bar * 16 + index) // density % len(arp)], 2)
                _add(music, at, _tone(note, step * 3, lead_wave, 0.18), 0.13 * lead_level)

    mix = drums * (0.6 + 0.08 * energy) + bass + music
    if soft:  # gentle low-pass for a dusty feel
        mix = np.convolve(mix, np.ones(6) / 6, mode="same")
    mix = np.tanh(mix * 1.3)
    fade = min(total, int(SR * min(2.0, request.duration_seconds / 6)))
    mix[-fade:] *= np.linspace(1, 0, fade)
    mix /= max(1e-6, float(np.max(np.abs(mix)))) / 0.9
    delayed = np.concatenate([np.zeros(180), mix[:-180]])  # tiny Haas offset for stereo width
    return np.stack([mix, 0.85 * mix + 0.15 * delayed], axis=1), bpm


def write_wav(path: Path, samples: np.ndarray, sample_rate: int = SR) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1 if pcm.ndim == 1 else pcm.shape[1])
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


class ProceduralBeatProvider(MusicGenerationProvider):
    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="procedural", kind=ProviderKind.MUSIC, model="troll-synth-1", is_ai=False)

    @property
    def capabilities(self) -> MusicCapabilities:
        return MusicCapabilities(exact_bpm=True, exact_duration=True, key_control=True)

    async def check(self) -> ProviderStatus:
        return ProviderStatus(ok=True, detail="Built-in synthesizer, always available. Not an AI model.")

    async def generate_instrumental(self, request: BeatRequest, out_path: Path, seed: int) -> Path:
        def work() -> Path:
            samples, _ = render_beat(request, seed)
            target = out_path.with_suffix(".wav")
            write_wav(target, samples)
            return target

        return await asyncio.to_thread(work)
