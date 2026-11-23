# Safety and privacy

TROLL-MUSIC-AI is for comedy. These are the rules the project is built around.

## What is in place today

- **Lyrics boundaries.** The system prompt for every lyrics request tells the model to write original
  lyrics, aim the jokes at behaviour, situations and fictional or consenting characters, and refuse threats,
  slurs, attacks on protected characteristics, sexual content about real people and private information.
  This is prompt-level guidance. It depends on the model you connect and is not a guarantee.
- **No fake results.** When a provider is missing or fails, the job fails with a readable error. The mock
  provider is opt-in, and its output is marked as mock on the asset, in the UI and in exports.
- **API keys stay on the backend.** Keys are read from the environment, never returned by any endpoint and
  never written into error messages. The web app does not receive them.
- **Local data stays local.** The database and storage directory are in `data/`, which is git-ignored.

- **Friend roasts roast actions, not identities.** Every one-button troll (diss track, roast, meme song,
  group chat roast, meme video) carries a friendship rule in its prompt: jokes come from the situation the user
  typed, never about looks, weight, health, race, religion, gender, sexuality, disability or family tragedy,
  at any intensity, and no surnames, addresses or workplaces even if given. "Brutal" means more exaggeration,
  not crossing those lines. Like the rest, this is prompt-level guidance and depends on the connected model.
- **AI scores are opinions.** Battle scorecards are labelled "AI opinion" with the model's name, and the page
  says the marks are one model's taste and may change if asked again. Friend votes are shown as the verdict.
- **Parody, not imitation.** Meme Factory designs use invented names ("The Trollies"), a generic player and no
  real logos or platform branding, and each carries a "PARODY" mark.
- **Group chat details stay minimal.** Only the names, nicknames and descriptions the user types are sent to
  the text model; the page says so.
- **Rap battles are between fictional characters.** The battle prompt tells the model the two rappers are
  made up and to keep it a roast of their invented traits, never a real person.
- **Optional API key.** `TROLL_API_KEY` puts every route except health behind a bearer key. Media URLs carry a
  per-file HMAC token instead of the key, so a leaked URL opens one file, not the API.
- **Uploads are checked by content.** Every upload is probed with FFmpeg (a renamed text file is rejected),
  size-limited (`TROLL_MAX_UPLOAD_MB`, default 50) and re-encoded before it is stored.
- **Honest labels.** Built-in engines are marked "not AI"; speech vocals are marked "spoken, not sung";
  untested adapters are marked "(untested)" in Model Settings.

## Voice profiles

Implemented to these rules (enforced in `backend/services/voices.py` and covered by tests):

1. A profile cannot be created without the owner's name, a consent statement and an explicit confirmation.
   The request is rejected with `consent_required` otherwise, and nothing is stored.
2. The studio asks the uploader to confirm it is their voice or that they have the owner's permission, and
   not to impersonate anyone. No profiles of public figures or of anyone who has not consented.
3. Samples are stored privately under `voices/`, never listed, and only served to an authorized caller
   (`/api/voices/{id}/sample`). With a hosted cloning provider (ElevenLabs) the sample is also sent to that
   provider, and the page says so.
4. Deleting a profile deletes the sample and the provider-side voice; if the provider's copy cannot be
   removed, the response says so.
5. Samples must be 5 seconds to 5 minutes of audio; quiet or short samples get a warning.

## What is not in place yet

- **User accounts.** The studio is single-tenant: anyone with the API key (or with network access when no
  key is set) sees everything. Run it locally or set `TROLL_API_KEY`.
- **Output moderation.** There is no classifier on generated text; boundaries are prompt-level.
- **Proof of consent.** Consent is recorded as stated by the uploader; the software cannot verify identity.

## Reporting a problem

Open a GitHub issue for bugs. For a security vulnerability, please use GitHub's private vulnerability
reporting on the repository instead of a public issue.
