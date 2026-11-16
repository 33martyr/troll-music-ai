"""The meme layer: one request that says who we are roasting and how.

Everything here is plain Python: request types, the style and intensity
vocabulary, a funny rapper-name generator and random troll ideas. Nothing in
this module calls a model; :class:`~troll_music_ai.lyrics.LyricsService`
turns a :class:`TrollRequest` into lyrics.
"""

from __future__ import annotations

import random
import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class TrollKind(StrEnum):
    DISS_TRACK = "diss_track"
    ROAST = "roast"
    RAP_BATTLE = "rap_battle"
    MEME_SONG = "meme_song"
    GROUP_ROAST = "group_roast"
    FUNNY_BEAT = "funny_beat"
    MEME_VIDEO = "meme_video"


class Intensity(StrEnum):
    FRIENDLY = "friendly"
    SAVAGE = "savage"
    BRUTAL = "brutal"


# Maps to the 1-5 scale the lyric prompts already understand.
INTENSITY_LEVEL = {Intensity.FRIENDLY: 2, Intensity.SAVAGE: 4, Intensity.BRUTAL: 5}

KIND_LABELS: dict[TrollKind, str] = {
    TrollKind.DISS_TRACK: "Diss Track",
    TrollKind.ROAST: "Savage Roast",
    TrollKind.RAP_BATTLE: "Rap Battle",
    TrollKind.MEME_SONG: "Meme Song",
    TrollKind.GROUP_ROAST: "Group Chat Roast",
    TrollKind.FUNNY_BEAT: "Funny Beat",
    TrollKind.MEME_VIDEO: "Meme Video",
}

# style id -> (label, genre words for the lyricist, built-in beat engine preset)
STYLES: dict[str, tuple[str, str, str]] = {
    "drill": ("Drill", "UK drill, sliding 808s, menacing but ridiculous", "drill"),
    "trap": ("Trap", "trap, hi-hat rolls, ad-libs", "trap"),
    "hip-hop": ("Hip-Hop", "classic boom-bap hip-hop", "hiphop"),
    "pop": ("Pop", "bubblegum pop, sing-along hooks", "pop"),
    "country": ("Country", "country, pickup trucks and heartbreak cliches", "country"),
    "opera": ("Opera", "melodramatic opera, tragic arias about tiny problems", "opera"),
    "techno": ("Techno", "pounding techno, repetitive rave chants", "techno"),
    "circus": ("Circus", "clown-music circus march", "circus"),
    "8-bit": ("8-Bit", "retro video-game chiptune", "chiptune"),
}
SONG_STYLES = ("drill", "trap", "hip-hop", "pop", "country", "opera", "techno")

# delivery id -> (label, how the lyrics are written and performed)
DELIVERIES: dict[str, tuple[str, str]] = {
    "hype": ("Hype Man", "an overexcited hype man shouting ad-libs in brackets, e.g. (WHAT?!)"),
    "narrator": ("Dramatic Narrator", "a deadly serious nature-documentary narrator describing a tragedy"),
    "deadpan": ("Deadpan", "completely flat, unimpressed, devastating understatement"),
    "cocky": ("Overconfident", "an absurdly cocky rapper who thinks every bar is a classic"),
    "news": ("Breaking News", "a breaking-news anchor reporting live from the scene of the embarrassment"),
    "diva": ("Diva", "a melodramatic diva, gasping and offended on everyone's behalf"),
}


class TrollRequest(BaseModel):
    """What the home screen asks: who, what happened, and how hard."""

    situation: str = Field(min_length=3, max_length=600, description="The joke, situation or inside joke.")
    kind: TrollKind = TrollKind.DISS_TRACK
    style: str = Field(default="trap", description="One of STYLES.")
    intensity: Intensity = Intensity.SAVAGE
    delivery: str = Field(default="cocky", description="One of DELIVERIES.")
    target: str | None = Field(default=None, max_length=40, description="First name or nickname of the friend.")
    names: list[str] = Field(default_factory=list, max_length=6, description="Group chat roast: everyone in it.")
    rapper_name: str | None = Field(default=None, max_length=40, description="The roaster's stage name.")
    explicit: bool = False
    language: str = Field(default="English", max_length=40)

    @field_validator("situation")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 3:
            raise ValueError("Tell us what happened (at least a few words).")
        return value

    @field_validator("style")
    @classmethod
    def _style(cls, value: str) -> str:
        if value not in STYLES:
            raise ValueError(f"Unknown style '{value}'. Choose one of: {', '.join(STYLES)}.")
        return value

    @field_validator("delivery")
    @classmethod
    def _delivery(cls, value: str) -> str:
        if value not in DELIVERIES:
            raise ValueError(f"Unknown delivery '{value}'. Choose one of: {', '.join(DELIVERIES)}.")
        return value

    @field_validator("target", "rapper_name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        value = " ".join((value or "").split())
        return value or None

    @field_validator("names")
    @classmethod
    def _names(cls, value: list[str]) -> list[str]:
        cleaned = [" ".join(name.split())[:40] for name in value]
        return list(dict.fromkeys(name for name in cleaned if name))

    @property
    def level(self) -> int:
        return INTENSITY_LEVEL[self.intensity]

    @property
    def genre(self) -> str:
        return STYLES[self.style][1]

    @property
    def beat_genre(self) -> str:
        return STYLES[self.style][2]

    @property
    def who(self) -> str:
        """The person being roasted, for titles. Falls back to a name found in the text."""
        if self.target:
            return self.target
        if self.kind is TrollKind.GROUP_ROAST and self.names:
            return "The Group Chat"
        return guess_name(self.situation) or "Your Friend"


_NOT_NAMES = {
    "My", "The", "A", "An", "Our", "His", "Her", "Their", "This", "That", "When", "Every", "He", "She",
    "They", "We", "I", "It", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
}


def guess_name(text: str) -> str | None:
    """The first capitalised word that looks like a first name: 'my friend Dave thinks...' -> 'Dave'."""
    for match in re.finditer(r"\b([A-Z][a-z]{1,15})\b", text):
        if match.group(1) not in _NOT_NAMES:
            return match.group(1)
    return None


# ----------------------------- rapper names ------------------------------- #

_PREFIXES = ("Lil", "Big", "MC", "DJ", "Young", "Notorious", "Grand Wizard", "Sir", "Baby", "OG", "King", "Lord")
_CORES = (
    "Overdraft", "Borrowed Tenner", "Wi-Fi Password", "Microwave Fish", "Reply-All", "Expired Coupon",
    "Unread Messages", "Group Project", "Cold Fries", "Low Battery", "Free Trial", "Buffering",
    "Parallel Parking", "Lukewarm Tea", "Lost Charger", "Seen 3h Ago", "Dad Joke", "Gym Membership",
    "Skipped Leg Day", "Soggy Cereal", "Autocorrect", "Voice Note", "Out Of Office", "Tax Return",
)
_SUFFIXES = ("Tha Broke", "Da Menace", "Supreme", "the Unbothered", "Jr.", "Deluxe", "3000", "XL", "Tha Liability")


def rapper_name(target: str | None = None, *, seed: int | None = None) -> str:
    """A ridiculous stage name. With a target, sometimes built from their name."""
    rng = random.Random(seed)
    if target and rng.random() < 0.5:
        first = target.split()[0]
        return rng.choice([f"Lil {first}", f"{first} {rng.choice(_SUFFIXES)}", f"MC {first}", f"Notorious {first[:1]}.{first[1:2].upper()}."])
    if rng.random() < 0.6:
        return f"{rng.choice(_PREFIXES)} {rng.choice(_CORES)}"
    return f"{rng.choice(_CORES)} {rng.choice(_SUFFIXES)}"


def beat_title(request: TrollRequest, *, seed: int | None = None) -> str:
    """A funny track title for a beat that has no lyrics, made from a template."""
    rng = random.Random(seed)
    who = request.who
    style = STYLES[request.style][0]
    return rng.choice(
        [
            f"{who}'s Walk of Shame ({style} Remix)",
            f"Theme Song For {who} Being Wrong Again",
            f"{who} Enters The Group Chat ({style} Edition)",
            f"Elevator Music For {who}'s Excuses",
            f"{who}.exe Has Stopped Working",
            f"Certified {who} Moment ({style} Version)",
        ]
    )


# ---------------------------- random trolls ------------------------------- #

SCENARIOS: tuple[str, ...] = (
    "My friend Dave thinks he's rich but borrows money every Friday",
    "Sam replies 'on my way' while still in the shower",
    "Priya has 47 unread voice notes and calls them 'a vibe'",
    "Marcus brought a guitar to the party. Nobody asked.",
    "Jess says she's 'basically a chef' because she owns an air fryer",
    "Tom bought a fitness tracker and now only tracks his naps",
    "Leo said he'd split the bill and then went to the bathroom for 20 minutes",
    "Ana starts every story with 'so basically' and it is never basic",
    "Our group chat planned a trip in 2021 and we are still 'finalising dates'",
    "Chris calls himself an entrepreneur because he resold two pairs of sneakers",
    "Mia leaves exactly one bite of food in the fridge so it doesn't count as finishing it",
    "Ben's crypto portfolio is down 94% but he says it's 'long term'",
    "Zoe has 12 alarms and snoozes all of them",
    "Raj parallel parks like he is defusing a bomb",
    "Kim reads the group chat, says nothing, then reacts with a thumbs up three days later",
)


def random_troll(*, seed: int | None = None) -> dict:
    """A complete, random request for the 'Random Troll' button."""
    rng = random.Random(seed)
    situation = rng.choice(SCENARIOS)
    kind = rng.choice([TrollKind.DISS_TRACK, TrollKind.ROAST, TrollKind.MEME_SONG, TrollKind.RAP_BATTLE])
    target = guess_name(situation)
    return {
        "situation": situation,
        "kind": kind.value,
        "style": rng.choice(SONG_STYLES),
        "intensity": rng.choice(list(Intensity)).value,
        "delivery": rng.choice(list(DELIVERIES)),
        "target": target,
        "rapper_name": rapper_name(seed=rng.randrange(2**31)),
    }


def options() -> dict:
    """Everything a UI needs to draw the troll form."""
    return {
        "kinds": [{"id": k.value, "label": v} for k, v in KIND_LABELS.items()],
        "styles": [{"id": k, "label": v[0], "song": k in SONG_STYLES} for k, v in STYLES.items()],
        "intensities": [{"id": i.value, "label": i.value.title()} for i in Intensity],
        "deliveries": [{"id": k, "label": v[0]} for k, v in DELIVERIES.items()],
    }
