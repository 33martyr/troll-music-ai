"""Prompt construction for the lyrics module.

Prompts carry ``KEY: value`` header lines (TASK, TOPIC, ...) so they stay easy
to read in logs and so test doubles can tell requests apart.
"""

from __future__ import annotations

import json

from ..providers.base import ChatMessage
from ..types import (
    BattleRequest,
    ChorusStyle,
    Lyrics,
    LyricSection,
    LyricsRequest,
    LyricStyle,
    RewriteMode,
    RhymeComplexity,
    SongLength,
)

SYSTEM_PROMPT = """\
You are the head songwriter of TROLL-MUSIC-AI: a sharp, funny lyricist who \
writes original comedic songs, including roasts, diss tracks, meme rap, parody and satire.

Craft:
- Punchlines land at the end of bars. Prefer specific, concrete images over generic insults.
- Keep a consistent flow and syllable count within a section so the lyrics can be performed.
- The chorus is short, repeatable and built around one hook.

Boundaries:
- Write original lyrics. Never reproduce lines from existing songs.
- The comedy targets behaviour, situations and fictional or consenting characters.
- No threats, no encouragement of violence or self-harm, no slurs, no attacks on \
protected characteristics, no sexual content about real people, no private information.
- If the request names a real private person, roast the behaviour described and keep it playful.

Output:
- Reply with exactly one JSON object and nothing else. No markdown fences, no commentary."""

# "sections" comes right after the title: small models sometimes stop after the
# short metadata fields, so the lyrics must be written first.
SONG_SCHEMA = """\
{
  "title": "string",
  "sections": [
    {"type": "intro|verse|chorus|bridge|outro", "label": "Verse 1", "lines": ["one lyric line", "..."]}
  ],
  "suggested_bpm": 140,
  "suggested_genre": "string",
  "beat_notes": ["short production note", "..."]
}"""

_STYLE_NOTES: dict[LyricStyle, str] = {
    LyricStyle.TROLL: "mischievous trolling, baiting and winking at the listener",
    LyricStyle.SAVAGE: "ruthless, confident roast with no filler bars",
    LyricStyle.SARCASTIC: "dry sarcasm and mock praise",
    LyricStyle.FUNNY: "light, crowd-pleasing humour",
    LyricStyle.ABSURD: "surreal non-sequiturs delivered completely seriously",
    LyricStyle.DARK_COMEDY: "gallows humour that stays witty rather than cruel",
    LyricStyle.SATIRICAL: "satire that exaggerates the subject to expose it",
    LyricStyle.DISS_TRACK: "classic diss track structure aimed at a fictional or consenting rival",
    LyricStyle.MEME_RAP: "internet-native meme references and quotable one-liners",
    LyricStyle.STORYTELLING: "a narrative with a setup, escalation and a punchline ending",
    LyricStyle.PARODY: "parody of a genre's cliches, with entirely original words and melody",
}

_INTENSITY_NOTES = {
    1: "gentle teasing, friendly enough for the target to laugh along",
    2: "cheeky and pointed, still warm",
    3: "proper roast: sharp jokes, clearly comedic",
    4: "heavy roast: relentless, cocky, no mercy on the behaviour being mocked",
    5: "maximum troll: outrageous, over-the-top exaggeration, still within the boundaries",
}

_LINES_PER_VERSE = {SongLength.SHORT: 8, SongLength.MEDIUM: 12, SongLength.LONG: 16}

_RHYME_NOTES = {
    RhymeComplexity.SIMPLE: "simple end rhymes",
    RhymeComplexity.MODERATE: "end rhymes with occasional internal rhyme",
    RhymeComplexity.COMPLEX: "multisyllabic and internal rhymes, layered schemes",
}

_CHORUS_NOTES = {
    ChorusStyle.CATCHY: "catchy and instantly singable",
    ChorusStyle.CHANT: "a crowd chant with heavy repetition",
    ChorusStyle.MELODIC: "melodic and sung rather than rapped",
    ChorusStyle.CALL_AND_RESPONSE: "call and response, with the response in parentheses",
    ChorusStyle.MINIMAL: "minimal: two to four lines",
}

_REWRITE_NOTES = {
    RewriteMode.FUNNIER: "Make every section funnier: stronger punchlines, sharper specifics, better setups.",
    RewriteMode.MORE_SAVAGE: "Make it more savage: harder roast lines and more confidence, within the boundaries.",
    RewriteMode.RHYME_SCHEME: "Rewrite the lines to follow the requested rhyme scheme.",
    RewriteMode.CUSTOM: "Apply the instruction below.",
}


def song_structure(request: LyricsRequest) -> list[str]:
    """Section labels in performance order."""
    labels = ["Intro"]
    for index in range(1, request.verses + 1):
        labels += [f"Verse {index}", "Chorus"]
    if request.include_bridge:
        labels += ["Bridge", "Chorus"]
    labels.append("Outro")
    return labels


def _style_block(request: LyricsRequest) -> str:
    lines = [
        f"GENRE: {request.genre}",
        f"MOOD: {request.mood}",
        f"LANGUAGE: {request.language}",
        f"STYLE: {request.style.value} ({_STYLE_NOTES[request.style]})",
        f"TROLL INTENSITY: {request.troll_intensity}/5 ({_INTENSITY_NOTES[request.troll_intensity]})",
        "LANGUAGE RATING: "
        + ("explicit language allowed" if request.explicit else "clean, no profanity"),
        f"RHYMES: {_RHYME_NOTES[request.rhyme_complexity]}",
        f"CHORUS: {_CHORUS_NOTES[request.chorus_style]}",
    ]
    if request.persona:
        lines.append(f"PERSONA: written in the voice of the fictional character '{request.persona}'")
    return "\n".join(lines)


def _song_json(lyrics: Lyrics) -> str:
    return json.dumps(
        {
            "title": lyrics.title,
            "suggested_bpm": lyrics.suggested_bpm,
            "suggested_genre": lyrics.suggested_genre,
            "beat_notes": lyrics.beat_notes,
            "sections": [
                {"type": s.type.value, "label": s.label, "lines": s.lines}
                | ({"performer": s.performer} if s.performer else {})
                for s in lyrics.sections
            ],
        },
        ensure_ascii=False,
        indent=1,
    )


def _messages(user: str) -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=user),
    ]


def generation_messages(request: LyricsRequest) -> list[ChatMessage]:
    lines_per_verse = _LINES_PER_VERSE[request.length]
    user = f"""\
TASK: generate_lyrics
TOPIC: {request.prompt}
{_style_block(request)}
STRUCTURE: {", ".join(song_structure(request))}

Write the full song in {request.language}. Each verse has about {lines_per_verse} lines; \
the intro and outro are 2 to 4 lines. Output one section per entry in STRUCTURE, in that \
order, using those exact labels. Every Chorus entry repeats the same lines.
Also suggest a BPM, a genre and 3 to 5 short beat characteristics for a producer.

Return JSON in this shape:
{SONG_SCHEMA}"""
    return _messages(user)


def section_messages(
    lyrics: Lyrics,
    section: LyricSection,
    request: LyricsRequest | None,
    instruction: str | None,
) -> list[ChatMessage]:
    style = f"{_style_block(request)}\nTOPIC: {request.prompt}\n" if request else ""
    extra = f"INSTRUCTION: {instruction.strip()}\n" if instruction and instruction.strip() else ""
    performer = f", delivered by the character {section.performer} in their own voice" if section.performer else ""
    user = f"""\
TASK: regenerate_section
SECTION: {section.label}
{style}{extra}
Here is the current song:
<song>
{_song_json(lyrics)}
</song>

Write a fresh take on the section labelled "{section.label}" only{performer}. Keep it about the same \
length ({len(section.lines)} lines), consistent with the rest of the song, and do not reuse \
its current lines. Leave every other section alone.

Return JSON in this shape:
{{"lines": ["one lyric line", "..."]}}"""
    return _messages(user)


def rewrite_messages(
    lyrics: Lyrics,
    mode: RewriteMode,
    request: LyricsRequest | None,
    instruction: str | None,
    rhyme_scheme: str | None,
) -> list[ChatMessage]:
    details = [_REWRITE_NOTES[mode]]
    if mode is RewriteMode.RHYME_SCHEME and rhyme_scheme:
        details.append(f"RHYME SCHEME: {rhyme_scheme} within each four-line group.")
    if instruction and instruction.strip():
        details.append(f"INSTRUCTION: {instruction.strip()}")
    style = f"{_style_block(request)}\nTOPIC: {request.prompt}\n" if request else ""
    user = f"""\
TASK: rewrite_lyrics
MODE: {mode.value}
{style}{chr(10).join(details)}

Here is the current song:
<song>
{_song_json(lyrics)}
</song>

Rewrite the song. Keep the same sections in the same order with the same types and labels, \
and keep the same topic and language. Every Chorus entry repeats the same lines.

Return the full song as JSON in this shape:
{SONG_SCHEMA}"""
    return _messages(user)


BATTLE_SCHEMA = SONG_SCHEMA.replace('"label": "Verse 1",', '"label": "Verse 1", "performer": "character name",')
_FICTION_RULE = (
    "Both rappers are fictional characters. If a name resembles a real person, treat it as a "
    "fictional namesake: use only the personality given here, no real biography, no real events."
)


def battle_structure(request: BattleRequest) -> list[tuple[str, str | None]]:
    """``(label, performer)`` pairs in performance order."""
    a, b = request.character_a.name, request.character_b.name
    plan: list[tuple[str, str | None]] = [("Intro", None)]
    for number in range(1, request.rounds + 1):
        name = "Knockout" if request.knockout and number == request.rounds and request.rounds > 1 else f"Round {number}"
        plan += [(f"{a}: {name}", a), (f"{b}: {name}", b)]
        if number == 1 or number == request.rounds:
            plan.append(("Chorus", None))
    plan.append(("Outro", None))
    return plan


def battle_messages(request: BattleRequest) -> list[ChatMessage]:
    a, b = request.character_a, request.character_b
    plan = battle_structure(request)
    rating = "explicit language allowed" if request.explicit else "clean, no profanity"
    user = f"""\
TASK: generate_battle
TOPIC: {request.topic}
GENRE: {request.genre}
LANGUAGE: {request.language}
TROLL INTENSITY: {request.troll_intensity}/5 ({_INTENSITY_NOTES[request.troll_intensity]})
LANGUAGE RATING: {rating}
CHARACTER A: {a.name} | personality: {a.personality or "up to you"} | rap style: {a.style or "up to you"}
CHARACTER B: {b.name} | personality: {b.personality or "up to you"} | rap style: {b.style or "up to you"}
STRUCTURE: {", ".join(label for label, _ in plan)}

Write a humorous rap battle between the two characters. {_FICTION_RULE}
Each round verse is 8 lines in that character's distinct voice, and each rapper answers the \
other's previous verse directly. The Chorus is a call-and-response between both of them and \
repeats identically. The Intro and Outro belong to a battle host: the Intro is a dramatic, \
over-the-top boxing-style introduction of both rappers. {"Knockout verses are each rapper's final and \
hardest verse, ending on the biggest punchline of the battle. " if request.knockout else ""}Output one section per entry \
in STRUCTURE, in that order, using those exact labels. Round verses have type "verse" and a \
"performer" equal to the character's name. Also suggest a BPM, a genre and beat notes.

Return JSON in this shape:
{BATTLE_SCHEMA}"""
    return _messages(user)


# ------------------------------ troll songs ------------------------------- #

_FRIEND_RULE = """\
This is a roast between friends, made to be sent to the group chat. The friend should laugh too.
- Roast what they DO (the situation), never who they ARE: no jokes about looks, weight, health, \
race, religion, gender, sexuality, disability or family tragedy, at any intensity.
- No real surnames, addresses, workplaces or other private details, even if given.
- Exaggerate wildly. Specific, absurd images beat generic insults."""

_LEVEL_NOTES = {
    "friendly": "FRIENDLY: affectionate teasing, the kind you'd say at their birthday",
    "savage": "SAVAGE: sharp, relentless punchlines, still clearly playful",
    "brutal": "BRUTAL: maximum comedic destruction of the behaviour, over-the-top, still within the rules above",
    "nuclear": (
        "NUCLEAR: apocalyptic, cinematic hyperbole about the behaviour (end-of-the-world stakes for a tiny "
        "crime), the most outrageous version you can write. Nuclear means bigger exaggeration, never crossing "
        "the rules above"
    ),
}

_VERSE_LINES = {"short": 6, "standard": 8, "long": 10}


def troll_structure(request) -> list[str]:
    """Section labels in performance order for a troll song."""
    from ..troll import TrollKind

    kind = request.kind
    if kind is TrollKind.ROAST:
        return ["Intro", "Roast", "Outro"]
    if kind is TrollKind.MEME_SONG:
        return ["Chorus", "Verse 1", "Chorus", "Chorus"]
    if kind is TrollKind.GROUP_ROAST and request.names:
        return ["Intro", *request.names, "Chorus", "Outro"]
    length = getattr(request, "length", "standard")
    if kind is TrollKind.MEME_VIDEO or length == "short":
        return ["Intro", "Verse 1", "Chorus", "Outro"]
    if length == "long":
        return ["Intro", "Verse 1", "Chorus", "Verse 2", "Chorus", "Verse 3", "Chorus", "Outro"]
    return ["Intro", "Verse 1", "Chorus", "Verse 2", "Chorus", "Outro"]


def _troll_shape(request) -> str:
    from ..troll import TrollKind

    kind = request.kind
    if kind is TrollKind.ROAST:
        return (
            "A stand-up style roast set over a beat. Intro: 2 lines, a dramatic announcer bringing the target "
            "to the stage. Roast: 10 to 12 one-liners, every line its own punchline. Outro: 2 lines, mic drop."
        )
    if kind is TrollKind.MEME_SONG:
        return (
            "A ridiculously catchy meme song. The Chorus is 4 short, DIFFERENT lines built around one chantable hook "
            "that names the target (the hook line may appear at most twice); it must be stupidly easy to sing along "
            "to, and every Chorus entry repeats the same 4 lines. Verse 1 is 6 lines telling the story."
        )
    if kind is TrollKind.GROUP_ROAST:
        return (
            "A group chat roast: each person gets their own section (labelled with their name) of 4 to 6 lines "
            "roasting them, the Chorus (4 lines) roasts the group chat as a whole, Intro and Outro 2 lines each."
        )
    if kind is TrollKind.MEME_VIDEO:
        return "A short diss track for a meme video: Intro 2 lines, Verse 1 8 lines, Chorus 4 lines, Outro 2 lines."
    return (
        f"A diss track. Intro: 2 to 4 lines of trash talk. Each verse: {_VERSE_LINES[getattr(request, 'length', 'standard')]} lines, building to the hardest punchline "
        "on the last bar. Chorus: 4 lines with one savage hook, identical every time. Outro: 2 to 4 lines."
    )


def troll_messages(request) -> list[ChatMessage]:
    from ..templates import get as get_template
    from ..troll import DELIVERIES

    target = request.who
    names = f"PEOPLE IN THE CHAT: {', '.join(request.names)}\n" if request.names else ""
    for person in getattr(request, "people", None) or []:
        detail = f" ({person.nickname})" if person.nickname else ""
        names += f"- {person.name}{detail}" + (f": {person.description}\n" if person.description else " (roast their part in the SITUATION)\n")
    template = get_template(request.template)
    if template:
        names += f"ARCHETYPE: {template.name}. {template.guidance}\n"
    if request.inside_jokes:
        names += "INSIDE JOKES (work each one in as a callback): " + " | ".join(request.inside_jokes) + "\n"
    if getattr(request, "instructions", None):
        names += f"EXTRA INSTRUCTIONS (follow them unless they break the rules below): {request.instructions}\n"
    if getattr(request, "group_name", None):
        names += f"GROUP CHAT NAME: {request.group_name}\n"
    performer = request.rapper_name or "the roaster"
    rating = "explicit language allowed (no slurs)" if request.explicit else "clean, no profanity"
    user = f"""\
TASK: generate_troll
KIND: {request.kind.value}
TARGET: {target}
{names}SITUATION: {request.situation}
STYLE: {request.genre}
INTENSITY: {_LEVEL_NOTES[request.intensity.value]}
DELIVERY: performed by {performer}, as {DELIVERIES[request.delivery][1]}
LANGUAGE: {request.language}
LANGUAGE RATING: {rating}
STRUCTURE: {", ".join(troll_structure(request))}

{_FRIEND_RULE}

{_troll_shape(request)}
Lines are short (4 to 10 words) so they can be performed fast. Name {target} often. Every joke \
comes from the SITUATION. Give it a funny title (a fake hit-single name). Output one section per \
entry in STRUCTURE, in that order, using those exact labels.
Also suggest a BPM, a genre and 3 short beat notes.

Return JSON in this shape:
{SONG_SCHEMA}"""
    return _messages(user)


def punchline_messages(
    lyrics: Lyrics, section: LyricSection, line_index: int, count: int, request: LyricsRequest | None, instruction: str | None
) -> list[ChatMessage]:
    line = section.lines[line_index]
    before = section.lines[line_index - 1] if line_index > 0 else None
    after = section.lines[line_index + 1] if line_index + 1 < len(section.lines) else None
    style = f"{_style_block(request)}\nTOPIC: {request.prompt}\n" if request else ""
    extra = f"INSTRUCTION: {instruction.strip()}\n" if instruction and instruction.strip() else ""
    context = "\n".join(
        part for part in (f"LINE BEFORE: {before}" if before else "", f"LINE TO REPLACE: {line}", f"LINE AFTER: {after}" if after else "") if part
    )
    user = f"""\
TASK: punchlines
SECTION: {section.label}
COUNT: {count}
{style}{extra}{context}

Song so far:
<song>
{_song_json(lyrics)}
</song>

Write {count} alternative versions of LINE TO REPLACE. Each one must fit the same spot: about the same length and syllable count, keep the rhyme with the neighbouring lines, and land a harder, funnier punchline. Make the {count} options genuinely different from each other (different angle, image or wordplay), and different from the current line.

Return JSON in this shape:
{{"punchlines": ["option one", "option two"]}}"""
    return _messages(user)


def score_messages(lyrics: Lyrics, a: str, b: str) -> list[ChatMessage]:
    user = f"""\
TASK: score_battle
RAPPER A: {a}
RAPPER B: {b}

Here is the battle:
<song>
{_song_json(lyrics)}
</song>

You are a panel of three comedy rap-battle judges. Judge only the verses each rapper performed (sections \
with their "performer"). Give each rapper a mark from 1 to 10 for punchlines, flow, creativity, humor and \
entertainment, and a one-sentence comment quoting or pointing at their actual lines. Then name the winner \
(or "draw"), write a short, funny winner announcement (2 to 3 sentences) that explains the decision using \
specific lines, and pick the single best line of the battle. This is your opinion: be fair, be specific, \
and be entertaining.

Return JSON in this shape:
{{"scores": {{"{a}": {{"punchlines": 7, "flow": 6, "creativity": 8, "humor": 9, "entertainment": 8, "comment": "..."}}, \
"{b}": {{"punchlines": 6, "flow": 7, "creativity": 6, "humor": 7, "entertainment": 7, "comment": "..."}}}}, \
"winner": "{a}", "announcement": "...", "best_line": "..."}}"""
    return _messages(user)


def characters_messages(topic: str) -> list[ChatMessage]:
    user = f"""\
TASK: suggest_characters
TOPIC: {topic}

Invent two fictional rival rappers who would battle about this topic. They must have opposing \
personalities and clearly different rap styles, and funny original stage names. Do not use or \
imitate real people.

Return JSON in this shape:
{{"characters": [{{"name": "stage name", "personality": "one sentence", "style": "rap style in a few words"}}, {{"name": "...", "personality": "...", "style": "..."}}]}}"""
    return _messages(user)
