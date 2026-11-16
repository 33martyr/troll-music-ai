"""Turns raw model output into validated lyrics.

Models wrap JSON in prose or code fences, return lines as one string, or invent
section types. The parser tolerates all of that and fails with
:class:`LyricsParseError` only when there is nothing usable.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..errors import LyricsParseError
from ..types import Lyrics, LyricSection, SectionType

_TYPE_ALIASES = {
    "hook": SectionType.CHORUS,
    "refrain": SectionType.CHORUS,
    "pre-chorus": SectionType.BRIDGE,
    "prechorus": SectionType.BRIDGE,
    "interlude": SectionType.BRIDGE,
    "ending": SectionType.OUTRO,
}


def _close_arrays(text: str) -> str:
    """Repair the commonest JSON slips of small models in a list of sections:

    * an array closed with ``}`` instead of ``]}``: ``"lines": ["a", "b"}``
    * an object never closed before the next one: ``"lines": ["a"], {"type": ...``
    """
    out: list[str] = []
    stack: list[str] = []
    in_string = escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{" and stack and stack[-1] == "{":
            # Inside an object a "{" can only follow a key. After a comma it
            # means the previous object was never closed: close it.
            last = len(out) - 1
            while last >= 0 and out[last].isspace():
                last -= 1
            if last >= 0 and out[last] == ",":
                out[last] = "},"
                stack.pop()
            stack.append(char)
        elif char in "{[":
            stack.append(char)
        elif char == "}" and stack and stack[-1] == "[":
            out.append("]")  # the array was never closed
            stack.pop()
            if stack:
                stack.pop()
        elif char in "}]" and stack:
            stack.pop()
        out.append(char)
    # Anything still open at the end (a reply cut short or missing its closers).
    if in_string:
        out.append('"')
    out.extend("]" if opener == "[" else "}" for opener in reversed(stack))
    return "".join(out)


def _flatten_sections(raw_sections: list) -> list:
    """Sections a model nested inside another section (``{..., "sections": [...]}``)
    are lifted back into the flat list, in order."""
    flat: list = []
    for raw in raw_sections:
        flat.append(raw)
        if isinstance(raw, dict) and isinstance(raw.get("sections"), list):
            flat.extend(_flatten_sections(raw["sections"]))
    return flat


def extract_json(text: str) -> dict[str, Any]:
    """Return the first JSON object found in ``text``.

    If the outermost object does not parse, one repair is tried before falling
    back to any smaller object inside it.
    """
    decoder = json.JSONDecoder()
    first = text.find("{")
    if first != -1:
        for candidate in (text, _close_arrays(text)):
            try:
                value, _ = decoder.raw_decode(candidate, first)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    position = text.find("{", first + 1) if first != -1 else -1
    while position != -1:
        try:
            value, _ = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            position = text.find("{", position + 1)
            continue
        if isinstance(value, dict):
            return value
        position = text.find("{", position + 1)
    raise LyricsParseError("The model did not return a JSON object.")


def _clean_lines(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = raw.splitlines()
    if not isinstance(raw, list):
        return []
    lines: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        for part in item.splitlines():
            part = part.strip()
            if part:
                lines.append(part)
    return lines


def _section_type(raw_type: Any, label: str) -> SectionType:
    for candidate in (raw_type, label):
        key = re.sub(r"[\s\d]+$", "", str(candidate or "")).strip().lower()
        if key in SectionType._value2member_map_:
            return SectionType(key)
        if key in _TYPE_ALIASES:
            return _TYPE_ALIASES[key]
    return SectionType.VERSE


def _bpm(raw: Any) -> int | None:
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return None
    return value if 40 <= value <= 240 else None


def parse_lyrics(text: str, *, language: str = "English", explicit: bool = False) -> Lyrics:
    data = extract_json(text)
    raw_sections = data.get("sections")
    if not isinstance(raw_sections, list):
        raise LyricsParseError("The model's response has no 'sections' list.")

    sections: list[LyricSection] = []
    verse_count = 0
    for raw in _flatten_sections(raw_sections):
        if not isinstance(raw, dict):
            continue
        lines = _clean_lines(raw.get("lines"))
        if not lines:
            continue
        label = " ".join(str(raw.get("label") or "").split())  # also folds non-breaking spaces
        section_type = _section_type(raw.get("type"), label)
        if section_type is SectionType.VERSE:
            verse_count += 1
        if not label:
            label = (
                f"Verse {verse_count}"
                if section_type is SectionType.VERSE
                else section_type.value.capitalize()
            )
        performer = str(raw.get("performer") or "").strip()[:60] or None
        sections.append(LyricSection(type=section_type, label=label[:60], lines=lines, performer=performer))

    if not sections:
        raise LyricsParseError("The model's response contained no lyric lines.")

    notes = data.get("beat_notes")
    genre = data.get("suggested_genre")
    return Lyrics(
        title=(str(data.get("title") or "").strip() or "Untitled")[:120],
        sections=sections,
        suggested_bpm=_bpm(data.get("suggested_bpm")),
        suggested_genre=str(genre).strip()[:60] if genre else None,
        beat_notes=_clean_lines(notes)[:8],
        language=language,
        explicit=explicit,
    )


def parse_section_lines(text: str) -> list[str]:
    lines = _clean_lines(extract_json(text).get("lines"))
    if not lines:
        raise LyricsParseError("The model's response contained no lines for the section.")
    return lines


_HEADER = re.compile(r"\[(.{1,60})\]|(?:intro|verse|chorus|hook|bridge|outro)[ \d]*:?", re.IGNORECASE)


def parse_plain_text(text: str, title: str = "Untitled", *, language: str = "English") -> Lyrics:
    """Turn pasted lyrics into sections.

    ``[Verse 1]`` style headers start a section; without headers, blank lines
    separate verses.
    """
    sections: list[LyricSection] = []
    label: str | None = None
    lines: list[str] = []

    def flush() -> None:
        nonlocal label, lines
        if lines:
            name = label or f"Verse {sum(s.type is SectionType.VERSE for s in sections) + 1}"
            sections.append(LyricSection(type=_section_type(None, name), label=name[:60], lines=lines))
        label, lines = None, []

    for raw in text.splitlines():
        line = raw.strip()
        header = _HEADER.fullmatch(line)
        if header:
            flush()
            label = (header.group(1) or line.rstrip(":")).strip().title()
        elif not line:
            if label is None:
                flush()
        else:
            lines.append(line)
    flush()
    if not sections:
        raise LyricsParseError("There are no lyric lines in that text.")
    return Lyrics(title=title.strip()[:120] or "Untitled", sections=sections, language=language)


def parse_characters(text: str) -> list[dict]:
    data = extract_json(text)
    raw = data.get("characters")
    found = [c for c in raw if isinstance(c, dict) and str(c.get("name") or "").strip()] if isinstance(raw, list) else []
    if len(found) < 2:
        raise LyricsParseError("The model did not return two characters.")
    return [
        {
            "name": str(c["name"]).strip()[:60],
            "personality": str(c.get("personality") or "").strip()[:300],
            "style": str(c.get("style") or "").strip()[:120],
        }
        for c in found[:2]
    ]
