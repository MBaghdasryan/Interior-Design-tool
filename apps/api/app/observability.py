"""Structured logs with a request id, optional OpenTelemetry traces (OTLP) and Sentry.
Everything is opt-in through env so local development stays dependency-free:
LOG_FORMAT=json, OTEL_EXPORTER_OTLP_ENDPOINT, SENTRY_DSN. Secrets and request bodies
are never logged."""
from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid

request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdMiddleware:
    """Pure ASGI middleware: accepts a safe incoming X-Request-ID or creates one, exposes it
    to logs via a contextvar and echoes it in the response; logs one access line per request."""

    def __init__(self, app):
        self.app = app
        self.log = logging.getLogger("forma.access")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if incoming and len(incoming) <= 64 and incoming.replace("-", "").isalnum() else uuid.uuid4().hex[:16]
        token = request_id.set(rid)
        t0 = time.perf_counter()
        status = {"code": 500}

        async def _send(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            path = scope.get("path", "")
            if not path.startswith(("/api/health", "/api/live")):  # probes would flood the log
                self.log.info("%s %s %s %.0fms", scope.get("method"), path, status["code"], (time.perf_counter() - t0) * 1000)
            request_id.reset(token)


def _trace_id() -> str | None:
    try:
        from opentelemetry import trace

        ctx = trace.get_current_span().get_span_context()
        return format(ctx.trace_id, "032x") if ctx.is_valid else None
    except Exception:  # noqa: BLE001
        return None


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname, "logger": record.name,
               "msg": record.getMessage(), "request_id": request_id.get()}
        tid = _trace_id()
        if tid:
            out["trace_id"] = tid
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id.get()
        return super().format(record)


def setup_logging(fmt: str = "text") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if fmt == "json" else _TextFormatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def setup_tracing(app, engine, *, endpoint: str | None, service_name: str, exporter=None):
    """OpenTelemetry for FastAPI, SQLAlchemy and httpx (outgoing calls to AI/APS/catalog sites).
    Returns the provider, or None when neither an endpoint nor a test exporter is given."""
    if not endpoint and exporter is None:
        return None
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls="api/health,api/live")
    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=provider)
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    return provider


def setup_sentry(dsn: str | None, env: str) -> bool:
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(dsn=dsn, environment=env, traces_sample_rate=0.1, send_default_pii=False)
    return True
