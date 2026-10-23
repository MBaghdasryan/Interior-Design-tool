"""Render providers. `GeminiImageProvider` (Gemini image models) is the photoreal provider;
`BlenderProvider` is the integration boundary for a Cycles worker (not deployed).
Prompts are versioned files in app/ai/prompts (render_room.v1, render_edit.v1)."""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field

import httpx

from ..config import get_settings

PROMPT_VERSION = "v1"


class RenderError(Exception):
    pass


@dataclass
class RenderResult:
    image: bytes
    mime: str
    model: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    images: int = 1
    meta: dict = field(default_factory=dict)


class RenderProvider:
    name = "base"

    def available(self) -> bool:  # pragma: no cover - interface
        return False

    def generate(self, prompt: str, images: list[tuple[bytes, str]], *, size: str | None = None) -> RenderResult:  # pragma: no cover
        raise NotImplementedError

    def cost(self, r: RenderResult) -> float:
        p = get_settings().price(r.model)
        return round(r.images * p.get("image", 0.0) + r.input_tokens / 1e6 * p["in"] + r.output_tokens / 1e6 * p["out"], 6)


class GeminiImageProvider(RenderProvider):
    name = "gemini"

    def __init__(self, client: httpx.Client | None = None):
        self.s = get_settings()
        self.client = client or httpx.Client(timeout=max(self.s.ai_timeout_s, 180))

    @property
    def model(self) -> str:
        return self.s.render_model

    def available(self) -> bool:
        return bool(self.s.gemini_api_key)

    def generate(self, prompt: str, images: list[tuple[bytes, str]], *, size: str | None = None, aspect: str = "16:9") -> RenderResult:
        parts: list[dict] = [{"text": prompt}] + [{"inline_data": {"mime_type": mime, "data": base64.b64encode(b).decode()}} for b, mime in images]
        cfg: dict = {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}
        if size or self.s.render_image_size:
            cfg["imageConfig"]["imageSize"] = size or self.s.render_image_size
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": cfg}
        t = time.time()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        r = None
        for attempt in range(3):  # 429/503 from the image models are common → backoff
            r = self.client.post(url, json=body, headers={"x-goog-api-key": self.s.gemini_api_key or ""})
            if r.status_code == 400 and "imageSize" in r.text and "imageSize" in cfg["imageConfig"]:
                cfg["imageConfig"].pop("imageSize")  # model without size control → default resolution
                continue
            if r.status_code not in (429, 500, 503):
                break
            time.sleep(2 * 2 ** attempt)
        if r is None or r.status_code >= 400:
            raise RenderError(f"gemini image {r.status_code if r is not None else '-'}: {r.text[:300] if r is not None else ''}")
        j = r.json()
        try:
            part = next(p for p in j["candidates"][0]["content"]["parts"] if "inlineData" in p)
        except (KeyError, IndexError, StopIteration) as e:
            reason = (j.get("candidates") or [{}])[0].get("finishReason") or j.get("promptFeedback")
            raise RenderError(f"gemini image: no image returned ({reason})") from e
        u = j.get("usageMetadata", {})
        return RenderResult(base64.b64decode(part["inlineData"]["data"]), part["inlineData"].get("mimeType", "image/png"), self.model,
                            int((time.time() - t) * 1000), u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0),
                            meta={"image_size": cfg["imageConfig"].get("imageSize", "default"), "aspect": aspect})


class BlenderProvider(RenderProvider):
    """Integration boundary for a Blender/Cycles worker (deterministic, geometry-exact renders
    from the GLB export). Not deployed — available() is False until RENDER_BLENDER_URL exists."""

    name = "blender"

    def available(self) -> bool:
        return False


def get_render_provider() -> RenderProvider | None:
    for p in (GeminiImageProvider(),):
        if p.available():
            return p
    return None
