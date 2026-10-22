"""P1-5: per-organisation AI budget — spend accounting, refusal for interactive calls,
deterministic fallback for background jobs, bureau usage endpoint."""
import pytest

from app import models as m
from app.ai import stub
from app.ai.budget import QuotaExceeded, check, summary
from app.ai.orchestrator import Orchestrator
from app.ai.providers import LLMProvider, LLMResponse, StubProvider
from app.db import SessionLocal

pytestmark = pytest.mark.usefixtures("client")


class _Paid(LLMProvider):
    name = "openai"

    @property
    def model(self):
        return "gpt-5.5"

    def available(self):
        return True

    def complete_json(self, req):
        return LLMResponse(stub.HANDLERS[req.task](req), self.name, self.model, 400_000, 100_000, 5)


def _demo(db):
    return db.query(m.Project).filter(m.Project.title.like("Демо%")).first()


def test_spend_is_logged_per_org_and_budget_enforced(client, designer):
    orch = Orchestrator(providers={"openai": _Paid(), "stub": StubProvider(stub.HANDLERS)})
    orch.s.ai_default_provider = "auto"
    with SessionLocal() as db:
        proj = _demo(db)
        org = db.get(m.Organization, proj.org_id)
        org.settings = {**(org.settings or {}), "ai_budget": {"daily_usd": 1.0, "monthly_usd": 10.0}}
        db.commit()
        _, prov = orch.run("design_brief", {"rooms": [], "brief": {}, "t": 1}, db=db, project_id=proj.id)
        db.commit()
        u = db.query(m.AIUsage).filter_by(org_id=proj.org_id, provider="openai").first()
        assert prov == "openai" and u.cost_usd == pytest.approx(0.4 * 1.25 + 0.1 * 10.0) and u.trace_id  # 1.5 USD estimate
        with pytest.raises(QuotaExceeded) as e:
            check(db, proj.org_id)
        assert e.value.period == "daily"
        with pytest.raises(QuotaExceeded):  # interactive call refused
            orch.run("design_brief", {"rooms": [], "brief": {}, "t": 2}, db=db, project_id=proj.id)
        _, prov2 = orch.run("design_brief", {"rooms": [], "brief": {}, "t": 3}, db=db, project_id=proj.id, stub_on_quota=True)
        assert prov2 == "stub"  # background job continues on deterministic rules
        s = summary(db, proj.org_id)
        assert s["today_usd"] >= 1.5 and s["limits"]["daily_usd"] == 1.0 and any(r["provider"] == "openai" for r in s["by_task"])
        org.settings = {k: v for k, v in org.settings.items() if k != "ai_budget"}
        db.query(m.AIUsage).filter_by(org_id=proj.org_id, provider="openai").delete()
        db.commit()


def test_bureau_usage_and_budget_endpoints(client):
    from tests.conftest import login

    h = login(client, "bureau@forma.local")
    r = client.put("/api/v1/bureau/ai-budget", headers=h, json={"daily_usd": 3, "monthly_usd": 30})
    assert r.status_code == 200 and r.json()["limits"] == {"daily_usd": 3.0, "monthly_usd": 30.0}
    assert client.get("/api/v1/bureau/ai-usage", headers=h).json()["limits"]["daily_usd"] == 3.0
    designer = login(client)
    assert client.put("/api/v1/bureau/ai-budget", headers=designer, json={"daily_usd": 999, "monthly_usd": 999}).status_code == 403


def test_gemini_joins_multipart_json_and_reports_truncation():
    """Gemini 3 can return the JSON over several parts (after a thought part); a MAX_TOKENS stop is reported, not mis-parsed."""
    import httpx

    from app.ai.providers import GeminiProvider, LLMRequest, ProviderError

    replies = []

    def handler(request):
        return httpx.Response(200, json=replies.pop(0))

    g = GeminiProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    req = LLMRequest(task="design_brief", system="s", user="u", schema_name="X", json_schema={"type": "object"})
    replies.append({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "plan…", "thought": True}, {"text": '{"rooms": [1,'}, {"text": ' 2]}'}]}}],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}})
    assert g.complete_json(req).data == {"rooms": [1, 2]}
    replies.append({"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": '{"rooms": [1,'}]}}]})
    with pytest.raises(ProviderError, match="truncated"):
        g.complete_json(req)
