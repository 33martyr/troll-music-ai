"""Subprocess entry point for the system speech engine.

``pyttsx3`` drives COM (Windows), NSSpeechSynthesizer (macOS) or eSpeak
(Linux). Those engines are not safe to use from worker threads, so the
provider runs this module in a short-lived process:

    python -m troll_music_ai.providers._speech_worker voices
    python -m troll_music_ai.providers._speech_worker speak <job.json>
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    import pyttsx3

    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    if sys.argv[1] == "voices":
        print(json.dumps([voice.name for voice in voices]))
        return 0

    with open(sys.argv[2], encoding="utf-8") as handle:
        job = json.load(handle)
    engine.setProperty("rate", job.get("rate", 185))
    for item in job["lines"]:
        wanted = (item.get("voice") or "").lower()
        match = next((v for v in voices if wanted and wanted in v.name.lower()), voices[0] if voices else None)
        if match is not None:
            engine.setProperty("voice", match.id)
        engine.save_to_file(item["text"], item["out"])
    engine.runAndWait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
