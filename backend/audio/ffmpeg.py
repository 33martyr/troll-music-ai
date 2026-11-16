"""FFmpeg wrappers: probing, conversion, normalization, looping and mixing.

FFmpeg is run as a subprocess. The binary is taken from ``TROLL_FFMPEG_PATH``,
then ``PATH``, then the copy bundled with the ``imageio-ffmpeg`` package.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from troll_music_ai import TrollMusicError


class MediaError(TrollMusicError):
    """FFmpeg is missing or failed on a file we produced."""

    code = "media_error"


class InvalidMediaError(TrollMusicError):
    """A user-supplied file is not usable media."""

    code = "invalid_media"


_configured_path: str | None = None


def configure(path: str | None) -> None:
    global _configured_path
    _configured_path = path or None
    ffmpeg_exe.cache_clear()


@lru_cache
def ffmpeg_exe() -> str:
    candidates = [_configured_path, shutil.which("ffmpeg")]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise MediaError(
            "FFmpeg was not found. Install it, or: pip install imageio-ffmpeg"
        ) from exc


def available() -> tuple[bool, str]:
    try:
        exe = ffmpeg_exe()
        line = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=15).stdout.splitlines()[0]
        return True, f"{line} ({exe})"
    except (MediaError, OSError, IndexError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def run(args: list[str], *, cwd: Path | None = None, timeout: float = 1800) -> str:
    """Run FFmpeg; return stderr. Raises :class:`MediaError` on failure."""
    command = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-y", *args]
    try:
        done = subprocess.run(command, capture_output=True, cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise MediaError("FFmpeg timed out.") from exc
    stderr = done.stderr.decode("utf-8", "replace")
    if done.returncode != 0:
        tail = " | ".join(line.strip() for line in stderr.strip().splitlines()[-3:])
        raise MediaError(f"FFmpeg failed: {tail[:400]}")
    return stderr


@dataclass
class MediaInfo:
    duration: float
    has_audio: bool
    has_video: bool
    sample_rate: int | None = None
    width: int | None = None
    height: int | None = None


def probe(path: Path) -> MediaInfo:
    """Inspect a file. Raises :class:`InvalidMediaError` if FFmpeg cannot read it."""
    done = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-nostdin", "-i", str(path)], capture_output=True, timeout=60
    )
    text = done.stderr.decode("utf-8", "replace")
    duration = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", text)
    audio = re.search(r"Stream #.*Audio:.*?(\d+) Hz", text)
    video = re.search(r"Stream #.*Video:.*?(\d{2,5})x(\d{2,5})", text)
    if "Invalid data" in text or not (audio or video):
        raise InvalidMediaError("That file is not audio or video that FFmpeg can read.")
    seconds = 0.0
    if duration:
        hours, minutes, rest = duration.groups()
        seconds = int(hours) * 3600 + int(minutes) * 60 + float(rest)
    return MediaInfo(
        duration=seconds,
        has_audio=bool(audio),
        has_video=bool(video),
        sample_rate=int(audio[1]) if audio else None,
        width=int(video[1]) if video else None,
        height=int(video[2]) if video else None,
    )


def mean_volume_db(path: Path) -> float | None:
    stderr = run(["-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"])
    match = re.search(r"mean_volume: (-?\d+(?:\.\d+)?) dB", stderr)
    return float(match[1]) if match else None


def to_wav(source: Path, target: Path, *, sample_rate: int = 44100, channels: int = 2) -> Path:
    run(["-i", str(source), "-vn", "-ar", str(sample_rate), "-ac", str(channels), str(target)])
    return target


def read_mono(path: Path, sample_rate: int = 44100) -> np.ndarray:
    """Decode any audio file to a mono float32 array."""
    command = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-"]
    done = subprocess.run(command, capture_output=True, timeout=300)
    if done.returncode != 0:
        raise MediaError("FFmpeg could not decode an audio file.")
    return np.frombuffer(done.stdout, dtype="<f4").astype(np.float32)


def finalize_audio(
    source: Path,
    target: Path,
    *,
    duration: float | None = None,
    loop: bool = False,
    normalize: bool = True,
    fade_out: float = 1.5,
) -> Path:
    """Produce the delivery file: optional loop to length, trim, fade, loudness
    normalization (EBU R128, -14 LUFS) and MP3 encoding."""
    args: list[str] = []
    if loop:
        args += ["-stream_loop", "-1"]
    args += ["-i", str(source), "-vn"]
    filters = []
    if duration:
        args += ["-t", f"{duration:.3f}"]
        if fade_out > 0 and duration > fade_out * 2:
            filters.append(f"afade=t=out:st={duration - fade_out:.3f}:d={fade_out:.3f}")
    if normalize:
        filters.append("loudnorm=I=-14:TP=-1.0:LRA=11")
    if filters:
        args += ["-af", ",".join(filters)]
    run([*args, "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(target)])
    return target


def mix(
    beat: Path,
    vocals: Path,
    target: Path,
    *,
    duration: float,
    vocal_gain_db: float = 3.0,
    beat_gain_db: float = -4.0,
) -> Path:
    """Mix vocals over a beat that is looped or trimmed to ``duration``, with a
    light master chain (vocal high-pass and compression, bus loudness)."""
    fade_start = max(0.0, duration - 2.0)
    graph = (
        f"[0:a]volume={beat_gain_db}dB,atrim=0:{duration:.3f},afade=t=out:st={fade_start:.3f}:d=2[b];"
        f"[1:a]highpass=f=90,acompressor=threshold=-18dB:ratio=3:attack=5:release=120,volume={vocal_gain_db}dB[v];"
        "[b][v]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.0:LRA=11[out]"
    )
    run([
        "-stream_loop", "-1", "-i", str(beat), "-i", str(vocals), "-filter_complex", graph, "-map", "[out]",
        "-t", f"{duration:.3f}", "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(target),
    ])
    return target


def time_stretch(source: Path, target: Path, factor: float) -> Path:
    """Change speed without changing pitch. ``factor`` > 1 is faster."""
    run(["-i", str(source), "-af", f"atempo={min(2.0, max(0.5, factor)):.4f}", str(target)])
    return target
