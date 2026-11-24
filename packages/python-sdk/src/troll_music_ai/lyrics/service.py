"""Lyrics generation, section regeneration and rewriting."""

from __future__ import annotations

from collections.abc import Callable

from ..errors import LyricsParseError
from ..providers.base import ChatMessage, TextGenerationProvider, TextRequest
from ..troll import TrollKind, TrollRequest
from ..types import BattleCharacter, BattleRequest, GenerationMeta, Lyrics, LyricSection, LyricsRequest, LyricStyle, RewriteMode, Scorecard, SectionType, _new_id
from . import prompts
from .parser import parse_characters, parse_lyrics, parse_punchlines, parse_scorecard, parse_section_lines

ProgressCallback = Callable[[float, str], None]


def _noop(_fraction: float, _stage: str) -> None:
    return None


_TROLL_STYLE = {
    TrollKind.DISS_TRACK: LyricStyle.DISS_TRACK,
    TrollKind.ROAST: LyricStyle.SAVAGE,
    TrollKind.MEME_SONG: LyricStyle.MEME_RAP,
    TrollKind.GROUP_ROAST: LyricStyle.TROLL,
    TrollKind.MEME_VIDEO: LyricStyle.DISS_TRACK,
    TrollKind.RAP_BATTLE: LyricStyle.DISS_TRACK,
    TrollKind.FUNNY_BEAT: LyricStyle.FUNNY,
}


def conform_to_structure(lyrics: Lyrics, structure: list[str]) -> Lyrics:
    """Put sections in the requested order and restore choruses a model skipped.

    Small models sometimes drop a repeated chorus or shuffle sections. If most
    requested labels are present, rebuild in order, reusing the chorus where one
    is missing; otherwise leave the lyrics as the model wrote them.
    """
    pool: dict[str, list[LyricSection]] = {}
    for section in lyrics.sections:
        pool.setdefault(section.label.strip().lower(), []).append(section)
    first_chorus = next((s for s in lyrics.sections if s.type is SectionType.CHORUS), None)
    matched = sum(1 for label in dict.fromkeys(structure) if label.lower() in pool)
    if matched < max(1, len(set(structure)) * 0.6):
        return lyrics
    used: set[str] = set()
    ordered: list[LyricSection] = []
    for label in structure:
        candidates = [s for s in pool.get(label.lower(), []) if s.id not in used]
        if candidates:
            ordered.append(candidates[0])
            used.add(candidates[0].id)
        elif label.lower() == "chorus" and first_chorus is not None:
            ordered.append(first_chorus.model_copy(update={"id": _new_id()}))
    leftovers = [s for s in lyrics.sections if s.id not in used and s.type is not SectionType.CHORUS]
    return lyrics.model_copy(update={"sections": ordered + leftovers})


def lyrics_request_for(request: TrollRequest) -> LyricsRequest:
    """The equivalent lyrics request, so the lyrics editor can regenerate a
    section or rewrite troll lyrics with the same settings."""
    return LyricsRequest(
        prompt=f"Roasting {request.who}: {request.situation}",
        genre=request.genre[:60],
        mood="playful",
        language=request.language,
        style=_TROLL_STYLE[request.kind],
        troll_intensity=request.level,
        explicit=request.explicit,
        persona=request.rapper_name,
    )


def battle_request_for(request: TrollRequest) -> BattleRequest:
    """The roaster against the friend. The friend's character is built only
    from the situation given, as the fiction rule in the prompt requires."""
    from ..troll import rapper_name

    if len(request.characters) == 2:  # two fictional rappers from the Troll Universe
        first, second = (BattleCharacter.model_validate(c) for c in request.characters)
        return BattleRequest(
            topic=request.situation, character_a=first, character_b=second, rounds=2, knockout=True,
            genre=request.genre[:60], language=request.language, troll_intensity=request.level, explicit=request.explicit,
        )
    challenger = request.rapper_name or rapper_name()
    who = request.who
    return BattleRequest(
        topic=request.situation,
        character_a=BattleCharacter(name=challenger[:60], personality="the friend who finally says what everyone is thinking", style="cocky, punchline-heavy"),
        character_b=BattleCharacter(name=who[:60], personality=f"defends themself badly. Known for: {request.situation}"[:300], style="flustered comebacks that backfire"),
        rounds=2,
        knockout=True,
        genre=request.genre[:60],
        language=request.language,
        troll_intensity=request.level,
        explicit=request.explicit,
    )


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
        conversation = list(messages)
        for attempt in range(1, self._max_attempts + 1):
            stage = "Writing" if attempt == 1 else f"Retrying (attempt {attempt})"
            progress(0.15, stage)
            result = await self._provider.generate_text(
                TextRequest(messages=conversation, json_mode=self._json_mode)
            )
            progress(0.85, "Structuring the lyrics")
            try:
                return parse(result.text), result.model
            except LyricsParseError as exc:
                last_error = exc
                # Tell the model what was wrong instead of asking the same thing again.
                conversation = [
                    *messages,
                    ChatMessage(role="assistant", content=result.text[:4000]),
                    ChatMessage(
                        role="user",
                        content=(
                            f"That reply could not be used: {exc.message} Reply again with the complete JSON "
                            "object in the requested shape, including every section with its lines. JSON only."
                        ),
                    ),
                ]
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
                new.performer = old.performer  # a battle keeps who raps what
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

    async def generate_troll(
        self, request: TrollRequest, *, on_progress: ProgressCallback | None = None
    ) -> Lyrics:
        """Lyrics for a diss track, roast, meme song or group chat roast.

        A rap battle goes through :meth:`generate_battle` with
        :func:`battle_request_for`; a funny beat has no lyrics.
        """
        if request.kind in (TrollKind.RAP_BATTLE, TrollKind.FUNNY_BEAT):
            raise ValueError(f"{request.kind.value} is not written by generate_troll.")
        lyrics, model = await self._ask(
            prompts.troll_messages(request),
            lambda text: parse_lyrics(text, language=request.language, explicit=request.explicit),
            on_progress or _noop,
        )
        lyrics = conform_to_structure(lyrics, prompts.troll_structure(request))
        if request.kind is TrollKind.GROUP_ROAST:
            # Whoever a section is about is its performer's target, not its performer:
            # keep the label so the video and editor show the name.
            for section in lyrics.sections:
                section.performer = None
        lyrics.meta = self._meta(model)
        return lyrics

    async def punchlines(
        self,
        lyrics: Lyrics,
        section_id: str,
        line_index: int,
        *,
        count: int = 5,
        request: LyricsRequest | None = None,
        instruction: str | None = None,
    ) -> tuple[list[str], str | None]:
        """PUNCHLINE MODE: ``count`` alternatives for one line. Nothing is saved;
        the caller applies the chosen one as a new version."""
        section = lyrics.section(section_id)
        if section is None:
            raise ValueError(f"No section with id '{section_id}'.")
        if not 0 <= line_index < len(section.lines):
            raise ValueError(f"Section '{section.label}' has no line {line_index + 1}.")
        current = section.lines[line_index]
        options, model = await self._ask(
            prompts.punchline_messages(lyrics, section, line_index, count, request, instruction),
            lambda text: parse_punchlines(text, current),
            _noop,
        )
        return options[:count], model

    async def score_battle(self, lyrics: Lyrics, a: str, b: str) -> Scorecard:
        """The AI judges' opinion of a battle: marks, a winner and why."""
        card, model = await self._ask(prompts.score_messages(lyrics, a, b), lambda text: parse_scorecard(text, a, b), _noop)
        card.meta = self._meta(model)
        return card

    async def create_rapper(self, idea: str | None = None):
        """A fictional rapper profile invented by the model (Troll Universe)."""
        from ..universe import parse_profile, profile_messages

        profile, _ = await self._ask(profile_messages(idea), parse_profile, _noop)
        return profile

    async def roast_awards(self, lyrics: Lyrics, count: int = 3):
        """Awards from the fixed Roast Awards list, with reasons quoting the lyrics."""
        from ..universe import awards_messages, parse_awards

        awards, model = await self._ask(awards_messages(prompts._song_json(lyrics), count), lambda t: parse_awards(t, count), _noop)
        return awards, model

    async def suggest_characters(self, topic: str) -> list[dict]:
        characters, _ = await self._ask(prompts.characters_messages(topic), parse_characters, _noop)
        return characters
