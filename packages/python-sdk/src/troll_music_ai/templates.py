"""Roast templates: ready-made friend archetypes the user customises before generating.

A template fills the troll form (situation, kind, style, intensity, delivery)
and adds prompt guidance the lyricist follows. The user can change any of it.
"""

from __future__ import annotations

from pydantic import BaseModel


class RoastTemplate(BaseModel):
    id: str
    name: str
    emoji: str
    scenario: str  # pre-filled situation, with {name} where the friend's name goes
    kind: str
    style: str
    intensity: str
    delivery: str
    guidance: str  # angle for the lyricist
    examples: list[str]  # example situations to spark ideas


TEMPLATES: tuple[RoastTemplate, ...] = (
    RoastTemplate(
        id="lazy", name="The Lazy Friend", emoji="🛋️", kind="diss_track", style="hip-hop",
        intensity="savage", delivery="deadpan",
        scenario="{name} treats the sofa like a full-time job and calls a nap 'self-care'",
        guidance="Exaggerate the laziness into heroic, legendary levels of doing nothing. Mock the excuses.",
        examples=["{name} asked me to pass the remote that was next to them", "{name} has been 'about to start the gym' since 2019"],
    ),
    RoastTemplate(
        id="late", name="The Always Late Friend", emoji="⏰", kind="meme_song", style="pop", intensity="friendly",
        delivery="news", scenario="{name} says 'five minutes away' while still in the shower",
        guidance="Build the hook around their signature excuse. Time-zone and clock jokes, fake travel updates.",
        examples=["{name} arrived at their own birthday party late", "{name}'s 'on my way' means 'just woke up'"],
    ),
    RoastTemplate(
        id="gamer", name="The Gamer", emoji="🎮", kind="diss_track", style="trap",
        intensity="savage", delivery="cocky", scenario="{name} blames lag for every single loss",
        guidance="Gaming vocabulary as roast ammunition: lag, respawn, noob, rage-quit. Never about looks.",
        examples=["{name} rage-quit a game of Uno", "{name} says they'd be pro if their chair was better"],
    ),
    RoastTemplate(
        id="gym", name="The Gym Bro", emoji="🏋️", kind="roast", style="drill", intensity="savage", delivery="hype",
        scenario="{name} can't go five minutes without mentioning their protein intake",
        guidance="Mock the routine, the supplements and the mirror selfies, never the body itself.",
        examples=["{name} brought a shaker bottle to a wedding", "{name} counts carrying groceries as leg day"],
    ),
    RoastTemplate(
        id="exaggerator", name="The Exaggerator", emoji="🎣", kind="diss_track", style="country", intensity="friendly",
        delivery="narrator", scenario="Every story {name} tells grows by 50% each time it's told",
        guidance="Escalate their stories to absurd, mythical proportions and fact-check them in the chorus.",
        examples=["{name}'s fish was 'this big' and now it's a whale", "{name} 'basically' met a celebrity once"],
    ),
    RoastTemplate(
        id="excuses", name="The Professional Excuse Maker", emoji="📝", kind="roast", style="hip-hop",
        intensity="savage", delivery="news", scenario="{name} has a new excuse for every plan they cancel",
        guidance="List increasingly ridiculous excuses as punchlines; the outro catches them in the lie.",
        examples=["{name} cancelled because their plant 'needed them'", "{name}'s grandma has 'passed away' four times"],
    ),
    RoastTemplate(
        id="ghost", name="The Group Chat Ghost", emoji="👻", kind="meme_song", style="techno", intensity="friendly",
        delivery="diva", scenario="{name} reads every message and replies three days later with a thumbs up",
        guidance="Haunting, paranormal investigation jokes about their read receipts and disappearing acts.",
        examples=["{name} left the chat on read during their own birthday plans", "{name}'s last message was in 2022"],
    ),
    RoastTemplate(
        id="broke", name="The Broke Friend", emoji="💸", kind="diss_track", style="trap", intensity="savage",
        delivery="cocky", scenario="{name} acts rich but borrows money every Friday",
        guidance="Fake-rich flexing versus the reality of their bank balance. Loans, IOUs, splitting the bill.",
        examples=["{name} 'forgot their wallet' for the 12th time", "{name} venmo-requested me for gum"],
    ),
    RoastTemplate(
        id="overthinker", name="The Overthinker", emoji="🌀", kind="roast", style="opera", intensity="friendly",
        delivery="narrator", scenario="{name} spent three hours writing a two-word text",
        guidance="Dramatise tiny decisions into epic tragedies. Spiralling inner monologue jokes.",
        examples=["{name} drafted a reply to 'ok'", "{name} needs a week to choose a sandwich"],
    ),
    RoastTemplate(
        id="main", name="The Main Character", emoji="🎬", kind="meme_video", style="pop", intensity="savage",
        delivery="diva", scenario="{name} narrates their life like a movie and everyone else is an extra",
        guidance="Movie-trailer energy: dramatic slow motion, soundtrack moments, nobody else gets lines.",
        examples=["{name} looks out of bus windows like it's a music video", "{name} made a speech at a bus stop"],
    ),
    RoastTemplate(
        id="food", name="The Food Thief", emoji="🍟", kind="diss_track", style="drill", intensity="savage",
        delivery="news", scenario="{name} 'just tries one' and finishes half your plate",
        guidance="Crime-thriller framing: evidence, fingerprints in the ketchup, the case of the missing fries.",
        examples=["{name} ate my labelled leftovers", "{name} orders a salad and eats my chips"],
    ),
    RoastTemplate(
        id="drama", name="The Drama Queen", emoji="🎭", kind="meme_song", style="opera", intensity="friendly",
        delivery="diva", scenario="{name} turns a slightly cold coffee into a three-act tragedy",
        guidance="Theatrical overreaction to tiny problems. Soap-opera twists and dramatic gasps.",
        examples=["{name} declared the end of the world when the Wi-Fi dropped", "{name} wrote a tribute to a lost sock"],
    ),
    RoastTemplate(
        id="disaster", name="The Walking Disaster", emoji="💥", kind="roast", style="country", intensity="savage",
        delivery="news", scenario="{name} can trip over a perfectly flat floor",
        guidance="A breaking-news catalogue of mishaps. Keep it about clumsiness, never injury or health.",
        examples=["{name} locked themself out of the car twice in one day", "{name} set off the smoke alarm making toast"],
    ),
    RoastTemplate(
        id="expert", name="The Fake Expert", emoji="🤓", kind="diss_track", style="hip-hop", intensity="savage",
        delivery="deadpan", scenario="{name} watched one video and now explains it to actual professionals",
        guidance="Confident wrongness. Fake credentials, 'actually...' energy, a chorus of debunked facts.",
        examples=["{name} explained cooking to a chef", "{name} is a crypto expert with a 94% loss"],
    ),
)

BY_ID = {template.id: template for template in TEMPLATES}


def get(template_id: str | None) -> RoastTemplate | None:
    return BY_ID.get(template_id or "")


def filled(template: RoastTemplate, name: str | None) -> dict:
    """The template as form values, with the friend's name filled in."""
    who = (name or "").strip() or "my friend"
    return {
        "template": template.id,
        "situation": template.scenario.format(name=who),
        "kind": template.kind,
        "style": template.style,
        "intensity": template.intensity,
        "delivery": template.delivery,
    }
