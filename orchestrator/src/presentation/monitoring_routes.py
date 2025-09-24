"""
Enhanced monitoring and observability routes for FamaGPT Orchestrator.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional
import time
import asyncio

from ..infrastructure.observability import get_observability, trace_operation
from ..infrastructure.circuit_breaker import get_circuit_breaker_manager
from shared.src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/health/detailed")
async def detailed_health_check():
    """Enhanced health check with component status."""
    start_time = time.time()

    with trace_operation("health_check", check_type="detailed"):
        health_status = {
            "status": "healthy",
            "timestamp": int(time.time()),
            "service": "famagpt-orchestrator",
            "version": "1.0.0",
            "components": {},
            "infrastructure_hardening": {
                "rate_limiting": True,
                "observability": True,
                "circuit_breakers": True
            }
        }

        # Check observability
        obs = get_observability()
        if obs:
            health_status["components"]["observability"] = {
                "status": "healthy",
                "enabled": True,
                "tracing": True
            }
        else:
            health_status["components"]["observability"] = {
                "status": "disabled",
                "enabled": False
            }

        # Check circuit breakers
        try:
            cb_manager = get_circuit_breaker_manager()
            cb_stats = cb_manager.get_all_stats()

            health_status["components"]["circuit_breakers"] = {
                "status": "healthy",
                "total_breakers": len(cb_stats),
                "breakers": {
                    name: {
                        "state": stats["state"],
                        "is_available": stats["is_available"]
                    }
                    for name, stats in cb_stats.items()
                }
            }
        except Exception as e:
            health_status["components"]["circuit_breakers"] = {
                "status": "error",
                "error": str(e)
            }

        # Add response time
        health_status["response_time_ms"] = round((time.time() - start_time) * 1000, 2)

        # Determine overall status
        component_statuses = [
            comp.get("status", "unknown")
            for comp in health_status["components"].values()
        ]

        if any(status == "error" for status in component_statuses):
            health_status["status"] = "unhealthy"
        elif any(status == "degraded" for status in component_statuses):
            health_status["status"] = "degraded"

        return health_status


@router.get("/metrics/summary")
async def metrics_summary():
    """Get a summary of key system metrics."""
    with trace_operation("metrics_summary"):
        try:
            cb_manager = get_circuit_breaker_manager()
            cb_stats = cb_manager.get_all_stats()

            summary = {
                "timestamp": int(time.time()),
                "circuit_breakers": {
                    "total": len(cb_stats),
                    "healthy": len([s for s in cb_stats.values() if s["is_available"]]),
                    "unhealthy": len([s for s in cb_stats.values() if not s["is_available"]]),
                    "details": cb_stats
                },
                "observability": {
                    "enabled": get_observability() is not None,
                    "tracing_active": True
                }
            }

            return summary

        except Exception as e:
            logger.error("Failed to get metrics summary", error=str(e))
            raise HTTPException(status_code=500, detail=f"Metrics error: {str(e)}")


@router.get("/circuit-breakers")
async def get_circuit_breaker_status():
    """Get detailed circuit breaker status."""
    with trace_operation("circuit_breaker_status"):
        try:
            cb_manager = get_circuit_breaker_manager()
            return cb_manager.get_all_stats()

        except Exception as e:
            logger.error("Failed to get circuit breaker status", error=str(e))
            raise HTTPException(status_code=500, detail=f"Circuit breaker error: {str(e)}")


@router.post("/circuit-breakers/{service_name}/reset")
async def reset_circuit_breaker(service_name: str):
    """Reset a specific circuit breaker."""
    with trace_operation("reset_circuit_breaker", service_name=service_name):
        try:
            cb_manager = get_circuit_breaker_manager()
            cb_manager.reset_circuit_breaker(service_name)

            logger.info("Circuit breaker reset", service_name=service_name)

            return {
                "status": "success",
                "message": f"Circuit breaker '{service_name}' has been reset",
                "timestamp": int(time.time())
            }

        except Exception as e:
            logger.error("Failed to reset circuit breaker",
                        service_name=service_name, error=str(e))
            raise HTTPException(status_code=500, detail=f"Reset error: {str(e)}")


@router.get("/observability/trace-test")
async def test_tracing():
    """Test endpoint to verify distributed tracing is working."""
    with trace_operation("trace_test", test_type="manual"):
        # Simulate some work
        await asyncio.sleep(0.1)

        # Test nested tracing
        with trace_operation("nested_operation", operation="database_call"):
            await asyncio.sleep(0.05)

        with trace_operation("nested_operation", operation="external_api_call"):
            await asyncio.sleep(0.02)

        return {
            "status": "success",
            "message": "Tracing test completed",
            "timestamp": int(time.time()),
            "tracing_enabled": get_observability() is not None
        }


@router.get("/performance/benchmark")
async def performance_benchmark():
    """Run a quick performance benchmark."""
    with trace_operation("performance_benchmark"):
        start_time = time.time()

        # Test various operations
        results = {
            "timestamp": int(time.time()),
            "tests": {}
        }

        # Test 1: Basic operation speed
        test_start = time.time()
        for _ in range(1000):
            _ = {"test": "value", "number": 42}
        results["tests"]["basic_operations"] = {
            "duration_ms": round((time.time() - test_start) * 1000, 2),
            "operations": 1000
        }

        # Test 2: Async operation
        test_start = time.time()
        await asyncio.sleep(0.001)  # Minimal async operation
        results["tests"]["async_operation"] = {
            "duration_ms": round((time.time() - test_start) * 1000, 2)
        }

        # Test 3: Circuit breaker overhead
        test_start = time.time()
        try:
            cb_manager = get_circuit_breaker_manager()
            cb_stats = cb_manager.get_all_stats()
        except Exception:
            cb_stats = {}
        results["tests"]["circuit_breaker_overhead"] = {
            "duration_ms": round((time.time() - test_start) * 1000, 2),
            "breakers_checked": len(cb_stats)
        }

        # Overall benchmark time
        results["total_duration_ms"] = round((time.time() - start_time) * 1000, 2)

        return results


@router.get("/config/infrastructure")
async def get_infrastructure_config():
    """Get current infrastructure hardening configuration."""
    with trace_operation("get_infrastructure_config"):
        import os

        config = {
            "rate_limiting": {
                "enabled": os.environ.get("RATE_LIMIT_ENABLED", "true"),
                "rpm": os.environ.get("RATE_LIMIT_RPM", "100"),
                "cost_limit_brl": os.environ.get("COST_LIMIT_BRL_DAY", "500.0"),
                "burst": os.environ.get("RATE_LIMIT_BURST", "20")
            },
            "observability": {
                "enabled": os.environ.get("OTEL_ENABLED", "true"),
                "service_name": os.environ.get("OTEL_SERVICE_NAME", "famagpt-orchestrator"),
                "endpoint": os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
                "sample_rate": os.environ.get("OTEL_TRACE_SAMPLE_RATE", "0.1")
            },
            "langsmith": {
                "enabled": os.environ.get("LANGCHAIN_TRACING_V2", "true"),
                "project": os.environ.get("LANGCHAIN_PROJECT", "famagpt-orchestrator")
            }
        }

        return {
            "timestamp": int(time.time()),
            "infrastructure_hardening": config,
            "status": "active"
        }