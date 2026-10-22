"""AI orchestrator: versioned prompts, routing per task, retries + provider
fallback, schema validation, caching, usage/cost logging."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections import OrderedDict
from pathlib import Path

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from . import budget, stub
from .providers import AnthropicProvider, GeminiProvider, ImageInput, LLMProvider, LLMRequest, OpenAIProvider, ProviderError, StubProvider
from .schemas import ChangePlan, DesignBrief, FloorplanRecognition, VariantCopy

log = logging.getLogger("forma.ai")
PROMPTS_DIR = Path(__file__).parent / "prompts"

TASKS: dict[str, tuple[type[BaseModel], str]] = {
    "design_brief": (DesignBrief, "v1"),
    "change_command": (ChangePlan, "v1"),
    "floorplan_vision": (FloorplanRecognition, "v1"),
    "variant_copy": (VariantCopy, "v1"),
}
# Preferred provider order per task when ai_default_provider=auto
ROUTING: dict[str, list[str]] = {
    "design_brief": ["openai", "anthropic", "gemini"],
    "change_command": ["openai", "anthropic", "gemini"],
    "floorplan_vision": ["openai", "gemini", "anthropic"],
    "variant_copy": ["anthropic", "openai", "gemini"],
}


def load_prompt(task: str, version: str) -> str:
    return (PROMPTS_DIR / f"{task}.{version}.md").read_text(encoding="utf-8")


class Orchestrator:
    def __init__(self, providers: dict[str, LLMProvider] | None = None, cache_size: int = 256):
        self.s = get_settings()
        self.providers = providers or {
            "openai": OpenAIProvider(),
            "anthropic": AnthropicProvider(),
            "gemini": GeminiProvider(),
            "stub": StubProvider(stub.HANDLERS),
        }
        self._cache: OrderedDict[str, tuple[dict, str]] = OrderedDict()
        self.cache_size = cache_size
        # per-provider circuit breaker: after 3 consecutive failures skip it for 5 minutes
        self._fails: dict[str, int] = {}
        self._open_until: dict[str, float] = {}
        self.sleep = time.sleep

    def chain(self, task: str) -> list[LLMProvider]:
        pref = self.s.ai_default_provider
        names = [pref] if pref not in ("auto", "stub") else ROUTING.get(task, ["openai", "anthropic", "gemini"])
        now = time.time()
        out = [self.providers[n] for n in names if n in self.providers and self.providers[n].available() and self._open_until.get(n, 0) <= now]
        out.append(self.providers["stub"])
        return out

    def status(self) -> dict:
        return {name: {"available": p.available(), "model": p.model} for name, p in self.providers.items()}

    def run(self, task: str, payload: dict, *, db: Session | None = None, project_id: str | None = None,
            images: list[ImageInput] | None = None, retries: int = 1, stub_on_quota: bool = False) -> tuple[BaseModel, str]:
        """Returns (validated model, provider name). Paid providers are skipped when the
        organisation's AI budget is exhausted: background jobs fall back to the deterministic
        rules (`stub_on_quota=True`), interactive calls raise QuotaExceeded."""
        schema_model, version = TASKS[task]
        system = load_prompt(task, version)
        user = json.dumps(payload, ensure_ascii=False)
        key = hashlib.sha256(f"{task}|{version}|{user}|{len(images or [])}".encode()).hexdigest()
        if key in self._cache and not images:
            data, prov = self._cache[key]
            return schema_model.model_validate(data), prov
        req = LLMRequest(task=task, system=system, user=user, schema_name=schema_model.__name__, json_schema=schema_model.model_json_schema(), images=images or [])
        errors: list[str] = []
        trace_id = uuid.uuid4().hex[:12]
        org_id = budget.org_of_project(db, project_id) if db is not None else None
        providers = self.chain(task)
        try:
            budget.check(db, org_id) if db is not None else None
        except budget.QuotaExceeded:
            if not stub_on_quota:
                raise
            providers = [self.providers["stub"]]
        for provider in providers:
            for attempt in range(retries + 1):
                if attempt:
                    self.sleep(min(8.0, 1.5 * 2 ** (attempt - 1)))  # exponential backoff for 429/503
                try:
                    resp = provider.complete_json(req)
                    model = schema_model.model_validate(resp.data)
                    self._fails[provider.name] = 0
                    self._log(db, project_id, task, version, provider, resp.input_tokens, resp.output_tokens, resp.latency_ms, provider.cost(resp), True, None,
                              org_id=org_id, trace_id=trace_id, model=resp.model)
                    self._cache[key] = (model.model_dump(), provider.name)
                    while len(self._cache) > self.cache_size:
                        self._cache.popitem(last=False)
                    return model, provider.name
                except (ProviderError, ValidationError, ValueError, KeyError) as e:
                    errors.append(f"{provider.name}#{attempt}: {e}")
                    log.warning("AI task %s [%s] failed on %s: %s", task, trace_id, provider.name, str(e)[:200])
                    if provider.name != "stub":
                        self._fails[provider.name] = self._fails.get(provider.name, 0) + 1
                        if self._fails[provider.name] >= 3:
                            self._open_until[provider.name] = time.time() + 300
                    self._log(db, project_id, task, version, provider, 0, 0, 0, 0.0, False, str(e)[:500], org_id=org_id, trace_id=trace_id)
                except Exception as e:  # network errors etc.
                    errors.append(f"{provider.name}#{attempt}: {e}")
                    self._log(db, project_id, task, version, provider, 0, 0, 0, 0.0, False, str(e)[:500], org_id=org_id, trace_id=trace_id)
                    break
        raise ProviderError("; ".join(errors))

    def _log(self, db, project_id, task, version, provider, tin, tout, lat, cost, ok, err, *, org_id=None, trace_id=None, model=None):
        if db is None:
            return
        db.add(m.AIUsage(project_id=project_id, org_id=org_id, trace_id=trace_id, task=task, provider=provider.name, model=model or provider.model, prompt_version=version,
                         input_tokens=tin, output_tokens=tout, latency_ms=lat, cost_usd=cost, ok=ok, error=err))
        db.flush()


_orch: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orch
    if _orch is None:
        _orch = Orchestrator()
    return _orch
