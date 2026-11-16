"""Generate lyrics with the Python toolkit and save them as Markdown.

    TROLL_LLM_PROVIDER=ollama python examples/generate_lyrics.py "A fake millionaire"

Pass --mock to see the flow without a model. Mock output is placeholder text.
"""

from __future__ import annotations

import argparse
import sys

from troll_music_ai import TrollMusic, TrollMusicError
from troll_music_ai.providers import MockTextProvider


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prompt")
    parser.add_argument("--genre", default="drill")
    parser.add_argument("--style", default="diss_track")
    parser.add_argument("--intensity", type=int, default=4)
    parser.add_argument("--out", default="lyrics.md")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    studio = TrollMusic(text_provider=MockTextProvider()) if args.mock else TrollMusic()
    try:
        lyrics = studio.generate_lyrics(
            prompt=args.prompt,
            genre=args.genre,
            style=args.style,
            troll_intensity=args.intensity,
        )
    except TrollMusicError as error:
        print(f"Could not generate lyrics ({error.code}): {error.message}", file=sys.stderr)
        return 1

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(lyrics.to_markdown())
    print(lyrics.to_text())
    print(f"Saved to {args.out}" + (" (MOCK placeholder text)" if lyrics.meta.is_mock else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
