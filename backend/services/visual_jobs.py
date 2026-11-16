"""Music-video and artwork job handlers.

A video is planned as a storyboard (one scene per lyric section), each scene
gets one image from the image provider, and FFmpeg renders the stills with
motion, transitions, audio and timed lyrics into a real MP4. There is no
AI video-animation model in this pipeline, and the output is labelled so.
"""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

from backend.audio import ffmpeg
from backend.models.tables import Asset, AssetKind
from backend.services.assets import sources_of
from backend.video.render import SIZES, Caption, Scene, render_video
from backend.workers.runner import JobContext, JobHandler
from troll_music_ai import Lyrics, TrollMusicError
from troll_music_ai.lyrics import extract_json
from troll_music_ai.providers import ChatMessage, ImageGenerationProvider, TextRequest
from troll_music_ai.providers.images import intro_card, meme_cover, render_card
from troll_music_ai.types import ImageRequest

JOB_VIDEO = "video.generate"
JOB_ARTWORK = "artwork.generate"

MAX_SCENES = 24
MAX_SCENE_SECONDS = 10.0
AUDIO_KINDS = (AssetKind.SONG, AssetKind.BEAT, AssetKind.VOCALS)

STYLE_HINTS = {
    "meme": "internet meme aesthetic, bold, exaggerated, funny",
    "cartoon": "colourful cartoon illustration, thick outlines",
    "cinematic": "cinematic film still, dramatic lighting, shallow depth of field",
    "anime-inspired": "anime-inspired illustration, vivid colours",
    "surreal": "surreal dreamlike scene, impossible geometry",
    "3d animation": "3D animated film still, soft global illumination",
    "retro": "retro 1980s VHS aesthetic, neon, grain",
    "lyric video": "bold abstract background, strong shapes, space for text",
    "music montage": "energetic concert and street photography montage",
}


# ------------------------------ storyboard -------------------------------- #


def _split(start: float, end: float) -> list[tuple[float, float]]:
    """Cut a long span into equal parts no longer than MAX_SCENE_SECONDS."""
    parts = max(1, round((end - start) / MAX_SCENE_SECONDS + 0.49))
    step = (end - start) / parts
    return [(start + i * step, start + (i + 1) * step) for i in range(parts)]


def plan_scenes(duration: float, lyrics: Lyrics | None, timings: list[dict] | None) -> list[dict]:
    """Scene boundaries that follow the song's sections.

    With line timings the cuts land where each section actually starts; without
    them the duration is shared between sections by line count.
    """
    spans: list[tuple[float, float, str, list[str]]] = []
    if timings:
        groups: list[dict] = []
        for line in timings:
            if not groups or groups[-1]["id"] != line["section_id"]:
                groups.append({"id": line["section_id"], "label": line["label"], "start": line["start"], "lines": []})
            groups[-1]["lines"].append(line["text"])
        for index, group in enumerate(groups):
            start = 0.0 if index == 0 else group["start"]
            end = groups[index + 1]["start"] if index + 1 < len(groups) else duration
            if end - start >= 0.6:
                spans.append((start, min(end, duration), group["label"], group["lines"]))
    elif lyrics and lyrics.sections:
        total = sum(max(1, len(s.lines)) for s in lyrics.sections)
        cursor = 0.0
        for section in lyrics.sections:
            length = duration * max(1, len(section.lines)) / total
            spans.append((cursor, cursor + length, section.label, list(section.lines)))
            cursor += length
    else:
        count = max(1, round(duration / 6))
        spans = [(i * duration / count, (i + 1) * duration / count, f"Scene {i + 1}", []) for i in range(count)]

    scenes: list[dict] = []
    for start, end, label, lines in spans:
        pieces = _split(start, end)
        for part, (piece_start, piece_end) in enumerate(pieces):
            # Share the section's lines between its pieces, in order.
            lo, hi = part * len(lines) // len(pieces), (part + 1) * len(lines) // len(pieces)
            scenes.append({"start": round(piece_start, 3), "end": round(piece_end, 3), "label": label, "lines": lines[lo:hi] or lines[:1]})
    if len(scenes) > MAX_SCENES:  # merge neighbours until the plan fits
        ratio = len(scenes) / MAX_SCENES
        merged = []
        for i in range(MAX_SCENES):
            chunk = scenes[int(i * ratio) : max(int(i * ratio) + 1, int((i + 1) * ratio))]
            merged.append({**chunk[0], "end": chunk[-1]["end"], "lines": [line for s in chunk for line in s["lines"]]})
        scenes = merged
    scenes[-1]["end"] = round(duration, 3)
    for index, scene in enumerate(scenes):
        scene["index"] = index
    return scenes


def _template_descriptions(scenes: list[dict], title: str, style: str, notes: str | None) -> None:
    hint = STYLE_HINTS.get(style, style)
    for scene in scenes:
        subject = scene["lines"][0] if scene["lines"] else title
        scene["description"] = f"{scene['label']}: {subject}"
        scene["image_prompt"] = ", ".join(
            part for part in (f"{hint}", f"music video scene for a song called '{title}'", f"depicting: {subject}", notes, "no text, no watermark") if part
        )


def _llm_descriptions(context: JobContext, scenes: list[dict], title: str, style: str, notes: str | None) -> bool:
    """Ask the text model to direct each scene. Returns False if it cannot."""
    provider = context.providers.get("text")
    if provider is None or provider.info.is_mock:
        return False
    listing = "\n".join(
        f"{s['index'] + 1}. [{s['label']}, {s['end'] - s['start']:.0f}s] " + " / ".join(s["lines"][:4]) for s in scenes
    )
    messages = [
        ChatMessage(
            role="system",
            content=(
                "You are a music video director for comedy rap. For every numbered scene write one vivid, "
                "funny, family-safe visual. Never depict real people or brands. Reply with JSON only: "
                '{"scenes":[{"description":"one sentence","image_prompt":"detailed prompt for an image model, no text in image"}]} '
                "with exactly one entry per scene, in order."
            ),
        ),
        ChatMessage(
            role="user",
            content=f"Song: {title}\nVisual style: {style} ({STYLE_HINTS.get(style, style)})\nDirector notes: {notes or 'none'}\n\nScenes:\n{listing}",
        ),
    ]
    try:
        result = asyncio.run(provider.generate_text(TextRequest(messages=messages, temperature=0.8, max_tokens=3000, json_mode=context.providers.json_mode())))  # type: ignore[attr-defined]
        entries = extract_json(result.text).get("scenes")
    except TrollMusicError:
        return False
    if not isinstance(entries, list) or len(entries) != len(scenes):
        return False
    hint = STYLE_HINTS.get(style, style)
    for scene, entry in zip(scenes, entries):
        if not isinstance(entry, dict) or not str(entry.get("image_prompt", "")).strip():
            return False
        scene["description"] = str(entry.get("description") or entry["image_prompt"])[:400]
        scene["image_prompt"] = f"{str(entry['image_prompt'])[:900]}, {hint}, no text, no watermark"
    return True


def _captions(scenes: list[dict], timings: list[dict] | None, duration: float) -> list[Caption]:
    if timings:
        captions = []
        for index, line in enumerate(timings):
            following = timings[index + 1]["start"] if index + 1 < len(timings) else duration
            end = min(max(line["end"] + 0.4, line["start"] + 1.0), following, duration)
            if end > line["start"]:
                captions.append(Caption(line["text"], line["start"], end))
        return captions
    captions = []
    for scene in scenes:  # no timings: share each scene evenly between its lines
        lines = scene["lines"]
        step = (scene["end"] - scene["start"]) / max(1, len(lines))
        captions += [Caption(text, scene["start"] + i * step, scene["start"] + (i + 1) * step - 0.05) for i, text in enumerate(lines)]
    return captions


# -------------------------------- video ----------------------------------- #


def _image(context: JobContext, provider: ImageGenerationProvider | None, request: ImageRequest, target: Path) -> tuple[Path, bool]:
    """One image. Returns ``(path, used_fallback)``; a failing provider falls
    back to the built-in card so one bad scene does not lose the whole video."""
    if provider is not None:
        try:
            return asyncio.run(provider.generate_image(request, target)), False
        except TrollMusicError as exc:
            context.progress(context.job.progress, f"Image model failed ({exc.code}); using a title card")
    return render_card(request, target.with_suffix(".png")), True


def generate_video(context: JobContext) -> str:
    params = context.params
    audio = context.asset(params["audio_asset_id"], AUDIO_KINDS) if params.get("audio_asset_id") else None
    lyrics_asset: Asset | None = None
    if params.get("lyrics_asset_id"):
        lyrics_asset = context.asset(params["lyrics_asset_id"], AssetKind.LYRICS)
    elif audio is not None:
        lyrics_asset = next((a for relation, a in sources_of(context.session, audio.id) if relation == "lyrics"), None)
    lyrics = Lyrics.model_validate(lyrics_asset.content) if lyrics_asset and lyrics_asset.content else None

    audio_path = context.file_of(audio) if audio else None
    duration = ffmpeg.probe(audio_path).duration if audio_path else float(params.get("duration_seconds") or 20)
    if duration < 3:
        raise TrollMusicError("The audio is too short to make a video from.")
    timings = (audio.meta or {}).get("line_timings") if audio else None
    title = params.get("title") or (lyrics.title if lyrics else audio.title if audio else "Untitled")
    style, aspect = params.get("style") or "lyric video", params.get("aspect") or "16:9"
    width, height = SIZES[aspect]

    context.progress(0.03, "Planning the storyboard")
    scenes = plan_scenes(duration, lyrics, timings)
    directed = _llm_descriptions(context, scenes, title, style, params.get("notes"))
    if not directed:
        _template_descriptions(scenes, title, style, params.get("notes"))
    text_provider = context.providers.get("text")
    storyboard = context.store(
        None,
        kind=AssetKind.STORYBOARD,
        title=f"{title} · storyboard",
        info=text_provider.info if directed and text_provider else None,
        content={"title": title, "style": style, "aspect": aspect, "duration": round(duration, 2), "source": "llm" if directed else "template", "scenes": scenes},
        sources={"lyrics": lyrics_asset, "audio": audio},
    )
    if not directed:
        storyboard.provider, storyboard.is_ai = "template", False

    provider: ImageGenerationProvider | None = context.providers.get("image")  # type: ignore[assignment]
    info = context.using(provider) if provider else None
    seed = secrets.randbelow(2**31)
    stills: list[Scene] = []
    fallbacks = 0
    for scene in scenes:
        context.progress(0.08 + 0.52 * scene["index"] / len(scenes), f"Creating scene {scene['index'] + 1} of {len(scenes)}")
        request = ImageRequest(
            prompt=scene["image_prompt"], width=width, height=height, seed=seed + scene["index"],
            title=scene["label"], subtitle=(scene["lines"][0] if scene["lines"] else title)[:90],
        )
        intro = params.get("intro")
        if intro and scene["index"] == 0:
            # Dramatic opening card, drawn by the built-in renderer on purpose.
            path, fell_back = intro_card(
                context.workdir / "still_000.png", width=width, height=height,
                presenter=str(intro.get("presenter") or "TROLL-MUSIC-AI"), title=str(intro.get("title") or title), seed=seed,
            ), False
        else:
            path, fell_back = _image(context, provider, request, context.workdir / f"still_{scene['index']:03d}.png")
        fallbacks += fell_back
        stills.append(Scene(path, scene["start"], scene["end"]))

    subtitles = bool(params.get("subtitles", True)) and bool(timings or lyrics)
    captions = _captions(scenes, timings, duration) if subtitles else None

    def on_clip(done: int, total: int) -> None:
        context.progress(0.6 + 0.3 * done / total, f"Rendering scene {done} of {total}")

    target = context.workdir / "video.mp4"
    render_video(stills, target, context.workdir, aspect=aspect, audio=audio_path, captions=captions, on_progress=on_clip)
    context.progress(0.95, "Saving")
    media = ffmpeg.probe(target)
    drawn = len(scenes) - (1 if params.get("intro") else 0)
    all_fallback = provider is None or drawn == 0 or fallbacks >= drawn
    video = context.store(
        target,
        kind=AssetKind.VIDEO,
        title=title,
        info=None if all_fallback else info,
        mime_type="video/mp4",
        duration=media.duration,
        meta={
            "width": media.width or width,
            "height": media.height or height,
            "aspect": aspect,
            "style": style,
            "scenes": len(scenes),
            "subtitles": subtitles,
            "has_audio": audio is not None,
            # How the pictures move: FFmpeg pan/zoom over stills, not an AI video model.
            "renderer": "ffmpeg-stills",
            "image_provider": "typographic" if all_fallback else info.name if info else None,
            "image_fallbacks": fallbacks,
            "intro_card": bool(params.get("intro")),
            "storyboard_source": "llm" if directed else "template",
            "storyboard_asset_id": storyboard.id,
        },
        sources={"audio": audio, "lyrics": lyrics_asset, "storyboard": storyboard},
    )
    if all_fallback:
        video.provider, video.model, video.is_ai = "typographic", "troll-cards-1", False
    return video.id


# ------------------------------- artwork ---------------------------------- #


def generate_artwork(context: JobContext) -> str:
    from PIL import Image

    params = context.params
    lyrics_asset = context.asset(params["lyrics_asset_id"], AssetKind.LYRICS) if params.get("lyrics_asset_id") else None
    provider: ImageGenerationProvider = context.providers.require("image")  # type: ignore[assignment]
    info = context.using(provider)
    title, genre, style = params["title"], params.get("genre") or "hip-hop", params.get("style") or "cartoon"
    prompt = ", ".join(
        part
        for part in (
            f"album cover art for a {genre} track called '{title}'",
            STYLE_HINTS.get(style, style),
            f"{params['mood']} mood" if params.get("mood") else None,
            f"featuring {params['character']}" if params.get("character") else None,
            params.get("notes"),
            "square composition, striking, no text, no watermark",
        )
        if part
    )
    context.progress(0.1, f"Creating the cover with {info.name}")
    request = ImageRequest(prompt=prompt, width=1024, height=1024, seed=secrets.randbelow(2**31), title=title, subtitle=genre)
    raw = asyncio.run(provider.generate_image(request, context.workdir / "cover_raw.png"))
    context.progress(0.85, "Finishing")
    try:
        with Image.open(raw) as image:
            image = image.convert("RGB")
            side = min(image.size)
            left, top = (image.width - side) // 2, (image.height - side) // 2
            image = image.crop((left, top, left + side, top + side)).resize((1024, 1024), Image.LANCZOS)
            final = context.workdir / "cover.png"
            image.save(final, "PNG")
    except OSError as exc:
        raise TrollMusicError(f"{info.name} did not return a usable image.") from exc
    if params.get("artist"):
        # Fake-album-cover text and sticker, drawn by Pillow over the picture.
        final = meme_cover(final, context.workdir / "cover_meme.png", title=title, artist=params["artist"])
    return context.store(
        final,
        kind=AssetKind.ARTWORK,
        title=f"{title} · cover",
        info=info,
        mime_type="image/png",
        meta={"width": 1024, "height": 1024, "style": style, "prompt": prompt, "meme_overlay": bool(params.get("artist"))},
        sources={"lyrics": lyrics_asset},
    ).id


HANDLERS: dict[str, JobHandler] = {JOB_VIDEO: generate_video, JOB_ARTWORK: generate_artwork}
