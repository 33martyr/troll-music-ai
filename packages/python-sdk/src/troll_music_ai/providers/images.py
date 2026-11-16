"""Image adapters: built-in typography, Pollinations, OpenAI-compatible, ComfyUI."""

from __future__ import annotations

import asyncio
import base64
import textwrap
from pathlib import Path
from urllib.parse import quote

from ..errors import ProviderResponseError, ProviderUnavailableError
from ..types import ImageRequest
from ._http import HttpAdapter
from .base import ImageGenerationProvider, ProviderInfo, ProviderKind, ProviderStatus

_PALETTES = [
    ((26, 10, 46), (162, 89, 255), (200, 255, 62)),
    ((8, 20, 40), (56, 225, 255), (255, 92, 122)),
    ((40, 8, 24), (255, 92, 122), (255, 194, 75)),
    ((10, 30, 22), (62, 220, 140), (200, 255, 62)),
    ((30, 14, 8), (255, 140, 60), (255, 230, 120)),
]


def _font(size: int):
    from PIL import ImageFont

    for name in ("impact.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def render_card(request: ImageRequest, out_path: Path) -> Path:
    """Draw a typographic card: gradient, shapes, title. Deterministic per seed."""
    import numpy as np
    from PIL import Image, ImageDraw

    width, height = request.width, request.height
    rng = np.random.default_rng(request.seed)
    dark, mid, accent = _PALETTES[int(rng.integers(len(_PALETTES)))]
    angle = rng.uniform(0, np.pi)
    ys, xs = np.mgrid[0:height, 0:width]
    blend = ((xs * np.cos(angle) + ys * np.sin(angle)) / (width + height) + 0.25).clip(0, 1)[..., None]
    pixels = np.array(dark) * (1 - blend) + np.array(mid) * blend * 0.8
    image = Image.fromarray(pixels.astype("uint8"), "RGB")

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for _ in range(int(rng.integers(5, 10))):
        radius = int(rng.uniform(0.05, 0.3) * min(width, height))
        cx, cy = int(rng.uniform(0, width)), int(rng.uniform(0, height))
        color = (*(accent if rng.random() < 0.4 else mid), int(rng.uniform(25, 80)))
        if rng.random() < 0.5:
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color)
        else:
            draw.rectangle((cx - radius, cy - radius // 3, cx + radius, cy + radius // 3), fill=color)
    bar_width = width / 24  # equalizer bars along the bottom
    for index in range(24):
        bar = rng.uniform(0.03, 0.2) * height
        draw.rectangle((index * bar_width + 2, height - bar, (index + 1) * bar_width - 2, height), fill=(*accent, 70))
    image = Image.alpha_composite(image.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(image)
    title = (request.title or request.prompt).strip().upper()
    size = max(24, min(width, height) // 8)
    lines = textwrap.wrap(title, width=max(8, int(width / (size * 0.62))))[:5]
    font = _font(size)
    y = height * 0.5 - len(lines) * size * 0.6
    for line in lines:
        text_width = draw.textlength(line, font=font)
        x = (width - text_width) / 2
        draw.text((x + size * 0.05, y + size * 0.05), line, font=font, fill=(0, 0, 0, 200))
        draw.text((x, y), line, font=font, fill=(245, 245, 250, 255))
        y += size * 1.15
    if request.subtitle:
        small = _font(max(14, size // 3))
        caption = request.subtitle[:80]
        draw.text(((width - draw.textlength(caption, font=small)) / 2, y + size * 0.2), caption, font=small, fill=(*accent, 255))

    target = out_path.with_suffix(".png")
    image.convert("RGB").save(target)
    return target


def _sticker(draw, x: float, y: float, width: float) -> None:
    """A parody parental-advisory sticker: black box, white frame, two lines."""
    height = width * 0.42
    draw.rectangle((x, y, x + width, y + height), fill=(0, 0, 0, 255))
    draw.rectangle((x + width * 0.03, y + width * 0.03, x + width * 0.97, y + height - width * 0.03), outline=(255, 255, 255, 255), width=max(2, int(width * 0.02)))
    for text, share, ty in (("PARENTAL ADVISORY", 0.085, y + height * 0.14), ("EMOTIONAL DAMAGE", 0.14, y + height * 0.45)):
        size = max(10, int(width * share))
        font = _font(size)
        while size > 10 and draw.textlength(text, font=font) > width * 0.84:
            size -= 1
            font = _font(size)
        draw.text((x + (width - draw.textlength(text, font=font)) / 2, ty), text, font=font, fill=(255, 255, 255, 255))


def _outlined(draw, xy: tuple[float, float], text: str, font, fill=(255, 255, 255, 255), stroke: int = 4) -> None:
    draw.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0, 255))


def meme_cover(source: Path, out_path: Path, *, title: str, artist: str) -> Path:
    """Turn a square picture into a fake album cover: artist, title and a
    parody advisory sticker drawn on top with Pillow (not an AI model)."""
    from PIL import Image, ImageDraw

    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    side = image.width
    draw = ImageDraw.Draw(image)
    artist_font = _font(max(18, side // 16))
    _outlined(draw, (side * 0.05, side * 0.04), artist.upper()[:32], artist_font, fill=(200, 255, 62, 255), stroke=max(2, side // 220))
    size = max(24, side // 11)
    lines = textwrap.wrap(title.upper(), width=max(8, int(side / (size * 0.62))))[:3]
    title_font = _font(size)
    y = side * 0.62 - (len(lines) - 1) * size * 1.1
    for line in lines:
        _outlined(draw, (side * 0.05, y), line, title_font, stroke=max(3, side // 160))
        y += size * 1.1
    sticker = side * 0.3
    _sticker(draw, side - sticker - side * 0.04, side - sticker * 0.42 - side * 0.04, sticker)
    target = out_path.with_suffix(".png")
    image.convert("RGB").save(target)
    return target


def intro_card(out_path: Path, *, width: int, height: int, presenter: str, title: str, seed: int = 0) -> Path:
    """A dramatic opening title card for a meme video: '<presenter> PRESENTS'."""
    from PIL import Image, ImageDraw

    base = render_card(ImageRequest(prompt=f"intro card {title}", width=width, height=height, seed=seed, title=" "), out_path.with_name(out_path.stem + "_bg"))
    with Image.open(base) as opened:
        image = opened.convert("RGBA")
    shade = Image.new("RGBA", image.size, (0, 0, 0, 150))
    image = Image.alpha_composite(image, shade)
    draw = ImageDraw.Draw(image)
    short = min(width, height)
    small, big = _font(max(16, short // 18)), _font(max(28, short // 8))
    presents = f"{presenter.upper()[:30]} PRESENTS"
    lines = textwrap.wrap(title.upper(), width=max(8, int(width / (short // 8 * 0.62))))[:4]
    y = height * 0.5 - (len(lines) * short // 8 * 1.1) / 2
    draw.text(((width - draw.textlength(presents, font=small)) / 2, y - short // 18 * 2.2), presents, font=small, fill=(200, 255, 62, 255))
    for line in lines:
        _outlined(draw, ((width - draw.textlength(line, font=big)) / 2, y), line, big, stroke=max(3, short // 180))
        y += short // 8 * 1.1
    sticker = short * 0.32
    _sticker(draw, (width - sticker) / 2, y + short * 0.05, sticker)
    target = out_path.with_suffix(".png")
    image.convert("RGB").save(target)
    return target


class TypographicProvider(ImageGenerationProvider):
    """Built-in title cards drawn with Pillow. Not an AI model."""

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="typographic", kind=ProviderKind.IMAGE, model="troll-cards-1", is_ai=False)

    async def check(self) -> ProviderStatus:
        return ProviderStatus(ok=True, detail="Built-in typographic cards, always available. Not an AI model.")

    async def generate_image(self, request: ImageRequest, out_path: Path) -> Path:
        return await asyncio.to_thread(render_card, request, out_path)


class PollinationsImageProvider(HttpAdapter, ImageGenerationProvider):
    """Pollinations.ai image API. Hosted, usable without a key but heavily
    rate-limited; a key raises the limits. Prompts leave this machine."""

    name = "pollinations"

    def __init__(self, *, model: str = "flux", retries: int = 5, retry_seconds: float = 12.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self._model = model
        self._retries = retries
        self._retry_seconds = retry_seconds

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, kind=ProviderKind.IMAGE, model=self._model, endpoint=self._base_url)

    async def check(self) -> ProviderStatus:
        ok, detail, _ = await self._probe("/models")
        return ProviderStatus(ok=ok, detail=detail + (" Free tier is rate-limited." if ok and not self._api_key else ""))

    async def generate_image(self, request: ImageRequest, out_path: Path) -> Path:
        params = {
            "width": request.width, "height": request.height, "seed": request.seed,
            "model": self._model, "nologo": "true",
        }
        last: Exception | None = None
        for attempt in range(self._retries):
            try:
                response = await self._send("GET", f"/prompt/{quote(request.prompt[:900], safe='')}", params=params)
            except ProviderResponseError as exc:
                if exc.status_code not in (429, 500, 502, 503):
                    raise
                last = exc
                await asyncio.sleep(self._retry_seconds * (attempt + 1))
                continue
            if not response.headers.get("content-type", "").startswith("image/"):
                raise ProviderResponseError("Pollinations did not return an image.")
            target = out_path.with_suffix(".jpg")
            target.write_bytes(response.content)
            return target
        raise ProviderUnavailableError(
            f"Pollinations is rate-limiting requests ({last.message if last else 'busy'}). "
            "Try again shortly or set an API key."
        )


class OpenAIImagesProvider(HttpAdapter, ImageGenerationProvider):
    """Any server with the OpenAI ``/images/generations`` endpoint."""

    name = "openai_images"

    def __init__(self, *, model: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._model = model

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, kind=ProviderKind.IMAGE, model=self._model, endpoint=self._base_url)

    async def check(self) -> ProviderStatus:
        ok, detail, _ = await self._probe("/models")
        return ProviderStatus(ok=ok, detail=detail)

    async def generate_image(self, request: ImageRequest, out_path: Path) -> Path:
        # Hosted image models only accept a few sizes; the caller crops and scales.
        ratio = request.width / request.height
        size = "1024x1024" if 0.8 < ratio < 1.25 else "1536x1024" if ratio > 1 else "1024x1536"
        response = await self._send(
            "POST", "/images/generations", json={"model": self._model, "prompt": request.prompt, "size": size, "n": 1}
        )
        try:
            item = response.json()["data"][0]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(f"{self.name} returned no image.") from exc
        if item.get("b64_json"):
            content = base64.b64decode(item["b64_json"])
        elif item.get("url"):
            content = (await self._send("GET", item["url"])).content
        else:
            raise ProviderResponseError(f"{self.name} returned no image.")
        target = out_path.with_suffix(".png")
        target.write_bytes(content)
        return target


class ComfyUIProvider(HttpAdapter, ImageGenerationProvider):
    """A local ComfyUI server running a standard text-to-image graph.

    ``model`` is the checkpoint file name as ComfyUI lists it.

    NOTE: follows ComfyUI's documented HTTP API but has not yet been run
    against a live server by the maintainers.
    """

    name = "comfyui"

    def __init__(self, *, model: str, steps: int = 20, cfg: float = 7.0, poll_seconds: float = 1.5, **kwargs) -> None:
        kwargs.setdefault("timeout", 600.0)
        super().__init__(**kwargs)
        self._model = model
        self._steps = steps
        self._cfg = cfg
        self._poll_seconds = poll_seconds

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, kind=ProviderKind.IMAGE, model=self._model, endpoint=self._base_url)

    async def check(self) -> ProviderStatus:
        ok, detail, _ = await self._probe("/system_stats")
        return ProviderStatus(ok=ok, detail=detail)

    def _workflow(self, request: ImageRequest) -> dict:
        # ComfyUI's stock SD/SDXL sizes must be multiples of 8.
        width, height = request.width // 8 * 8, request.height // 8 * 8
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": self._model}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": request.prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "text, watermark, blurry, low quality", "clip": ["1", 1]}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": request.seed, "steps": self._steps, "cfg": self._cfg, "sampler_name": "euler",
                    "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0],
                    "negative": ["3", 0], "latent_image": ["4", 0],
                },
            },
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "troll"}},
        }

    async def generate_image(self, request: ImageRequest, out_path: Path) -> Path:
        queued = (await self._send("POST", "/prompt", json={"prompt": self._workflow(request)})).json()
        prompt_id = queued.get("prompt_id")
        if not prompt_id:
            raise ProviderResponseError(f"ComfyUI rejected the workflow: {str(queued)[:200]}")
        waited = 0.0
        while waited < self._timeout:
            await asyncio.sleep(self._poll_seconds)
            waited += self._poll_seconds
            history = (await self._send("GET", f"/history/{prompt_id}")).json().get(prompt_id)
            if not history:
                continue
            images = [image for node in history.get("outputs", {}).values() for image in node.get("images", [])]
            if not images:
                raise ProviderResponseError("ComfyUI finished without an image. Check the checkpoint name.")
            first = images[0]
            content = await self._send(
                "GET", "/view",
                params={"filename": first["filename"], "subfolder": first.get("subfolder", ""), "type": first.get("type", "output")},
            )
            target = out_path.with_suffix(".png")
            target.write_bytes(content.content)
            return target
        raise ProviderUnavailableError(f"ComfyUI did not finish within {self._timeout:.0f}s.")
