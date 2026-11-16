# Backend image. Build from the repository root:
#   docker build -t troll-music-backend .
FROM python:3.12-slim

# FFmpeg: audio processing and video rendering. espeak-ng: the speech engine
# pyttsx3 uses on Linux (the built-in system_tts voice provider). fonts-dejavu:
# title cards and burned-in subtitles.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg espeak-ng libespeak1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY packages/python-sdk packages/python-sdk
COPY pyproject.toml ./
COPY backend backend
# Local AI extras (torch, transformers) are deliberately not installed: they add
# several GB. Build a derived image with ".[musicgen]" if you want MusicGen.
RUN pip install --no-cache-dir ./packages/python-sdk ".[postgres]"

RUN useradd --create-home troll && mkdir -p /app/data && chown -R troll /app/data
USER troll

ENV TROLL_DATABASE_URL=sqlite:////app/data/troll.db \
    TROLL_STORAGE_DIR=/app/data/storage
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
