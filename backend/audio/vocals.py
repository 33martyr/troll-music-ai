"""Places spoken lines on a beat grid to make a rap-style vocal track.

Speech models do not rap in time by themselves. This module gives each line a
bar (or two when it is long), speeds over-long lines up slightly so they fit,
and records where every line landed so subtitles can be synchronized exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backend.audio import ffmpeg
from troll_music_ai.providers.procedural import SR, write_wav

MAX_SPEEDUP = 1.35
FILL = 0.94  # how much of its slot a line may occupy


@dataclass
class VocalLine:
    section_id: str
    section_label: str
    performer: str | None
    text: str
    audio: Path


def _trim_silence(samples: np.ndarray, threshold: float = 0.012) -> np.ndarray:
    loud = np.flatnonzero(np.abs(samples) > threshold)
    if loud.size == 0:
        return samples[:0]
    return samples[max(0, loud[0] - 400) : loud[-1] + 2000]


def build_vocal_track(
    lines: list[VocalLine], bpm: float, target: Path, workdir: Path, *, lead_in_bars: int = 2
) -> tuple[list[dict], float]:
    """Write the vocal track to ``target`` (WAV). Returns ``(timings, duration)``.

    Each timing is ``{section_id, label, performer, text, start, end}`` in seconds.
    """
    bar = 240.0 / bpm
    placed: list[tuple[int, np.ndarray]] = []
    timings: list[dict] = []
    cursor = lead_in_bars
    previous_section: str | None = None

    for index, line in enumerate(lines):
        if previous_section is not None and line.section_id != previous_section:
            cursor = math.ceil(cursor / 2) * 2  # sections start on an even bar
        previous_section = line.section_id

        samples = _trim_silence(ffmpeg.read_mono(line.audio, SR))
        if samples.size == 0:
            continue
        seconds = samples.size / SR
        slots = 1 if seconds / MAX_SPEEDUP <= bar * FILL else 2 if seconds / MAX_SPEEDUP <= 2 * bar * FILL else 4
        room = slots * bar * FILL
        if seconds > room:
            stretched = workdir / f"stretch_{index:03d}.wav"
            ffmpeg.time_stretch(line.audio, stretched, seconds / room)
            samples = _trim_silence(ffmpeg.read_mono(stretched, SR))
            seconds = samples.size / SR

        start = cursor * bar
        placed.append((int(start * SR), samples))
        timings.append(
            {
                "section_id": line.section_id,
                "label": line.section_label,
                "performer": line.performer,
                "text": line.text,
                "start": round(start, 3),
                "end": round(start + seconds, 3),
            }
        )
        cursor += slots

    total_bars = math.ceil(cursor / 2) * 2
    duration = total_bars * bar
    track = np.zeros(int(duration * SR) + SR, dtype=np.float32)
    for offset, samples in placed:
        end = min(track.size, offset + samples.size)
        track[offset:end] += samples[: end - offset]
    peak = float(np.max(np.abs(track))) if track.size else 0.0
    if peak > 0:
        track *= 0.9 / peak
    write_wav(target, track[: int(duration * SR)])
    return timings, duration
