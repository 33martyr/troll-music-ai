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

from .templates import TEMPLATES


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
    NUCLEAR = "nuclear"  # maximum exaggeration; the friendship rules still apply


# Maps to the 1-5 scale the lyric prompts already understand.
INTENSITY_LEVEL = {Intensity.FRIENDLY: 2, Intensity.SAVAGE: 4, Intensity.BRUTAL: 5, Intensity.NUCLEAR: 5}

LENGTHS = ("short", "standard", "long")

# style id -> [(subgenre id, label, words for the lyricist and music models)]
SUBGENRES: dict[str, list[tuple[str, str, str]]] = {
    "drill": [("uk", "UK Drill", "UK drill"), ("ny", "NY Drill", "New York drill"), ("jersey", "Jersey Club Drill", "jersey club drill")],
    "trap": [("rage", "Rage", "rage trap with distorted synths"), ("plugg", "Plugg", "dreamy plugg"), ("phonk", "Phonk", "drift phonk, cowbells")],
    "hip-hop": [("boom-bap", "Boom Bap", "90s boom bap"), ("lofi", "Lo-fi", "lo-fi hip-hop"), ("west-coast", "West Coast", "West Coast g-funk")],
    "pop": [("bubblegum", "Bubblegum", "bubblegum pop"), ("kpop", "K-Pop style", "K-pop style idol anthem"), ("ballad", "Power Ballad", "dramatic power ballad")],
    "country": [("outlaw", "Outlaw", "outlaw country"), ("bro", "Bro-Country", "bro-country tailgate anthem"), ("bluegrass", "Bluegrass", "frantic bluegrass")],
    "opera": [("tragic", "Tragic Aria", "tragic aria"), ("comic", "Comic Opera", "comic opera patter song"), ("rock-opera", "Rock Opera", "rock opera")],
    "techno": [("hard", "Hard Techno", "hard techno"), ("eurodance", "Eurodance", "90s eurodance"), ("hyperpop", "Hyperpop", "chaotic hyperpop")],
    "circus": [], "8-bit": [],
}

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


# vocal style id -> (label, words for a music model that sings). These are prompt
# directions, not voice presets: the model follows them loosely, and none of them
# imitates a real singer.
VOCAL_STYLES: dict[str, tuple[str, str]] = {
    "auto": ("Match the genre", ""),
    "aggressive": ("Aggressive rap", "aggressive, shouted rap vocals, hard-hitting flow"),
    "deep": ("Deep rap", "deep, low male rap vocals, slow menacing flow"),
    "playful": ("Playful rap", "playful, bouncy rap vocals, cheeky and animated"),
    "comedic": ("Comedic", "comedic, over-the-top theatrical vocals, exaggerated character voice"),
    "melodic": ("Melodic rap", "melodic, auto-tuned rap-singing vocals"),
    "pop": ("Pop singer", "bright, catchy female pop vocals, sing-along hook"),
    "electronic": ("Electronic", "energetic, processed electronic dance vocals, vocal chops"),
}

# style id -> (music model genre directions, default vocal style). More explicit
# about instruments than the lyricist's words, so each genre sounds like itself.
SONG_SOUNDS: dict[str, tuple[str, str]] = {
    "drill": ("UK drill, sliding 808 bass, skippy hi-hats, dark piano, 142 BPM", "aggressive"),
    "trap": ("trap, booming 808s, rolling hi-hats, ad-libs, 140 BPM", "playful"),
    "hip-hop": ("boom bap hip-hop, dusty drum break, vinyl scratches, jazzy sample, 92 BPM", "comedic"),
    "pop": ("upbeat pop, bright synths, handclaps, big sing-along chorus, 118 BPM", "pop"),
    "country": ("country, twangy acoustic and slide guitar, stomping drums, 100 BPM", "comedic"),
    "opera": ("operatic, orchestral strings and timpani, dramatic choir, theatrical", "comedic"),
    "techno": ("techno, pounding four-on-the-floor kick, rave synths, 130 BPM", "electronic"),
    "circus": ("circus march, tuba, calliope organ, snare rolls", "comedic"),
    "8-bit": ("chiptune, 8-bit square-wave melody, retro video game", "electronic"),
}
_HEAT = {"friendly": "light-hearted, cheeky", "savage": "cocky, mocking", "brutal": "hard, ruthless, mocking", "nuclear": "explosive, maximum hype, mocking"}


class Participant(BaseModel):
    """Someone in a group chat roast. Only what the user typed is used."""

    name: str = Field(min_length=1, max_length=40)
    nickname: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=200)
    voice: str | None = Field(default=None, max_length=120, description="Stock voice for their verse, where supported.")


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
    subgenre: str | None = Field(default=None, max_length=30, description="One of SUBGENRES[style].")
    length: str = Field(default="standard", description="short, standard or long.")
    instructions: str | None = Field(default=None, max_length=300, description="Extra instructions for the lyricist.")
    template: str | None = Field(default=None, max_length=40, description="A roast template id (see templates.py).")
    inside_jokes: list[str] = Field(default_factory=list, max_length=5, description="Inside jokes to work in.")
    people: list[Participant] = Field(default_factory=list, max_length=8, description="Group chat roast participants.")
    voice: str | None = Field(default=None, max_length=120, description="Stock voice for the main performer.")
    voice_b: str | None = Field(default=None, max_length=120, description="Rap battle: the friend's voice.")
    characters: list[dict] = Field(
        default_factory=list, max_length=2,
        description="Rap battle between two Troll Universe rappers: [{name, personality, style}, {...}].",
    )
    group_name: str | None = Field(default=None, max_length=60)
    vocal_style: str = Field(default="auto", description="One of VOCAL_STYLES. Only used by music models that sing.")

    @field_validator("vocal_style")
    @classmethod
    def _vocal_style(cls, value: str | None) -> str:
        value = (value or "auto").strip()
        if value not in VOCAL_STYLES:
            raise ValueError(f"Unknown vocal style '{value}'. Choose one of: {', '.join(VOCAL_STYLES)}.")
        return value

    @field_validator("inside_jokes")
    @classmethod
    def _jokes(cls, value: list[str]) -> list[str]:
        return [" ".join(joke.split())[:200] for joke in value if joke.strip()]

    @field_validator("template")
    @classmethod
    def _template(cls, value: str | None) -> str | None:
        from .templates import BY_ID

        value = (value or "").strip() or None
        if value and value not in BY_ID:
            raise ValueError(f"Unknown template '{value}'.")
        return value

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

    @field_validator("length")
    @classmethod
    def _length(cls, value: str) -> str:
        if value not in LENGTHS:
            raise ValueError(f"Length must be one of: {', '.join(LENGTHS)}.")
        return value

    @field_validator("instructions")
    @classmethod
    def _instructions(cls, value: str | None) -> str | None:
        value = " ".join((value or "").split())
        return value or None

    def model_post_init(self, _context) -> None:
        if self.people and not self.names:
            self.names = list(dict.fromkeys(p.name.strip() for p in self.people if p.name.strip()))
        if self.subgenre and self.subgenre not in {sid for sid, _, _ in SUBGENRES.get(self.style, [])}:
            self.subgenre = None  # a subgenre from another style is dropped, not an error

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
        sub = next((words for sid, _, words in SUBGENRES.get(self.style, []) if sid == self.subgenre), None)
        return f"{sub}, {STYLES[self.style][1]}" if sub else STYLES[self.style][1]

    @property
    def song_style(self) -> str:
        """Comma-separated directions for a music model that sings the whole song."""
        sound, default_vocal = SONG_SOUNDS[self.style]
        sub = next((words for sid, _, words in SUBGENRES.get(self.style, []) if sid == self.subgenre), None)
        vocal = VOCAL_STYLES[self.vocal_style if self.vocal_style != "auto" else default_vocal][1]
        parts = [sub, sound, vocal, _HEAT[self.intensity.value], "funny comedy song", f"clear, intelligible {self.language} vocals", "polished studio mix"]
        if self.kind is TrollKind.RAP_BATTLE:
            parts.insert(2, "two rappers trading verses, two contrasting voices")
        return ", ".join(p for p in parts if p)

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
        "subgenres": {style: [{"id": sid, "label": label} for sid, label, _ in subs] for style, subs in SUBGENRES.items()},
        "lengths": list(LENGTHS),
        "deliveries": [{"id": k, "label": v[0]} for k, v in DELIVERIES.items()],
        "vocal_styles": [{"id": k, "label": v[0]} for k, v in VOCAL_STYLES.items()],
        "templates": [t.model_dump() for t in TEMPLATES],
    }
