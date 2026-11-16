# Contributing

Thanks for wanting to help. The project is young, so well-scoped contributions land quickly.

## Good first contributions

- **A provider adapter.** The interfaces are in `packages/python-sdk/src/troll_music_ai/providers/base.py`
  and the guide is in [docs/providers.md](docs/providers.md). A music adapter unlocks phase 3.
- **Trying a real model.** Run lyrics generation against Ollama or a hosted API and report what breaks.
- Anything unchecked in [docs/roadmap.md](docs/roadmap.md).

Open an issue before starting something large, so nobody builds the same thing twice.

## Setup

Follow the quick start in the [README](README.md). Then:

```bash
pytest                              # backend and toolkit
npm --prefix apps/web run lint      # web
npm --prefix apps/web run build
```

`python scripts/dev_backend.py --mock` runs the backend with the mock provider, which is enough for UI work.

## Ground rules

1. **Do not claim what is not built.** If a feature is partial, the UI and the docs say so. Update
   `docs/roadmap.md` in the same pull request that finishes something.
2. **No fake results.** Mock providers are for tests and UI development, and must set `is_mock`.
3. **Keep modules independent.** A generator must work without the others. Modules exchange saved assets;
   they do not call each other.
4. **Generation logic lives in the toolkit**, not in the backend or the web app. The toolkit must not import
   from `backend`.
5. **Long work goes in a job**, never in an HTTP handler.
6. **Never regenerate something the user did not ask about.** New output is a new asset version.
7. **Secrets stay server-side** and out of logs and error messages.
8. **Add tests** for services and adapters. Adapters are tested against a fake transport, not the network.
9. Voice features must follow [docs/safety.md](docs/safety.md).
10. State the licence of any model or service an adapter depends on.

## Pull requests

Keep them focused, describe how you tested, and include screenshots for UI changes. By contributing you
agree that your work is released under the MIT licence.
