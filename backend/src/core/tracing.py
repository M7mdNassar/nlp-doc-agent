from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor


def setup_tracing() -> None:
    """Basic OpenTelemetry setup. Can be swapped to OTLP exporter later."""
    provider = TracerProvider()

    # For now, just print spans to console if in debug mode.
    # In production, use OTLPExporter to send to Jaeger/Datadog.
    processor = SimpleSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
