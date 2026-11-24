"""Meme Factory artwork, drawn with Pillow (not an AI model).

Each maker takes an optional background picture (the troll's cover, which may
be AI-made) and draws the text design on top. Every design is an obvious
parody: invented award names, no real logos or platform branding, and a
small "PARODY" mark.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from .images import _font, _outlined

THEMES: dict[str, dict] = {
    "neon": {"label": "Neon", "bg": (14, 6, 30), "accent": (200, 255, 62), "second": (162, 89, 255), "text": (255, 255, 255)},
    "gold": {"label": "Gold", "bg": (20, 14, 4), "accent": (255, 204, 77), "second": (255, 140, 60), "text": (255, 246, 220)},
    "vaporwave": {"label": "Vaporwave", "bg": (40, 10, 60), "accent": (56, 225, 255), "second": (255, 92, 200), "text": (255, 255, 255)},
    "grunge": {"label": "Grunge", "bg": (24, 22, 20), "accent": (255, 92, 60), "second": (200, 190, 170), "text": (240, 236, 228)},
    "comic": {"label": "Comic", "bg": (255, 220, 60), "accent": (230, 30, 60), "second": (30, 90, 255), "text": (20, 20, 20)},
}

FORMATS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}


def _canvas(size: tuple[int, int], theme: dict, background: Path | None, dim: int = 140):
    """Theme colour, or the background picture cropped to fill and darkened."""
    from PIL import Image

    width, height = size
    canvas = Image.new("RGBA", size, (*theme["bg"], 255))
    if background and background.exists():
        with Image.open(background) as opened:
            picture = opened.convert("RGBA")
        scale = max(width / picture.width, height / picture.height)
        picture = picture.resize((int(picture.width * scale) + 1, int(picture.height * scale) + 1), Image.LANCZOS)
        left, top = (picture.width - width) // 2, (picture.height - height) // 2
        canvas = picture.crop((left, top, left + width, top + height))
        # Tint with the theme colour rather than plain black, so the theme reads on any picture.
        canvas = Image.alpha_composite(canvas, Image.new("RGBA", size, (*theme["bg"], dim)))
        glow = Image.new("RGBA", size, (*theme["second"], 0))
        from PIL import ImageDraw as _Draw

        _Draw.Draw(glow).ellipse((-width * 0.3, height * 0.55, width * 1.3, height * 1.6), fill=(*theme["second"], 70))
        canvas = Image.alpha_composite(canvas, glow)
    return canvas


def _centered(draw, text: str, y: float, width: int, font, fill, stroke: int = 0) -> float:
    """Draw centred text; returns the y below it."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    x = (width - (right - left)) / 2
    if stroke:
        _outlined(draw, (x, y), text, font, fill=(*fill, 255), stroke=stroke)
    else:
        draw.text((x, y), text, font=font, fill=(*fill, 255))
    return y + (bottom - top) * 1.25


def _wrapped(draw, text: str, y: float, width: int, size: int, fill, stroke: int = 0, max_lines: int = 4) -> float:
    font = _font(size)
    chars = max(6, int(width * 0.86 / (size * 0.56)))
    for line in textwrap.wrap(text, width=chars)[:max_lines]:
        y = _centered(draw, line, y, width, font, fill, stroke)
    return y


def _parody_mark(draw, width: int, height: int, theme: dict) -> None:
    font = _font(max(14, min(width, height) // 50))
    text = "PARODY · MADE WITH TROLL-MUSIC-AI"
    draw.text((width - draw.textlength(text, font=font) - 24, height - 24 - font.size), text, font=font, fill=(*theme["text"], 170))


def _save(image, out_path: Path) -> Path:
    target = out_path.with_suffix(".png")
    image.convert("RGB").save(target)
    return target


def concert_poster(out_path: Path, *, artist: str, title: str, target: str, theme: str = "neon", size: str = "9:16", background: Path | None = None) -> Path:
    """A fake gig poster: 'LIVE AND UNAPOLOGETIC', the artist, the 'tour' and a support act."""
    from PIL import ImageDraw

    look = THEMES.get(theme, THEMES["neon"])
    width, height = FORMATS[size]
    image = _canvas((width, height), look, background, dim=160)
    draw = ImageDraw.Draw(image)
    unit = min(width, height)
    y = height * 0.08
    y = _centered(draw, "ONE NIGHT ONLY", y, width, _font(unit // 22), look["accent"])
    y = _wrapped(draw, artist.upper(), y + unit * 0.02, width, unit // 8, look["text"], stroke=max(3, unit // 200), max_lines=2)
    y = _centered(draw, "LIVE AND UNAPOLOGETIC", y + unit * 0.02, width, _font(unit // 26), look["second"])
    y = _wrapped(draw, f"THE '{title.upper()}' TOUR", y + unit * 0.06, width, unit // 14, look["accent"], stroke=max(2, unit // 260), max_lines=3)
    y = _centered(draw, f"SPECIAL GUEST: {target.upper()}'S DIGNITY (CANCELLED)", y + unit * 0.05, width, _font(unit // 34), look["text"])
    footer = ["DOORS: WHENEVER THEY SHOW UP", "TICKETS: BORROWED FROM A FRIEND", "NO REFUNDS. NO REGRETS."]
    y = max(y + unit * 0.06, height * 0.72)
    for line in footer:
        y = _centered(draw, line, y, width, _font(unit // 32), look["text"])
    _parody_mark(draw, width, height, look)
    return _save(image, out_path)


AWARDS = (
    "Best Punchline", "Most Emotional Damage", "Funniest Chorus", "Best Flow", "Most Creative Diss",
    "Worst Friend of the Year", "Most Likely to End a Friendship", "Legendary Roast",
)


def award_card(out_path: Path, *, award: str, artist: str, title: str, reason: str | None = None, theme: str = "gold", size: str = "1:1", background: Path | None = None) -> Path:
    """An award certificate from 'The Trollies' (an invented award)."""
    from PIL import ImageDraw

    look = THEMES.get(theme, THEMES["gold"])
    width, height = FORMATS[size]
    image = _canvas((width, height), look, background, dim=190)
    draw = ImageDraw.Draw(image)
    unit = min(width, height)
    margin = unit * 0.05
    draw.rectangle((margin, margin, width - margin, height - margin), outline=(*look["accent"], 255), width=max(4, unit // 120))
    draw.rectangle((margin * 1.6, margin * 1.6, width - margin * 1.6, height - margin * 1.6), outline=(*look["accent"], 140), width=max(2, unit // 300))
    y = height * 0.13
    y = _centered(draw, "THE TROLLIES", y, width, _font(unit // 13), look["accent"], stroke=max(2, unit // 260))
    y = _centered(draw, "ANNUAL ROAST AWARDS", y, width, _font(unit // 34), look["text"])
    y = _wrapped(draw, award.upper(), y + unit * 0.06, width, unit // 12, look["text"], stroke=max(3, unit // 220), max_lines=3)
    y = _centered(draw, "IS AWARDED TO", y + unit * 0.03, width, _font(unit // 32), look["second"])
    y = _wrapped(draw, artist.upper(), y + unit * 0.01, width, unit // 14, look["accent"], stroke=max(2, unit // 260), max_lines=2)
    y = _wrapped(draw, f"for “{title}”", y + unit * 0.01, width, unit // 30, look["text"], max_lines=2)
    if reason:
        _wrapped(draw, reason, y + unit * 0.04, int(width * 0.85), unit // 36, look["text"], max_lines=3)
    _parody_mark(draw, width, height, look)
    return _save(image, out_path)


def streaming_card(
    out_path: Path, *, artist: str, title: str, line: str | None, theme: str = "neon", size: str = "9:16",
    cover: Path | None = None, background: Path | None = None,
) -> Path:
    """A generic 'now playing' share card. Deliberately no real platform's look or name."""
    from PIL import Image, ImageDraw

    look = THEMES.get(theme, THEMES["neon"])
    width, height = FORMATS[size]
    image = _canvas((width, height), look, background, dim=200)
    draw = ImageDraw.Draw(image)
    unit = min(width, height)
    art = int(unit * (0.62 if size != "16:9" else 0.5))
    top = int(height * 0.12) if size == "9:16" else int((height - art) / 2) if size == "16:9" else int(height * 0.08)
    left = (width - art) // 2 if size != "16:9" else int(width * 0.08)
    if cover and cover.exists():
        with Image.open(cover) as opened:
            image.paste(opened.convert("RGB").resize((art, art), Image.LANCZOS), (left, top))
    else:
        draw.rectangle((left, top, left + art, top + art), fill=(*look["second"], 255))
    if size == "16:9":
        text_x, text_w = left + art + int(width * 0.04), int(width - left - art - width * 0.1)
        y = top + art * 0.2
        draw.text((text_x, y), "NOW PLAYING", font=_font(unit // 28), fill=(*look["accent"], 255))
        y += unit // 20
        for chunk in textwrap.wrap(title, width=max(8, int(text_w / (unit // 14 * 0.56))))[:3]:
            _outlined(draw, (text_x, y), chunk, _font(unit // 14), fill=(*look["text"], 255), stroke=2)
            y += unit // 12
        draw.text((text_x, y + 10), artist, font=_font(unit // 26), fill=(*look["second"], 255))
        bar_y, bar_x0, bar_x1 = top + art - unit * 0.05, text_x, text_x + text_w
    else:
        y = top + art + unit * 0.05
        y = _centered(draw, "NOW PLAYING", y, width, _font(unit // 30), look["accent"])
        y = _wrapped(draw, title, y, width, unit // 15, look["text"], stroke=2, max_lines=2)
        y = _centered(draw, artist, y, width, _font(unit // 26), look["second"])
        if line and size == "9:16":
            _wrapped(draw, f"“{line}”", y + unit * 0.06, int(width * 0.9), unit // 30, look["text"], max_lines=3)
        bar_y, bar_x0, bar_x1 = height * 0.86, width * 0.12, width * 0.88
    # A progress bar stuck at the most humiliating moment.
    draw.rounded_rectangle((bar_x0, bar_y, bar_x1, bar_y + 8), radius=4, fill=(*look["text"], 70))
    draw.rounded_rectangle((bar_x0, bar_y, bar_x0 + (bar_x1 - bar_x0) * 0.62, bar_y + 8), radius=4, fill=(*look["accent"], 255))
    small = _font(unit // 40)
    draw.text((bar_x0, bar_y + 16), "1:09", font=small, fill=(*look["text"], 200))
    draw.text((bar_x1 - draw.textlength("−0:42", font=small), bar_y + 16), "−0:42", font=small, fill=(*look["text"], 200))
    _parody_mark(draw, width, height, look)
    return _save(image, out_path)


def _initials(name: str) -> str:
    skip = {"the", "tha", "da", "of", "a", "an"}
    words = [w for w in name.replace("-", " ").split() if w[:1].isalnum() and w.lower() not in skip]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def _paste_square(image, picture: Path | None, box: tuple[int, int, int, int], fallback_colour, name: str = "") -> None:
    """Paste the portrait, or draw a placeholder: a silhouette with the rapper's initials."""
    from PIL import Image, ImageDraw

    left, top, right, bottom = box
    if picture and picture.exists():
        with Image.open(picture) as opened:
            art = opened.convert("RGB")
        side = min(art.size)
        art = art.crop(((art.width - side) // 2, (art.height - side) // 2, (art.width + side) // 2, (art.height + side) // 2))
        image.paste(art.resize((right - left, bottom - top), Image.LANCZOS), (left, top))
        return
    draw = ImageDraw.Draw(image)
    draw.rectangle(box, fill=(*fallback_colour, 255))
    w, h = right - left, bottom - top
    shade = tuple(max(0, int(c * 0.72)) for c in fallback_colour)
    # Head and shoulders, in a darker shade of the card colour.
    draw.ellipse((left + w * 0.32, top + h * 0.16, left + w * 0.68, top + h * 0.52), fill=(*shade, 255))
    draw.pieslice((left + w * 0.14, top + h * 0.56, left + w * 0.86, top + h * 1.44), 180, 360, fill=(*shade, 255))
    if name:
        font = _font(int(h * 0.2))
        text = _initials(name)
        tb = draw.textbbox((0, 0), text, font=font)
        draw.text((left + (w - (tb[2] - tb[0])) / 2 - tb[0], top + h * 0.34 - (tb[3] - tb[1]) / 2 - tb[1]), text, font=font,
                  fill=(255, 255, 255, 235), stroke_width=max(2, h // 120), stroke_fill=(0, 0, 0, 200))


def rapper_card(
    out_path: Path, *, name: str, catchphrase: str, style: str, stats: dict[str, int], overall: int,
    record: str | None = None, titles: list[str] | None = None, avatar: Path | None = None, theme: str = "neon",
) -> Path:
    """A collectible trading card: portrait, overall rating, five stats, catchphrase."""
    from PIL import Image, ImageDraw

    look = THEMES.get(theme, THEMES["neon"])
    width, height = 750, 1050
    image = Image.new("RGBA", (width, height), (*look["bg"], 255))
    draw = ImageDraw.Draw(image)
    for i in range(height):  # vertical gradient
        mix = i / height
        colour = tuple(int(look["bg"][c] * (1 - mix * 0.6) + look["second"][c] * mix * 0.6) for c in range(3))
        draw.line((0, i, width, i), fill=(*colour, 255))
    draw.rounded_rectangle((14, 14, width - 14, height - 14), radius=36, outline=(*look["accent"], 255), width=8)
    portrait = (95, 110, width - 95, 110 + width - 190)
    _paste_square(image, avatar, portrait, look["second"], name)
    draw = ImageDraw.Draw(image)
    draw.rectangle(portrait, outline=(*look["accent"], 255), width=4)
    # Overall badge, top-left, overlapping the portrait.
    draw.ellipse((34, 34, 174, 174), fill=(*look["accent"], 255), outline=(0, 0, 0, 255), width=4)
    number = str(overall)
    big = _font(64)
    draw.text((104 - draw.textlength(number, font=big) / 2, 62), number, font=big, fill=(0, 0, 0, 255))
    draw.text((width - 60 - draw.textlength(style.upper(), font=_font(30)), 60), style.upper(), font=_font(30), fill=(*look["text"], 255))
    y = portrait[3] + 16
    y = _centered(draw, name.upper()[:24], y, width, _font(58 if len(name) < 16 else 44), look["text"], stroke=3)
    if catchphrase:
        y = _wrapped(draw, f"“{catchphrase}”", y - 4, width, 26, look["accent"], max_lines=2)
    small = _font(28)
    col = [(70, "punchline"), (70, "flow"), (70, "comedy"), (width // 2 + 20, "creativity"), (width // 2 + 20, "reputation")]
    row_y = {0: y + 12, 1: y + 52, 2: y + 92, 3: y + 12, 4: y + 52}
    for index, (x, stat) in enumerate(col):
        value = stats.get(stat, 50)
        draw.text((x, row_y[index]), f"{value:>2} {stat.upper()[:5]}", font=small, fill=(*look["text"], 255))
    footer = record or ""
    if titles:
        footer = f"{footer}   {titles[0].upper()}".strip()
    if footer:
        _centered(draw, footer[:48], height - 92, width, _font(26), look["second"])
    draw.text((width - 210, height - 52), "FICTIONAL · PARODY", font=_font(20), fill=(*look["text"], 150))
    return _save(image, out_path)


def rivalry_poster(
    out_path: Path, *, a: str, b: str, record: str, tagline: str, avatar_a: Path | None = None, avatar_b: Path | None = None,
    champion: str | None = None, theme: str = "grunge", size: str = "9:16",
) -> Path:
    """A fight-night poster for two fictional rappers."""
    from PIL import ImageDraw

    look = THEMES.get(theme, THEMES["grunge"])
    width, height = FORMATS[size]
    image = _canvas((width, height), look, None)
    unit = min(width, height)
    side = int(unit * 0.42)
    top = int(height * 0.2) if size == "9:16" else int(height * 0.22)
    gap = int(unit * 0.04)
    left_a = width // 2 - side - gap // 2
    _paste_square(image, avatar_a, (left_a, top, left_a + side, top + side), look["accent"], a)
    _paste_square(image, avatar_b, (width // 2 + gap // 2, top, width // 2 + gap // 2 + side, top + side), look["second"], b)
    draw = ImageDraw.Draw(image)
    y = height * 0.05
    y = _centered(draw, "THE RIVALRY", y, width, _font(unit // 14), look["accent"], stroke=3)
    vs = _font(unit // 8)
    draw.text((width / 2 - draw.textlength("VS", font=vs) / 2, top + side / 2 - unit // 16), "VS", font=vs, fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255))
    y = top + side + unit * 0.03
    y = _wrapped(draw, f"{a.upper()}  vs  {b.upper()}", y, width, unit // 16, look["text"], stroke=3, max_lines=2)
    y = _centered(draw, f"RECORD: {record}", y + unit * 0.02, width, _font(unit // 26), look["accent"])
    if champion:
        y = _centered(draw, f"CHAMPION: {champion.upper()}", y, width, _font(unit // 26), look["second"])
    _wrapped(draw, tagline, y + unit * 0.04, int(width * 0.86), unit // 30, look["text"], max_lines=3)
    _parody_mark(draw, width, height, look)
    return _save(image, out_path)


def reaction_meme(out_path: Path, *, top: str, bottom: str, theme: str = "neon", size: str = "1:1", background: Path | None = None) -> Path:
    """Classic top-text / bottom-text meme, with the emotional damage sticker."""
    from PIL import ImageDraw

    look = THEMES.get(theme, THEMES["neon"])
    width, height = FORMATS[size]
    image = _canvas((width, height), look, background, dim=90)
    draw = ImageDraw.Draw(image)
    unit = min(width, height)
    stroke = max(3, unit // 140)
    _wrapped(draw, top.upper(), height * 0.04, width, unit // 11, (255, 255, 255), stroke=stroke, max_lines=3)
    chars = max(6, int(width * 0.86 / (unit // 11 * 0.56)))
    lines = textwrap.wrap(bottom.upper(), width=chars)[:3]
    _wrapped(draw, bottom.upper(), height * 0.96 - len(lines) * unit // 11 * 1.25, width, unit // 11, (255, 255, 255), stroke=stroke, max_lines=3)
    _parody_mark(draw, width, height, look)
    return _save(image, out_path)
