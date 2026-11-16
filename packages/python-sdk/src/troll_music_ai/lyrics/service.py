"""Lyrics generation, section regeneration and rewriting."""

from __future__ import annotations

from collections.abc import Callable

from ..errors import LyricsParseError
from ..providers.base import ChatMessage, TextGenerationProvider, TextRequest
from ..types import BattleRequest, GenerationMeta, Lyrics, LyricsRequest, RewriteMode, SectionType
from . import prompts
from .parser import parse_characters, parse_lyrics, parse_section_lines

ProgressCallback = Callable[[float, str], None]


def _noop(_fraction: float, _stage: str) -> None:
    return None


class LyricsService:
    """Stateless: every method takes lyrics in and returns new lyrics out.

    Persistence and history belong to the caller.
    """

    def __init__(
        self,
        provider: TextGenerationProvider,
        *,
        max_attempts: int = 2,
        json_mode: bool = False,
    ) -> None:
        self._provider = provider
        self._max_attempts = max(1, max_attempts)
        self._json_mode = json_mode

    def _meta(self, model: str | None) -> GenerationMeta:
        info = self._provider.info
        return GenerationMeta(provider=info.name, model=model or info.model, is_mock=info.is_mock)

    async def _ask(self, messages: list[ChatMessage], parse, progress: ProgressCallback):
        """Call the model and parse; retry when the output is unusable."""
        last_error: LyricsParseError | None = None
        for attempt in range(1, self._max_attempts + 1):
            stage = "Writing" if attempt == 1 else f"Retrying (attempt {attempt})"
            progress(0.15, stage)
            result = await self._provider.generate_text(
                TextRequest(messages=messages, json_mode=self._json_mode)
            )
            progress(0.85, "Structuring the lyrics")
            try:
                return parse(result.text), result.model
            except LyricsParseError as exc:
                last_error = exc
        assert last_error is not None
        raise LyricsParseError(
            f"{last_error.message} Tried {self._max_attempts} time(s). "
            "A larger model usually fixes this."
        )

    async def generate(
        self, request: LyricsRequest, *, on_progress: ProgressCallback | None = None
    ) -> Lyrics:
        lyrics, model = await self._ask(
            prompts.generation_messages(request),
            lambda text: parse_lyrics(text, language=request.language, explicit=request.explicit),
            on_progress or _noop,
        )
        lyrics.meta = self._meta(model)
        return lyrics

    async def regenerate_section(
        self,
        lyrics: Lyrics,
        section_id: str,
        *,
        request: LyricsRequest | None = None,
        instruction: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> Lyrics:
        """Return a copy with one section rewritten and everything else intact.

        Regenerating a chorus updates every repeat of that same chorus.
        """
        target = lyrics.section(section_id)
        if target is None:
            raise ValueError(f"No section with id '{section_id}'.")

        new_lines, model = await self._ask(
            prompts.section_messages(lyrics, target, request, instruction),
            parse_section_lines,
            on_progress or _noop,
        )

        updated = lyrics.model_copy(deep=True)
        for section in updated.sections:
            is_repeat = (
                target.type is SectionType.CHORUS
                and section.type is SectionType.CHORUS
                and section.lines == target.lines
            )
            if section.id == section_id or is_repeat:
                section.lines = list(new_lines)
        updated.meta = self._meta(model)
        return updated

    async def rewrite(
        self,
        lyrics: Lyrics,
        mode: RewriteMode,
        *,
        request: LyricsRequest | None = None,
        instruction: str | None = None,
        rhyme_scheme: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> Lyrics:
        rewritten, model = await self._ask(
            prompts.rewrite_messages(lyrics, mode, request, instruction, rhyme_scheme),
            lambda text: parse_lyrics(text, language=lyrics.language, explicit=lyrics.explicit),
            on_progress or _noop,
        )
        # A rewrite changes the words, not the song's identity.
        rewritten.title = lyrics.title
        rewritten.suggested_bpm = rewritten.suggested_bpm or lyrics.suggested_bpm
        rewritten.suggested_genre = rewritten.suggested_genre or lyrics.suggested_genre
        rewritten.beat_notes = rewritten.beat_notes or lyrics.beat_notes
        for old, new in zip(lyrics.sections, rewritten.sections):
            if old.type is new.type:
                new.id = old.id
        rewritten.meta = self._meta(model)
        return rewritten

    async def generate_battle(
        self, request: BattleRequest, *, on_progress: ProgressCallback | None = None
    ) -> Lyrics:
        """A rap battle is lyrics whose verses carry a ``performer``."""
        lyrics, model = await self._ask(
            prompts.battle_messages(request),
            lambda text: parse_lyrics(text, language=request.language, explicit=request.explicit),
            on_progress or _noop,
        )
        # Trust the plan, not the model, for who performs what. Only the two
        # characters are performers; a host or a shared chorus has none, so
        # each character keeps the same voice throughout.
        planned = dict(prompts.battle_structure(request))
        names = (request.character_a.name, request.character_b.name)
        for section in lyrics.sections:
            if section.label in planned:
                section.performer = planned[section.label]
                continue
            claimed = [name for name in names if name.lower() in (section.performer or "").lower()]
            section.performer = claimed[0] if len(claimed) == 1 else None
            if section.performer and section.performer not in section.label:
                section.label = f"{section.performer}: {section.label}"[:60]
        lyrics.meta = self._meta(model)
        return lyrics

    async def suggest_characters(self, topic: str) -> list[dict]:
        characters, _ = await self._ask(prompts.characters_messages(topic), parse_characters, _noop)
        return characters
