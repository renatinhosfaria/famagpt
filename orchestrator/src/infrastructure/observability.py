"""
OpenTelemetry observability setup for FamaGPT Orchestrator.
Provides distributed tracing, metrics, and LangSmith integration.
"""
import os
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider, Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.semantic_conventions.resource import ResourceAttributes

from shared.src.utils.logging import get_logger

logger = get_logger(__name__)


class ObservabilityConfig:
    """Configuration for observability components."""

    def __init__(self):
        self.enabled = os.environ.get("OTEL_ENABLED", "true").lower() == "true"
        self.service_name = os.environ.get("OTEL_SERVICE_NAME", "famagpt-orchestrator")
        self.service_version = os.environ.get("OTEL_SERVICE_VERSION", "1.0.0")
        self.environment = os.environ.get("ENVIRONMENT", "development")

        # OTLP Exporter configuration
        self.otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        self.otlp_headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")

        # Sampling configuration
        self.trace_sample_rate = float(os.environ.get("OTEL_TRACE_SAMPLE_RATE", "0.1"))

        # LangSmith integration
        self.langsmith_enabled = os.environ.get("LANGCHAIN_TRACING_V2", "true").lower() == "true"
        self.langsmith_project = os.environ.get("LANGCHAIN_PROJECT", "famagpt-orchestrator")
        self.langsmith_api_key = os.environ.get("LANGCHAIN_API_KEY", "")


class FamaGPTObservability:
    """Main observability manager for FamaGPT."""

    def __init__(self, config: ObservabilityConfig):
        self.config = config
        self.tracer: Optional[trace.Tracer] = None
        self.meter: Optional[metrics.Meter] = None
        self._initialized = False

        # Custom metrics
        self._request_counter = None
        self._request_duration = None
        self._cost_counter = None
        self._rate_limit_counter = None
        self._llm_token_counter = None

    def initialize(self) -> bool:
        """Initialize OpenTelemetry components."""
        if not self.config.enabled:
            logger.info("OpenTelemetry disabled - skipping initialization")
            return False

        try:
            # Setup resource
            resource = Resource.create({
                ResourceAttributes.SERVICE_NAME: self.config.service_name,
                ResourceAttributes.SERVICE_VERSION: self.config.service_version,
                ResourceAttributes.DEPLOYMENT_ENVIRONMENT: self.config.environment,
                "famagpt.component": "orchestrator",
                "famagpt.version": "1.0.0"
            })

            # Setup tracing
            self._setup_tracing(resource)

            # Setup metrics
            self._setup_metrics(resource)

            # Setup auto-instrumentation
            self._setup_auto_instrumentation()

            # Initialize custom metrics
            self._setup_custom_metrics()

            self._initialized = True
            logger.info("OpenTelemetry initialized successfully",
                       service_name=self.config.service_name,
                       otlp_endpoint=self.config.otlp_endpoint,
                       sample_rate=self.config.trace_sample_rate)

            return True

        except Exception as e:
            logger.error("Failed to initialize OpenTelemetry", error=str(e))
            return False

    def _setup_tracing(self, resource: Resource):
        """Setup distributed tracing."""
        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource)

        # Setup OTLP exporter
        if self.config.otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(
                endpoint=self.config.otlp_endpoint,
                headers=self._parse_headers(self.config.otlp_headers)
            )
            span_processor = BatchSpanProcessor(otlp_exporter)
            tracer_provider.add_span_processor(span_processor)

        # Set the global tracer provider
        trace.set_tracer_provider(tracer_provider)

        # Get tracer
        self.tracer = trace.get_tracer(
            __name__,
            version=self.config.service_version
        )

    def _setup_metrics(self, resource: Resource):
        """Setup metrics collection."""
        # Create meter provider
        meter_provider = MeterProvider(resource=resource)

        # Setup OTLP metric exporter
        if self.config.otlp_endpoint:
            otlp_metric_exporter = OTLPMetricExporter(
                endpoint=self.config.otlp_endpoint,
                headers=self._parse_headers(self.config.otlp_headers)
            )
            # Note: Metrics export setup would go here

        # Set the global meter provider
        metrics.set_meter_provider(meter_provider)

        # Get meter
        self.meter = metrics.get_meter(
            __name__,
            version=self.config.service_version
        )

    def _setup_auto_instrumentation(self):
        """Setup automatic instrumentation for common libraries."""
        # FastAPI instrumentation will be done in main.py
        # Here we setup others

        # HTTPx instrumentation (for external API calls)
        HTTPXClientInstrumentor().instrument()

        # Redis instrumentation
        RedisInstrumentor().instrument()

        logger.info("Auto-instrumentation setup complete")

    def _setup_custom_metrics(self):
        """Setup custom business metrics."""
        if not self.meter:
            return

        # Request metrics
        self._request_counter = self.meter.create_counter(
            name="famagpt_requests_total",
            description="Total number of requests processed",
            unit="1"
        )

        self._request_duration = self.meter.create_histogram(
            name="famagpt_request_duration_seconds",
            description="Request processing duration",
            unit="s"
        )

        # Cost tracking
        self._cost_counter = self.meter.create_counter(
            name="famagpt_cost_brl_total",
            description="Total cost in BRL",
            unit="BRL"
        )

        # Rate limiting
        self._rate_limit_counter = self.meter.create_counter(
            name="famagpt_rate_limit_total",
            description="Rate limit hits by type",
            unit="1"
        )

        # LLM specific metrics
        self._llm_token_counter = self.meter.create_counter(
            name="famagpt_llm_tokens_total",
            description="LLM tokens consumed",
            unit="tokens"
        )

    def _parse_headers(self, headers_str: str) -> Dict[str, str]:
        """Parse OTLP headers from environment variable."""
        if not headers_str:
            return {}

        headers = {}
        for header in headers_str.split(","):
            if "=" in header:
                key, value = header.split("=", 1)
                headers[key.strip()] = value.strip()

        return headers

    @contextmanager
    def trace_operation(self, operation_name: str, **attributes):
        """Context manager for tracing operations."""
        if not self._initialized or not self.tracer:
            yield None
            return

        with self.tracer.start_as_current_span(operation_name) as span:
            # Add custom attributes
            for key, value in attributes.items():
                span.set_attribute(key, value)

            try:
                yield span
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    def record_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """Record request metrics."""
        if not self._initialized:
            return

        labels = {
            "method": method,
            "endpoint": endpoint,
            "status_code": str(status_code)
        }

        if self._request_counter:
            self._request_counter.add(1, labels)

        if self._request_duration:
            self._request_duration.record(duration, labels)

    def record_cost(self, cost_brl: float, operation: str = "llm_call"):
        """Record cost metrics."""
        if not self._initialized or not self._cost_counter:
            return

        self._cost_counter.add(cost_brl, {"operation": operation})

    def record_rate_limit(self, limit_type: str, hit: bool = True):
        """Record rate limiting events."""
        if not self._initialized or not self._rate_limit_counter:
            return

        labels = {"limit_type": limit_type, "hit": str(hit).lower()}
        self._rate_limit_counter.add(1, labels)

    def record_llm_tokens(self, prompt_tokens: int, completion_tokens: int, model: str = "gpt-4"):
        """Record LLM token usage."""
        if not self._initialized or not self._llm_token_counter:
            return

        self._llm_token_counter.add(
            prompt_tokens,
            {"token_type": "prompt", "model": model}
        )

        self._llm_token_counter.add(
            completion_tokens,
            {"token_type": "completion", "model": model}
        )

    def trace_langsmith_integration(self, run_id: str, operation: str):
        """Integrate OpenTelemetry traces with LangSmith."""
        if not self._initialized or not self.tracer:
            return

        with self.tracer.start_as_current_span(f"langsmith.{operation}") as span:
            span.set_attribute("langsmith.run_id", run_id)
            span.set_attribute("langsmith.project", self.config.langsmith_project)
            span.set_attribute("langsmith.operation", operation)

            # Add link to LangSmith trace
            if self.config.langsmith_enabled:
                span.add_link(
                    trace.Link(
                        trace.SpanContext(
                            trace_id=int(run_id, 16) if run_id else 0,
                            span_id=int(run_id[:16], 16) if run_id else 0,
                            is_remote=True
                        )
                    )
                )

    def shutdown(self):
        """Shutdown observability components."""
        if self._initialized:
            # Flush any pending traces/metrics
            if hasattr(trace.get_tracer_provider(), 'shutdown'):
                trace.get_tracer_provider().shutdown()

            logger.info("OpenTelemetry shutdown complete")


# Global observability instance
_observability: Optional[FamaGPTObservability] = None


def get_observability() -> Optional[FamaGPTObservability]:
    """Get the global observability instance."""
    return _observability


def initialize_observability() -> bool:
    """Initialize global observability."""
    global _observability

    config = ObservabilityConfig()
    _observability = FamaGPTObservability(config)

    return _observability.initialize()


def shutdown_observability():
    """Shutdown global observability."""
    global _observability

    if _observability:
        _observability.shutdown()
        _observability = None


# Convenience functions
def trace_operation(operation_name: str, **attributes):
    """Trace an operation (convenience function)."""
    obs = get_observability()
    if obs:
        return obs.trace_operation(operation_name, **attributes)
    else:
        # Return a no-op context manager
        from contextlib import nullcontext
        return nullcontext()


def record_request(method: str, endpoint: str, status_code: int, duration: float):
    """Record request metrics (convenience function)."""
    obs = get_observability()
    if obs:
        obs.record_request(method, endpoint, status_code, duration)


def record_cost(cost_brl: float, operation: str = "llm_call"):
    """Record cost metrics (convenience function)."""
    obs = get_observability()
    if obs:
        obs.record_cost(cost_brl, operation)


def record_llm_tokens(prompt_tokens: int, completion_tokens: int, model: str = "gpt-4"):
    """Record LLM token usage (convenience function)."""
    obs = get_observability()
    if obs:
        obs.record_llm_tokens(prompt_tokens, completion_tokens, model)