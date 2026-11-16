"""Plain-text and Markdown rendering of lyrics."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..types import Lyrics


def to_text(lyrics: "Lyrics") -> str:
    blocks = [lyrics.title]
    for section in lyrics.sections:
        blocks.append("\n".join([f"[{section.label}]", *section.lines]))
    return "\n\n".join(blocks) + "\n"


def to_markdown(lyrics: "Lyrics") -> str:
    out = [f"# {lyrics.title}", ""]
    facts = []
    if lyrics.suggested_genre:
        facts.append(f"**Genre:** {lyrics.suggested_genre}")
    if lyrics.suggested_bpm:
        facts.append(f"**BPM:** {lyrics.suggested_bpm}")
    facts.append(f"**Language:** {lyrics.language}")
    out += [" · ".join(facts), ""]
    for section in lyrics.sections:
        out += [f"## {section.label}", ""]
        # Two trailing spaces force a line break inside a Markdown paragraph.
        out += [f"{line}  " for line in section.lines[:-1]] + section.lines[-1:]
        out.append("")
    if lyrics.beat_notes:
        out += ["## Beat notes", ""] + [f"- {note}" for note in lyrics.beat_notes] + [""]
    if lyrics.meta:
        label = "mock provider, placeholder text" if lyrics.meta.is_mock else lyrics.meta.provider
        model = f" ({lyrics.meta.model})" if lyrics.meta.model and not lyrics.meta.is_mock else ""
        out += ["---", f"Generated with TROLL-MUSIC-AI via {label}{model}.", ""]
    return "\n".join(out)
