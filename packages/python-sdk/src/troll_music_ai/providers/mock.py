"""Mock text provider. For tests and UI development only.

It never calls a model. Every line it produces says so, and
``ProviderInfo.is_mock`` is set so interfaces can label the result.
"""

from __future__ import annotations

import json
import re

from .base import (
    ProviderInfo,
    ProviderKind,
    ProviderStatus,
    TextGenerationProvider,
    TextRequest,
    TextResult,
)

_TAG = "[MOCK]"


class MockTextProvider(TextGenerationProvider):
    def __init__(self) -> None:
        self.calls: list[TextRequest] = []

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="mock", kind=ProviderKind.TEXT, model="mock-lyrics", is_mock=True)

    async def check(self) -> ProviderStatus:
        return ProviderStatus(ok=True, detail="Mock provider: no AI model is used.")

    async def generate_text(self, request: TextRequest) -> TextResult:
        self.calls.append(request)
        prompt = request.messages[-1].content
        task = _field(prompt, "TASK") or "generate_lyrics"

        if task == "regenerate_section":
            label = _field(prompt, "SECTION") or "Section"
            payload: dict = {
                "lines": [
                    f"{_TAG} regenerated placeholder for {label}, call {len(self.calls)}",
                    f"{_TAG} no AI model wrote this line",
                ]
            }
        elif task == "punchlines":
            count = int(_field(prompt, "COUNT") or 5)
            payload = {"punchlines": [f"{_TAG} alternative punchline {i + 1}, not written by a model" for i in range(count)]}
        elif task == "score_battle":
            a, b = _field(prompt, "RAPPER A") or "A", _field(prompt, "RAPPER B") or "B"
            mark = {"punchlines": 5, "flow": 5, "creativity": 5, "humor": 5, "entertainment": 5}
            payload = {
                "scores": {a: {**mark, "humor": 6, "comment": f"{_TAG} placeholder comment"}, b: {**mark, "comment": f"{_TAG} placeholder comment"}},
                "winner": a,
                "announcement": f"{_TAG} placeholder announcement: no AI judged this battle.",
                "best_line": f"{_TAG} placeholder best line",
            }
        elif task == "create_rapper":
            payload = {
                "name": f"{_TAG} MC Stub", "personality": f"{_TAG} placeholder personality", "bio": f"{_TAG} no AI wrote this biography.",
                "catchphrase": f"{_TAG} placeholder", "style": "trap", "delivery": "cocky",
                "stats": {"punchline": 50, "flow": 50, "comedy": 50, "creativity": 50, "reputation": 50},
            }
        elif task == "roast_awards":
            count = int(_field(prompt, "COUNT") or 3)
            names = ["Best Punchline", "Funniest Chorus", "Legendary Roast", "Best Flow"][:count]
            payload = {"awards": [{"award": n, "reason": f"{_TAG} placeholder reason", "line": None} for n in names]}
        elif task == "suggest_characters":
            payload = {
                "characters": [
                    {"name": f"{_TAG} MC Placeholder", "personality": f"{_TAG} placeholder personality", "style": "mock"},
                    {"name": f"{_TAG} Lil Stub", "personality": f"{_TAG} the opposite placeholder", "style": "mock"},
                ]
            }
        elif task == "rewrite_lyrics":
            song = json.loads(_block(prompt))
            mode = _field(prompt, "MODE") or "custom"
            for section in song["sections"]:
                section["lines"] = [f"{_TAG} {mode} rewrite of {section['label']}"] * 2
            payload = song
        else:
            topic = _field(prompt, "TOPIC") or _field(prompt, "SITUATION") or "nothing in particular"
            structure = (_field(prompt, "STRUCTURE") or "Intro, Verse 1, Chorus, Outro").split(", ")
            payload = {
                "title": f"{_TAG} Placeholder Song",
                "suggested_bpm": 140,
                "suggested_genre": _field(prompt, "GENRE") or "trap",
                "beat_notes": [f"{_TAG} placeholder beat note"],
                "sections": [
                    {
                        "type": "verse" if ": " in label else re.sub(r"[\s\d]+$", "", label).lower(),
                        "label": label,
                        "lines": [
                            f"{_TAG} placeholder line for {label} about: {topic}",
                            f"{_TAG} configure a real provider to get real lyrics",
                        ],
                    }
                    for label in structure
                ],
            }
        return TextResult(text=json.dumps(payload), model="mock-lyrics")


def _field(prompt: str, name: str) -> str | None:
    match = re.search(rf"^{name}: (.+)$", prompt, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _block(prompt: str) -> str:
    start = prompt.index("<song>") + len("<song>")
    return prompt[start : prompt.index("</song>")]
