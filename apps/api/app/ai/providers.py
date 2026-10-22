"""LLM provider adapters behind one interface. Keys never reach the client bundle."""
from __future__ import annotations

import base64
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from ..config import get_settings


@dataclass
class ImageInput:
    data: bytes
    mime: str = "image/png"

    def b64(self) -> str:
        return base64.b64encode(self.data).decode()


@dataclass
class LLMRequest:
    task: str
    system: str
    user: str
    schema_name: str
    json_schema: dict
    images: list[ImageInput] = field(default_factory=list)
    max_tokens: int = 4000


@dataclass
class LLMResponse:
    data: dict
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


class ProviderError(Exception):
    pass


class LLMProvider(ABC):
    name = "base"
    # USD per 1M tokens (input, output) — configurable estimates for cost tracking
    price = (0.0, 0.0)

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def complete_json(self, req: LLMRequest) -> LLMResponse: ...

    def cost(self, r: LLMResponse) -> float:
        p = get_settings().price(r.model) if r.model else {"in": self.price[0], "out": self.price[1]}
        return round(r.input_tokens / 1e6 * p["in"] + r.output_tokens / 1e6 * p["out"], 6)


def _strictify(schema: dict) -> dict:
    """OpenAI strict mode: every object lists all properties as required and forbids extras."""
    s = json.loads(json.dumps(schema))

    def walk(node):
        if isinstance(node, dict):
            if "prefixItems" in node:  # tuples (e.g. polygon points) → plain arrays: strict mode rejects prefixItems
                node["items"] = node.pop("prefixItems")[0]
                node.pop("minItems", None)
                node.pop("maxItems", None)
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"].keys())
                node["additionalProperties"] = False
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(s)
    for d in s.get("$defs", {}).values():
        walk(d)
    return s


class OpenAIProvider(LLMProvider):
    name = "openai"
    price = (1.25, 10.0)

    def __init__(self, client: httpx.Client | None = None):
        self.s = get_settings()
        self.client = client or httpx.Client(timeout=self.s.ai_timeout_s)

    @property
    def model(self) -> str:
        return self.s.openai_model

    def available(self) -> bool:
        return bool(self.s.openai_api_key)

    def complete_json(self, req: LLMRequest) -> LLMResponse:
        content = [{"type": "input_text", "text": req.user}]
        for im in req.images:
            content.append({"type": "input_image", "image_url": f"data:{im.mime};base64,{im.b64()}"})
        body = {
            "model": self.model,
            "input": [{"role": "developer", "content": req.system}, {"role": "user", "content": content}],
            "text": {"format": {"type": "json_schema", "name": req.schema_name, "schema": _strictify(req.json_schema), "strict": True}},
            "max_output_tokens": req.max_tokens,
        }
        t = time.time()
        r = self.client.post("https://api.openai.com/v1/responses", json=body, headers={"Authorization": f"Bearer {self.s.openai_api_key}"})
        if r.status_code >= 400:
            raise ProviderError(f"openai {r.status_code}: {r.text[:300]}")
        j = r.json()
        text = None
        for item in j.get("output", []):
            for c in item.get("content", []) or []:
                if c.get("type") == "output_text":
                    text = c.get("text")
        if text is None:
            raise ProviderError("openai: no output_text")
        u = j.get("usage", {})
        return LLMResponse(json.loads(text), self.name, self.model, u.get("input_tokens", 0), u.get("output_tokens", 0), int((time.time() - t) * 1000))


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    price = (5.0, 25.0)

    def __init__(self, client: httpx.Client | None = None):
        self.s = get_settings()
        self.client = client or httpx.Client(timeout=self.s.ai_timeout_s)

    @property
    def model(self) -> str:
        return self.s.anthropic_model

    def available(self) -> bool:
        return bool(self.s.anthropic_api_key)

    def complete_json(self, req: LLMRequest) -> LLMResponse:
        content: list[dict] = []
        for im in req.images:
            content.append({"type": "image", "source": {"type": "base64", "media_type": im.mime, "data": im.b64()}})
        content.append({"type": "text", "text": req.user})
        body = {
            "model": self.model,
            "max_tokens": req.max_tokens,
            "system": req.system,
            "messages": [{"role": "user", "content": content}],
            "tools": [{"name": "emit_result", "description": f"Return the {req.schema_name} result", "input_schema": req.json_schema}],
            "tool_choice": {"type": "tool", "name": "emit_result"},
        }
        t = time.time()
        r = self.client.post("https://api.anthropic.com/v1/messages", json=body,
                             headers={"x-api-key": self.s.anthropic_api_key or "", "anthropic-version": "2023-06-01"})
        if r.status_code >= 400:
            raise ProviderError(f"anthropic {r.status_code}: {r.text[:300]}")
        j = r.json()
        block = next((b for b in j.get("content", []) if b.get("type") == "tool_use"), None)
        if not block:
            raise ProviderError("anthropic: no tool_use block")
        u = j.get("usage", {})
        return LLMResponse(block["input"], self.name, self.model, u.get("input_tokens", 0), u.get("output_tokens", 0), int((time.time() - t) * 1000))


class GeminiProvider(LLMProvider):
    name = "gemini"
    price = (1.25, 10.0)

    def __init__(self, client: httpx.Client | None = None):
        self.s = get_settings()
        self.client = client or httpx.Client(timeout=self.s.ai_timeout_s)

    @property
    def model(self) -> str:
        return self.s.gemini_model

    def model_for(self, req: LLMRequest) -> str:
        """Vision tasks (plans, photos) use the stronger model; text tasks the fast one."""
        return self.s.gemini_vision_model if req.images and self.s.gemini_vision_model else self.s.gemini_model

    def available(self) -> bool:
        return bool(self.s.gemini_api_key)

    def complete_json(self, req: LLMRequest) -> LLMResponse:
        model = self.model_for(req)
        parts: list[dict] = [{"text": req.user}]
        for im in req.images:
            parts.append({"inline_data": {"mime_type": im.mime, "data": im.b64()}})
        body = {
            "systemInstruction": {"parts": [{"text": req.system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": req.json_schema, "maxOutputTokens": req.max_tokens},
        }
        t = time.time()
        r = self.client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                             json=body, headers={"x-goog-api-key": self.s.gemini_api_key or ""})
        if r.status_code >= 400:
            raise ProviderError(f"gemini {r.status_code}: {r.text[:300]}")
        j = r.json()
        try:
            cand = j["candidates"][0]
            # Gemini 3 may stream the JSON over several parts (and thought-summary parts first): join the answer parts
            text = "".join(p.get("text", "") for p in cand["content"]["parts"] if not p.get("thought"))
        except (KeyError, IndexError) as e:
            raise ProviderError("gemini: empty candidate") from e
        if cand.get("finishReason") == "MAX_TOKENS":
            raise ProviderError(f"gemini: output truncated at maxOutputTokens={req.max_tokens}")
        u = j.get("usageMetadata", {})
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderError(f"gemini: invalid JSON ({e.msg} at {e.pos}; finishReason={cand.get('finishReason')})") from e
        return LLMResponse(data, self.name, model, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0), int((time.time() - t) * 1000))


class StubProvider(LLMProvider):
    """Development stub: deterministic rule-based handlers per task. Its results are
    labelled provider='stub' in usage logs and in the UI."""

    name = "stub"

    def __init__(self, handlers: dict | None = None):
        self.handlers = handlers or {}

    @property
    def model(self) -> str:
        return "rules-v1"

    def available(self) -> bool:
        return True

    def complete_json(self, req: LLMRequest) -> LLMResponse:
        h = self.handlers.get(req.task)
        if not h:
            raise ProviderError(f"stub has no handler for {req.task}")
        t = time.time()
        return LLMResponse(h(req), self.name, self.model, 0, 0, int((time.time() - t) * 1000))
