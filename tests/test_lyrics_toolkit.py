"""Toolkit tests: parser, lyrics service, exports and the TrollMusic facade."""

from __future__ import annotations

import asyncio
import json

import pytest

from tests.conftest import SONG, ScriptedProvider
from troll_music_ai import (
    FeatureNotAvailableError,
    LLMConfig,
    LyricsParseError,
    LyricsRequest,
    ProviderNotConfiguredError,
    ProviderUnavailableError,
    RewriteMode,
    SectionType,
    TrollMusic,
    build_text_provider,
)
from troll_music_ai.lyrics import LyricsService, parse_lyrics, song_structure
from troll_music_ai.providers import MockTextProvider

REQUEST = LyricsRequest(prompt="A fake millionaire", genre="drill")


def run(coro):
    return asyncio.run(coro)


# ------------------------------- parser ----------------------------------- #


def test_parser_reads_json_wrapped_in_prose_and_fences():
    text = f"Sure! Here you go:\n```json\n{json.dumps(SONG)}\n```\nHope {{you}} like it."
    lyrics = parse_lyrics(text)
    assert lyrics.title == "Lambo On Layaway"
    assert [s.label for s in lyrics.sections][:3] == ["Intro", "Verse 1", "Chorus"]
    assert lyrics.suggested_bpm == 142


def test_parser_tolerates_sloppy_model_output():
    lyrics = parse_lyrics(
        json.dumps(
            {
                "title": "  ",
                "suggested_bpm": "999",
                "sections": [
                    {"type": "Hook", "lines": "one\n\n two "},
                    {"type": "verse 2", "label": "", "lines": ["a", 7, "b"]},
                    {"type": "verse", "lines": []},
                    "garbage",
                ],
            }
        )
    )
    assert lyrics.title == "Untitled"
    assert lyrics.suggested_bpm is None  # out of range, dropped rather than trusted
    assert [(s.type, s.label, s.lines) for s in lyrics.sections] == [
        (SectionType.CHORUS, "Chorus", ["one", "two"]),
        (SectionType.VERSE, "Verse 1", ["a", "b"]),
    ]


@pytest.mark.parametrize("text", ["no json here", '{"title": "x"}', '{"sections": [{"lines": []}]}'])
def test_parser_rejects_unusable_output(text):
    with pytest.raises(LyricsParseError):
        parse_lyrics(text)


# ------------------------------- service ---------------------------------- #


def test_structure_follows_the_request():
    request = LyricsRequest(prompt="topic", verses=3, include_bridge=True)
    assert song_structure(request) == [
        "Intro", "Verse 1", "Chorus", "Verse 2", "Chorus", "Verse 3", "Chorus",
        "Bridge", "Chorus", "Outro",
    ]


def test_generate_sends_the_request_options_to_the_model():
    provider = ScriptedProvider(SONG)
    request = LyricsRequest(
        prompt="A fake millionaire", genre="drill", troll_intensity=5, explicit=False, persona="DJ Budget"
    )
    lyrics = run(LyricsService(provider).generate(request))

    prompt = provider.requests[0].messages[-1].content
    assert "TOPIC: A fake millionaire" in prompt
    assert "GENRE: drill" in prompt
    assert "5/5" in prompt
    assert "clean, no profanity" in prompt
    assert "DJ Budget" in prompt
    assert lyrics.meta.provider == "scripted" and lyrics.meta.is_mock is False


def test_generate_retries_once_when_the_model_returns_junk():
    provider = ScriptedProvider("I cannot do JSON today", SONG)
    lyrics = run(LyricsService(provider, max_attempts=2).generate(REQUEST))
    assert lyrics.title == "Lambo On Layaway"
    assert len(provider.requests) == 2


def test_generate_gives_up_with_a_parse_error():
    provider = ScriptedProvider("junk", "more junk")
    with pytest.raises(LyricsParseError, match="Tried 2 time"):
        run(LyricsService(provider, max_attempts=2).generate(REQUEST))


def test_provider_failures_are_not_swallowed():
    provider = ScriptedProvider(ProviderUnavailableError("down"))
    with pytest.raises(ProviderUnavailableError):
        run(LyricsService(provider).generate(REQUEST))


def test_regenerate_section_changes_only_that_section():
    provider = ScriptedProvider(SONG, {"lines": ["New bar one", "New bar two"]})
    service = LyricsService(provider)
    original = run(service.generate(REQUEST))
    verse = original.sections[1]

    updated = run(service.regenerate_section(original, verse.id, instruction="mention a yacht"))

    assert updated.section(verse.id).lines == ["New bar one", "New bar two"]
    for before, after in zip(original.sections, updated.sections):
        if before.id != verse.id:
            assert before == after
    assert original.sections[1].lines == ["Rented the whip", "Returned it by six"]  # input untouched
    assert "INSTRUCTION: mention a yacht" in provider.requests[1].messages[-1].content


def test_regenerating_a_chorus_updates_every_repeat():
    provider = ScriptedProvider(SONG, {"lines": ["Brand new hook"]})
    service = LyricsService(provider)
    original = run(service.generate(REQUEST))
    chorus = original.sections[2]

    updated = run(service.regenerate_section(original, chorus.id))

    choruses = [s for s in updated.sections if s.type is SectionType.CHORUS]
    assert [c.lines for c in choruses] == [["Brand new hook"], ["Brand new hook"]]
    assert updated.sections[1] == original.sections[1]


def test_regenerate_unknown_section_is_an_error():
    provider = ScriptedProvider(SONG)
    service = LyricsService(provider)
    lyrics = run(service.generate(REQUEST))
    with pytest.raises(ValueError):
        run(service.regenerate_section(lyrics, "nope"))


def test_rewrite_keeps_title_and_section_ids():
    rewritten_song = json.loads(json.dumps(SONG))
    rewritten_song["title"] = "Totally Different Title"
    rewritten_song["sections"][1]["lines"] = ["Funnier bar"]
    provider = ScriptedProvider(SONG, rewritten_song)
    service = LyricsService(provider)
    original = run(service.generate(REQUEST))

    rewritten = run(service.rewrite(original, RewriteMode.RHYME_SCHEME, rhyme_scheme="ABAB"))

    assert rewritten.title == "Lambo On Layaway"
    assert [s.id for s in rewritten.sections] == [s.id for s in original.sections]
    assert rewritten.sections[1].lines == ["Funnier bar"]
    assert "RHYME SCHEME: ABAB" in provider.requests[1].messages[-1].content


# ------------------------------- exports ---------------------------------- #


def test_text_and_markdown_exports():
    lyrics = run(LyricsService(ScriptedProvider(SONG)).generate(REQUEST))
    text = lyrics.to_text()
    assert text.startswith("Lambo On Layaway\n\n[Intro]\nYeah\nCheck the receipt\n\n[Verse 1]")
    markdown = lyrics.to_markdown()
    assert markdown.startswith("# Lambo On Layaway")
    assert "## Verse 1\n\nRented the whip  \nReturned it by six\n" in markdown
    assert "**BPM:** 142" in markdown and "- sliding 808s" in markdown


# ------------------------- config and facade ------------------------------ #


def test_no_provider_selected_means_none():
    assert build_text_provider(LLMConfig(provider="none")) is None


@pytest.mark.parametrize(
    "config",
    [
        LLMConfig(provider="suno-but-free"),
        LLMConfig(provider="openai", model="some-model"),  # no API key
        LLMConfig(provider="openai_compatible", model="m"),  # no base URL
        LLMConfig(provider="openai_compatible", base_url="http://x/v1"),  # no model
    ],
)
def test_incomplete_provider_config_is_rejected(config):
    with pytest.raises(ProviderNotConfiguredError):
        build_text_provider(config)


def test_ollama_preset_needs_no_extra_settings():
    provider = build_text_provider(LLMConfig(provider="ollama"))
    assert provider.info.endpoint == "http://localhost:11434/v1"
    assert provider.info.is_mock is False


def test_sync_facade_generates_lyrics_and_labels_mock_output():
    studio = TrollMusic(text_provider=MockTextProvider())
    lyrics = studio.generate_lyrics(prompt="A fake millionaire", genre="drill", verses=1)
    assert lyrics.meta.is_mock is True
    assert all("[MOCK]" in line for s in lyrics.sections for line in s.lines)
    assert [s.label for s in lyrics.sections] == ["Intro", "Verse 1", "Chorus", "Outro"]


def test_facade_without_provider_fails_clearly():
    studio = TrollMusic(llm=LLMConfig(provider="none"))
    with pytest.raises(ProviderNotConfiguredError, match="TROLL_LLM_PROVIDER"):
        studio.generate_lyrics(prompt="anything at all")


def test_unimplemented_modules_say_so_instead_of_faking_output():
    studio = TrollMusic(text_provider=MockTextProvider())
    for call in (studio.generate_vocals, studio.generate_song, studio.generate_music_video):
        with pytest.raises(FeatureNotAvailableError):
            call()


def test_unclosed_line_arrays_from_small_models_are_repaired():
    from troll_music_ai.lyrics import extract_json, parse_lyrics

    broken = 'Here: {"title":"T","sections":[{"type":"verse","label":"Verse 1","lines":["a {b}","c"},{"type":"chorus","label":"Chorus","lines":["d"]}]}'
    assert [s["lines"] for s in extract_json(broken)["sections"]] == [["a {b}", "c"], ["d"]]
    assert len(parse_lyrics(broken).sections) == 2

    unclosed = '{"title":"T","sections":[{"type":"verse","label":"V","lines":["say \\"hi\\"", "b"],{"type":"chorus","label":"C","lines":["c"]}]}'
    assert [s["label"] for s in extract_json(unclosed)["sections"]] == ["V", "C"]
    assert extract_json(unclosed)["sections"][0]["lines"][0] == 'say "hi"'

    # A "sections" list reopened inside the last section, outer list never closed.
    nested = '{"title":"T","sections":[{"type":"verse","label":"Round 1","lines":["a"],"sections":[{"type":"outro","label":"Outro","lines":["z"]}]}'
    assert [s.label for s in parse_lyrics(nested).sections] == ["Round 1", "Outro"]
