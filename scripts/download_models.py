"""Download model weights for local AI providers. Nothing else in this project
downloads weights: this script is the only place it happens, and only when you
run it.

    python scripts/download_models.py --list
    python scripts/download_models.py musicgen
    python scripts/download_models.py musicgen --model facebook/musicgen-medium

Weights go to the Hugging Face cache (~/.cache/huggingface, or HF_HOME).
"""

from __future__ import annotations

import argparse
import sys

MODELS = {
    "musicgen": {
        "default": "facebook/musicgen-small",
        "sizes": {
            "facebook/musicgen-small": "about 2.4 GB on disk, 4 GB VRAM",
            "facebook/musicgen-medium": "about 8 GB on disk, 8 GB+ VRAM",
            "facebook/musicgen-stereo-small": "about 2.4 GB on disk, 4 GB VRAM",
        },
        "license": "CC-BY-NC 4.0: NON-COMMERCIAL use only",
        "then": "Set TROLL_MUSIC_PROVIDER=musicgen (or choose MusicGen in Model Settings).",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Download weights for local AI providers.")
    parser.add_argument("name", nargs="?", choices=sorted(MODELS))
    parser.add_argument("--model", help="a specific model id instead of the default")
    parser.add_argument("--list", action="store_true", help="show what can be downloaded and exit")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args()

    if args.list or not args.name:
        for name, entry in MODELS.items():
            print(f"{name}  (licence: {entry['license']})")
            for model, size in entry["sizes"].items():
                print(f"  {model}: {size}{'  [default]' if model == entry['default'] else ''}")
        return 0

    entry = MODELS[args.name]
    model = args.model or entry["default"]
    print(f"Model:   {model}")
    print(f"Size:    {entry['sizes'].get(model, 'unknown; check the model card')}")
    print(f"Licence: {entry['license']}")
    if not args.yes and input("Download now? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing downloaded.")
        return 1
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub is missing. Install the model extras first: pip install torch transformers", file=sys.stderr)
        return 2
    # Skip the duplicate weight formats the loader does not need.
    path = snapshot_download(model, ignore_patterns=["*.bin", "*.onnx", "*.msgpack", "*.h5"])
    print(f"Saved to {path}")
    print(entry["then"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
