
"""
Distributed Tracing Tool for GODMODESCANNER
Tracks requests across 47+ agents using OpenTelemetry and Jaeger

Usage:
    from agentzero.tools.godmode.observability_tool import DistributedTracing, tracer

    # In your agent code:
    with tracer.start_as_current_span("transaction_analysis") as span:
        span.set_attribute("wallet.address", wallet_address)
        span.set_attribute("system", "godmodescanner")
        # Your code here

Features:
- End-to-end tracing across 47+ agents
- Automatic Redis and PostgreSQL instrumentation
- Jaeger UI for visualization (http://localhost:16686)
- Performance monitoring and bottleneck detection
"""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
import os
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Configuration from environment variables
JAEGER_HOST = os.getenv("JAEGER_HOST", "localhost")
JAEGER_PORT = int(os.getenv("JAEGER_PORT", "6831"))
SERVICE_NAME = os.getenv("SERVICE_NAME", "godmodescanner")

# Initialize tracing
trace.set_tracer_provider(TracerProvider())
jaeger_exporter = JaegerExporter(
    agent_host_name=JAEGER_HOST,
    agent_port=JAEGER_PORT,
)
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)

# Auto-instrument Redis and Postgres
try:
    RedisInstrumentor().instrument()
    logger.info("Redis instrumentation enabled")
except Exception as e:
    logger.warning(f"Redis instrumentation failed: {e}")

try:
    AsyncPGInstrumentor().instrument()
    logger.info("AsyncPG instrumentation enabled")
except Exception as e:
    logger.warning(f"AsyncPG instrumentation failed: {e}")

tracer = trace.get_tracer(__name__)


class DistributedTracing:
    """
    Add to your agents for end-to-end tracing across the GODMODESCANNER pipeline.

    Example:
        # In transaction_monitor.py
        from agentzero.tools.godmode.observability_tool import DistributedTracing

        dt = DistributedTracing()
        result = dt.trace_transaction_analysis(
            wallet_address="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
            transaction_signature="5xyz..."
        )
    """

    def __init__(self, service_name: str = SERVICE_NAME):
        self.service_name = service_name
        self.tracer = trace.get_tracer(service_name)

    def trace_transaction_analysis(
        self,
        wallet_address: str,
        transaction_signature: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Trace a transaction through the entire pipeline:
        Transaction Monitor -> Wallet Analyzer -> Pattern Recognition 
        -> Risk Scoring -> Alert Manager

        Args:
            wallet_address: Solana wallet address
            transaction_signature: Transaction signature (optional)
            **kwargs: Additional attributes to add to the span

        Returns:
            Dict with tracing metadata and results
        """
        with self.tracer.start_as_current_span("transaction_analysis") as span:
            # Set standard attributes
            span.set_attribute("wallet.address", wallet_address)
            span.set_attribute("system", "godmodescanner")
            span.set_attribute("service.name", self.service_name)

            if transaction_signature:
                span.set_attribute("transaction.signature", transaction_signature)

            # Add custom attributes
            for key, value in kwargs.items():
                span.set_attribute(f"custom.{key}", str(value))

            # Get trace context for propagation
            trace_context = {
                "trace_id": format(span.get_span_context().trace_id, '032x'),
                "span_id": format(span.get_span_context().span_id, '016x'),
            }

            logger.info(
                f"Started trace for wallet {wallet_address}",
                extra=trace_context
            )

            return trace_context

    def trace_wallet_analysis(
        self,
        wallet_address: str,
        analysis_type: str = "full",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Trace wallet analysis operations.

        Args:
            wallet_address: Solana wallet address
            analysis_type: Type of analysis (full, quick, deep)
            **kwargs: Additional attributes

        Returns:
            Dict with tracing metadata
        """
        with self.tracer.start_as_current_span("wallet_analysis") as span:
            span.set_attribute("wallet.address", wallet_address)
            span.set_attribute("analysis.type", analysis_type)
            span.set_attribute("system", "godmodescanner")

            for key, value in kwargs.items():
                span.set_attribute(f"custom.{key}", str(value))

            trace_context = {
                "trace_id": format(span.get_span_context().trace_id, '032x'),
                "span_id": format(span.get_span_context().span_id, '016x'),
            }

            return trace_context

    def trace_pattern_detection(
        self,
        pattern_type: str,
        wallet_address: str,
        confidence: float,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Trace pattern detection operations.

        Args:
            pattern_type: Type of pattern (dev_insider, sybil_army, etc.)
            wallet_address: Wallet being analyzed
            confidence: Detection confidence (0-1)
            **kwargs: Additional attributes

        Returns:
            Dict with tracing metadata
        """
        with self.tracer.start_as_current_span("pattern_detection") as span:
            span.set_attribute("pattern.type", pattern_type)
            span.set_attribute("wallet.address", wallet_address)
            span.set_attribute("detection.confidence", confidence)
            span.set_attribute("system", "godmodescanner")

            # Mark high-confidence detections
            if confidence >= 0.80:
                span.set_attribute("detection.high_confidence", True)

            for key, value in kwargs.items():
                span.set_attribute(f"custom.{key}", str(value))

            trace_context = {
                "trace_id": format(span.get_span_context().trace_id, '032x'),
                "span_id": format(span.get_span_context().span_id, '016x'),
            }

            return trace_context

    def trace_risk_scoring(
        self,
        wallet_address: str,
        risk_score: float,
        alert_level: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Trace risk scoring operations.

        Args:
            wallet_address: Wallet being scored
            risk_score: Risk score (0-100)
            alert_level: Alert level (CRITICAL, HIGH, MEDIUM, LOW)
            **kwargs: Additional attributes

        Returns:
            Dict with tracing metadata
        """
        with self.tracer.start_as_current_span("risk_scoring") as span:
            span.set_attribute("wallet.address", wallet_address)
            span.set_attribute("risk.score", risk_score)
            span.set_attribute("alert.level", alert_level)
            span.set_attribute("system", "godmodescanner")

            # Mark critical alerts
            if alert_level == "CRITICAL":
                span.set_attribute("alert.critical", True)

            for key, value in kwargs.items():
                span.set_attribute(f"custom.{key}", str(value))

            trace_context = {
                "trace_id": format(span.get_span_context().trace_id, '032x'),
                "span_id": format(span.get_span_context().span_id, '016x'),
            }

            return trace_context

    def trace_graph_traversal(
        self,
        start_wallet: str,
        depth: int,
        nodes_discovered: int,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Trace graph traversal operations.

        Args:
            start_wallet: Starting wallet address
            depth: Traversal depth (hops)
            nodes_discovered: Number of nodes discovered
            **kwargs: Additional attributes

        Returns:
            Dict with tracing metadata
        """
        with self.tracer.start_as_current_span("graph_traversal") as span:
            span.set_attribute("graph.start_wallet", start_wallet)
            span.set_attribute("graph.depth", depth)
            span.set_attribute("graph.nodes_discovered", nodes_discovered)
            span.set_attribute("system", "godmodescanner")

            for key, value in kwargs.items():
                span.set_attribute(f"custom.{key}", str(value))

            trace_context = {
                "trace_id": format(span.get_span_context().trace_id, '032x'),
                "span_id": format(span.get_span_context().span_id, '016x'),
            }

            return trace_context


# Convenience function for quick tracing
def trace_operation(operation_name: str, **attributes):
    """
    Decorator for tracing any operation.

    Usage:
        @trace_operation("my_operation", custom_attr="value")
        def my_function():
            # Your code here
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(operation_name) as span:
                # Set attributes
                for key, value in attributes.items():
                    span.set_attribute(key, str(value))

                # Execute function
                result = func(*args, **kwargs)

                return result
        return wrapper
    return decorator


if __name__ == "__main__":
    # Example usage
    dt = DistributedTracing()

    # Trace a transaction analysis
    trace_ctx = dt.trace_transaction_analysis(
        wallet_address="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        transaction_signature="5xyz123...",
        token_address="pump123..."
    )

    print(f"Trace ID: {trace_ctx['trace_id']}")
    print(f"Span ID: {trace_ctx['span_id']}")
    print(f"View trace at: http://localhost:16686/trace/{trace_ctx['trace_id']}")
