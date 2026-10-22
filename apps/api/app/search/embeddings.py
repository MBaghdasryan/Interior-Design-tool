"""Embedding providers behind one interface (P2-4).

* `local` (default, no network, no cost): multilingual LEXICAL vectors — word and character
  3–5-gram hashing (works across Armenian, Cyrillic and Latin script) plus taxonomy expansion, so
  «բազմոց», «диван» and «sofa» meet through the shared category vocabulary. It is not a neural
  model and the UI says so.
* `gemini`: `gemini-embedding-001` (needs GEMINI_API_KEY with quota). Any provider error falls back
  to `local` and the status reports it — results from different providers are never mixed.
* `off`: semantic search disabled; the catalogue keeps its keyword search.
"""
from __future__ import annotations

import hashlib
import math
import re

import httpx

from ..catalog.taxonomy import CATEGORIES
from ..config import get_settings

DIM_LOCAL = 512
WORD = re.compile(r"[\wԱ-֏]+", re.UNICODE)


class EmbeddingError(Exception):
    pass


def _expand(text: str) -> str:
    """Append every-language names of taxonomy categories mentioned in the text (cross-lingual bridge)."""
    low = text.lower()
    extra = []
    for key, (_, ru, hy, en) in CATEGORIES.items():
        names = (key.replace("_", " "), ru.lower(), hy.lower(), en.lower())
        if any(n and n in low for n in names):
            extra += [key, ru, hy, en]
    return text + (" " + " ".join(extra) if extra else "")


class LocalLexical:
    name, model, dim = "local", "lexical-hash-v1", DIM_LOCAL

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for w in WORD.findall(_expand(text).lower()):
            feats = [f"w:{w}"] + [f"g:{g}" for n in (3, 4, 5) for g in (f"<{w}>"[i:i + n] for i in range(max(1, len(w) + 3 - n)))]
            for f in feats:
                h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
                v[h % self.dim] += (1.0 if (h >> 63) & 1 else -1.0) * (2.0 if f.startswith("w:") else 1.0)
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]


class GeminiEmbeddings:
    name, model, dim = "gemini", "gemini-embedding-001", 768

    def __init__(self, client: httpx.Client | None = None):
        self.key = get_settings().gemini_api_key or ""
        self.client = client or httpx.Client(timeout=30)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for i in range(0, len(texts), 100):
            body = {"requests": [{"model": f"models/{self.model}", "content": {"parts": [{"text": t[:2000]}]}, "outputDimensionality": self.dim} for t in texts[i:i + 100]]}
            r = self.client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:batchEmbedContents", json=body, headers={"x-goog-api-key": self.key})
            if r.status_code >= 400:
                raise EmbeddingError(f"gemini {r.status_code}")
            for e in r.json()["embeddings"]:
                vals = e["values"]
                n = math.sqrt(sum(x * x for x in vals)) or 1.0
                out.append([x / n for x in vals])
        return out


_last_error: dict[str, str] = {}


def text_provider():
    """→ provider or None when search is off. `auto` prefers Gemini when a key is configured."""
    mode = (get_settings().search_embeddings or "local").lower()
    if mode == "off":
        return None
    if mode == "gemini" or (mode == "auto" and get_settings().gemini_api_key):
        return GeminiEmbeddings()
    return LocalLexical()


def embed_texts(texts: list[str]):
    """→ (provider used, vectors). A remote failure falls back to local and is reported in status()."""
    prov = text_provider()
    if prov is None:
        raise EmbeddingError("search.off")
    try:
        return prov, prov.embed(texts)
    except (EmbeddingError, httpx.HTTPError) as e:
        _last_error[prov.name] = str(e)[:200]
        local = LocalLexical()
        return local, local.embed(texts)


def status() -> dict:
    prov = text_provider()
    return {"mode": (get_settings().search_embeddings or "local").lower(), "text_provider": prov.name if prov else "off", "text_model": prov.model if prov else None,
            "neural": bool(prov and prov.name != "local"), "image_provider": "local-visual-v1", "last_error": dict(_last_error)}
