from .export import to_markdown, to_text
from .parser import extract_json, parse_lyrics, parse_plain_text, parse_section_lines
from .prompts import song_structure, troll_structure
from .service import LyricsService, battle_request_for, lyrics_request_for

__all__ = [
    "LyricsService",
    "battle_request_for",
    "lyrics_request_for",
    "extract_json",
    "parse_lyrics",
    "parse_plain_text",
    "parse_section_lines",
    "song_structure",
    "to_markdown",
    "to_text",
    "troll_structure",
]
