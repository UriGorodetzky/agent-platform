"""Distributed tracing with OpenTelemetry (the third observability pillar).

A trace follows one request as a tree of spans (each a timed unit of work).
Auto-instrumentation gives us a server span per HTTP request (FastAPI) and a
client span per outbound call (httpx); we add manual spans for the workflow
nodes. Spans are exported over OTLP to a backend like Jaeger.

Tracing only turns on when OTEL_EXPORTER_OTLP_ENDPOINT is set, so tests and
local runs are unaffected. The tracer used in the workflow is a cheap no-op
until a provider is configured here.
"""

from __future__ import annotations

import os


def setup_tracing(app) -> None:
    """Configure the tracer + exporter and instrument FastAPI/httpx — if enabled."""
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return  # tracing disabled

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": "orchestrator"}))
    # OTLPSpanExporter reads OTEL_EXPORTER_OTLP_ENDPOINT and posts to /v1/traces.
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)   # a span per HTTP request
    HTTPXClientInstrumentor().instrument()    # a span per outbound httpx call
