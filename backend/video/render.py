"""Renders a music video from still images with FFmpeg.

Each scene is one image with a slow zoom (the Ken Burns effect) and a fade at
both ends. Scenes are joined, the audio is attached and, optionally, timed
lyrics are burned in. The result is a real H.264/AAC MP4.

This is the fallback renderer: it is used whenever no video-generation model is
configured, which today is always.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.audio import ffmpeg

FPS = 25
SIZES = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1024, 1024)}


@dataclass
class Scene:
    image: Path
    start: float
    end: float


@dataclass
class Caption:
    text: str
    start: float
    end: float


def _ass_time(seconds: float) -> str:
    hours, rest = divmod(max(0.0, seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def write_subtitles(captions: list[Caption], path: Path, width: int, height: int) -> Path:
    """Write an ASS subtitle file styled for lyrics."""
    size = max(28, height // 15)
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
        f"Style: Lyric,Arial,{size},&H00FFFFFF,&H00000000,&H96000000,1,1,3,1,2,60,60,{height // 12}\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Text\n"
    )
    events = []
    for caption in captions:
        text = caption.text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")
        events.append(f"Dialogue: 0,{_ass_time(caption.start)},{_ass_time(caption.end)},Lyric,{text}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return path


def render_video(
    scenes: list[Scene],
    target: Path,
    workdir: Path,
    *,
    aspect: str = "16:9",
    audio: Path | None = None,
    captions: list[Caption] | None = None,
    on_progress=None,
) -> tuple[int, int, float]:
    """Render to ``target`` (MP4). Returns ``(width, height, duration)``."""
    width, height = SIZES[aspect]
    clips = []
    for index, scene in enumerate(scenes):
        seconds = max(0.6, scene.end - scene.start)
        frames = max(2, round(seconds * FPS))
        fade = min(0.4, seconds / 4)
        # Alternate zooming in and out so consecutive scenes feel different.
        zoom = f"1+0.12*on/{frames}" if index % 2 == 0 else f"1.12-0.12*on/{frames}"
        chain = (
            f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
            f"crop={width * 2}:{height * 2},"
            f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={FPS},"
            f"fade=t=in:st=0:d={fade:.2f},fade=t=out:st={seconds - fade:.2f}:d={fade:.2f},format=yuv420p"
        )
        clip = workdir / f"scene_{index:03d}.mp4"
        ffmpeg.run([
            "-loop", "1", "-i", str(scene.image), "-vf", chain, "-frames:v", str(frames),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), str(clip),
        ])
        clips.append(clip)
        if on_progress:
            on_progress(index + 1, len(scenes))

    listing = workdir / "scenes.txt"
    listing.write_text("".join(f"file '{clip.name}'\n" for clip in clips), encoding="utf-8")
    duration = sum(max(0.6, scene.end - scene.start) for scene in scenes)

    args = ["-f", "concat", "-safe", "0", "-i", listing.name]
    if audio is not None:
        args += ["-i", str(audio)]
    else:  # players and platforms expect an audio stream; add silence
        args += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    if captions:
        # The subtitles filter is run from the work directory with a bare file
        # name, which avoids Windows path escaping inside the filter graph.
        write_subtitles(captions, workdir / "lyrics.ass", width, height)
        args += ["-vf", "subtitles=lyrics.ass", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
    else:
        args += ["-c:v", "copy"]
    args += [
        "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target),
    ]
    ffmpeg.run(args, cwd=workdir)
    return width, height, duration
