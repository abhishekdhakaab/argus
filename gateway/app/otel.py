from __future__ import annotations

import os

import structlog

logger = structlog.get_logger()


def setup_otel(app) -> None:
    """Instrument FastAPI and optionally export spans over OTLP."""
    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider()

        otlp_endpoint = os.getenv("OTLP_ENDPOINT")
        if otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
            logger.info("otel_configured", export="otlp", endpoint=otlp_endpoint)
        else:
            logger.info("otel_configured", export="none", reason="OTLP_ENDPOINT not set")

        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        logger.info("otel_fastapi_instrumented")

    except ImportError:
        logger.warning("otel_skipped", reason="opentelemetry packages not installed")
