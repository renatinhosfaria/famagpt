"""
Chaos Engineering and Fault Injection for FamaGPT.
Provides controlled failure testing to improve system resilience.
"""
import asyncio
import random
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import httpx

from shared.src.utils.logging import get_logger

logger = get_logger(__name__)


class ChaosType(Enum):
    """Types of chaos experiments."""
    LATENCY_INJECTION = "latency_injection"
    ERROR_INJECTION = "error_injection"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    NETWORK_PARTITION = "network_partition"
    SERVICE_UNAVAILABLE = "service_unavailable"
    DATA_CORRUPTION = "data_corruption"
    TIMEOUT_INJECTION = "timeout_injection"


@dataclass
class ChaosExperiment:
    """Definition of a chaos experiment."""
    name: str
    chaos_type: ChaosType
    target_service: str
    target_endpoint: Optional[str] = None

    # Experiment parameters
    failure_rate: float = 0.1          # 10% of requests affected
    duration_seconds: int = 300        # 5 minutes
    intensity: float = 1.0             # Intensity of the chaos (0-1)

    # Conditions
    enabled: bool = True
    schedule: Optional[str] = None     # Cron-like schedule
    prerequisites: List[str] = None    # Conditions that must be met

    # Safety measures
    max_error_rate: float = 0.2        # Abort if error rate exceeds 20%
    max_response_time_ms: float = 5000 # Abort if response time exceeds 5s
    rollback_on_alert: bool = True

    def __post_init__(self):
        if self.prerequisites is None:
            self.prerequisites = []


class ChaosEngineer:
    """Manages chaos engineering experiments."""

    def __init__(self):
        self.active_experiments: Dict[str, ChaosExperiment] = {}
        self.experiment_history: List[Dict[str, Any]] = []
        self.safety_monitors: Dict[str, Callable] = {}

        # Experiment catalog
        self.experiment_catalog = self._create_experiment_catalog()

        # State tracking
        self.baseline_metrics: Dict[str, float] = {}
        self.is_production_safe = True

    def _create_experiment_catalog(self) -> Dict[str, ChaosExperiment]:
        """Create catalog of predefined chaos experiments."""
        return {
            # Network and latency experiments
            "openai_latency_spike": ChaosExperiment(
                name="OpenAI API Latency Spike",
                chaos_type=ChaosType.LATENCY_INJECTION,
                target_service="openai_api",
                failure_rate=0.05,
                duration_seconds=180,
                intensity=0.5,  # Add 500ms-2s latency
                prerequisites=["low_traffic_period", "circuit_breakers_active"]
            ),

            "internal_service_timeout": ChaosExperiment(
                name="Internal Service Timeout",
                chaos_type=ChaosType.TIMEOUT_INJECTION,
                target_service="memory_service",
                target_endpoint="/api/v1/memory/store",
                failure_rate=0.1,
                duration_seconds=120,
                intensity=0.7,
                prerequisites=["circuit_breakers_active"]
            ),

            # Error injection experiments
            "database_connection_errors": ChaosExperiment(
                name="Database Connection Errors",
                chaos_type=ChaosType.ERROR_INJECTION,
                target_service="database_service",
                failure_rate=0.08,
                duration_seconds=300,
                intensity=0.4,
                prerequisites=["backup_systems_ready"]
            ),

            "rate_limit_breach": ChaosExperiment(
                name="Rate Limit Breach Simulation",
                chaos_type=ChaosType.ERROR_INJECTION,
                target_service="orchestrator",
                target_endpoint="/api/v1/workflows/execute",
                failure_rate=0.15,
                duration_seconds=240,
                intensity=0.6,
                prerequisites=["rate_limiting_active"]
            ),

            # Resource exhaustion experiments
            "memory_pressure": ChaosExperiment(
                name="Memory Pressure Test",
                chaos_type=ChaosType.RESOURCE_EXHAUSTION,
                target_service="orchestrator",
                failure_rate=1.0,  # Affects all instances
                duration_seconds=180,
                intensity=0.3,  # Consume 30% additional memory
                prerequisites=["auto_scaling_active", "monitoring_active"]
            ),

            # Service availability experiments
            "whatsapp_webhook_unavailable": ChaosExperiment(
                name="WhatsApp Webhook Unavailable",
                chaos_type=ChaosType.SERVICE_UNAVAILABLE,
                target_service="webhooks_service",
                failure_rate=1.0,
                duration_seconds=120,
                intensity=1.0,
                prerequisites=["message_queue_active", "retry_mechanisms_active"]
            ),

            # Network partition experiments
            "redis_network_partition": ChaosExperiment(
                name="Redis Network Partition",
                chaos_type=ChaosType.NETWORK_PARTITION,
                target_service="redis",
                failure_rate=1.0,
                duration_seconds=60,  # Short duration for critical service
                intensity=1.0,
                prerequisites=["redis_backup_active", "low_traffic_period"]
            )
        }

    async def run_experiment(self, experiment_name: str) -> Dict[str, Any]:
        """Run a chaos experiment."""
        if experiment_name not in self.experiment_catalog:
            raise ValueError(f"Experiment {experiment_name} not found")

        experiment = self.experiment_catalog[experiment_name]

        if not experiment.enabled:
            return {"status": "skipped", "reason": "experiment disabled"}

        # Check prerequisites
        if not await self._check_prerequisites(experiment):
            return {"status": "skipped", "reason": "prerequisites not met"}

        # Check safety conditions
        if not await self._check_safety_conditions():
            return {"status": "aborted", "reason": "safety conditions not met"}

        logger.info("Starting chaos experiment",
                   experiment=experiment_name,
                   target=experiment.target_service,
                   duration=experiment.duration_seconds)

        # Capture baseline metrics
        baseline = await self._capture_baseline_metrics()

        # Start the experiment
        experiment_id = f"{experiment_name}_{int(time.time())}"
        self.active_experiments[experiment_id] = experiment

        try:
            # Execute the chaos
            chaos_result = await self._execute_chaos(experiment)

            # Monitor during experiment
            monitoring_result = await self._monitor_experiment(experiment, baseline)

            # Stop the experiment
            await self._stop_experiment(experiment)

            # Analyze results
            analysis = await self._analyze_experiment_results(
                experiment, baseline, chaos_result, monitoring_result
            )

            result = {
                "experiment_id": experiment_id,
                "status": "completed",
                "baseline_metrics": baseline,
                "chaos_result": chaos_result,
                "monitoring_result": monitoring_result,
                "analysis": analysis,
                "duration_actual": monitoring_result.get("duration_seconds", 0)
            }

            # Store in history
            self.experiment_history.append(result)

            logger.info("Chaos experiment completed",
                       experiment=experiment_name,
                       status=result["status"],
                       impact=analysis.get("impact_level", "unknown"))

            return result

        except Exception as e:
            # Emergency rollback
            await self._emergency_rollback(experiment)

            logger.error("Chaos experiment failed",
                        experiment=experiment_name,
                        error=str(e))

            return {
                "experiment_id": experiment_id,
                "status": "failed",
                "error": str(e),
                "rollback_performed": True
            }

        finally:
            # Cleanup
            if experiment_id in self.active_experiments:
                del self.active_experiments[experiment_id]

    async def _check_prerequisites(self, experiment: ChaosExperiment) -> bool:
        """Check if experiment prerequisites are met."""
        for prerequisite in experiment.prerequisites:
            if not await self._check_prerequisite(prerequisite):
                logger.warning("Prerequisite not met",
                              prerequisite=prerequisite,
                              experiment=experiment.name)
                return False
        return True

    async def _check_prerequisite(self, prerequisite: str) -> bool:
        """Check a specific prerequisite."""
        checks = {
            "low_traffic_period": self._is_low_traffic_period,
            "circuit_breakers_active": self._are_circuit_breakers_active,
            "backup_systems_ready": self._are_backup_systems_ready,
            "rate_limiting_active": self._is_rate_limiting_active,
            "auto_scaling_active": self._is_auto_scaling_active,
            "monitoring_active": self._is_monitoring_active,
            "message_queue_active": self._is_message_queue_active,
            "retry_mechanisms_active": self._are_retry_mechanisms_active,
            "redis_backup_active": self._is_redis_backup_active
        }

        check_func = checks.get(prerequisite)
        if check_func:
            return await check_func()

        logger.warning("Unknown prerequisite", prerequisite=prerequisite)
        return False

    async def _is_low_traffic_period(self) -> bool:
        """Check if it's a low traffic period."""
        # Check current hour (assuming low traffic 2-6 AM Brazil time)
        current_hour = time.localtime().tm_hour
        return 2 <= current_hour <= 6

    async def _are_circuit_breakers_active(self) -> bool:
        """Check if circuit breakers are active."""
        try:
            from .circuit_breaker import get_circuit_breaker_manager
            cb_manager = get_circuit_breaker_manager()
            stats = cb_manager.get_all_stats()
            return len(stats) > 0  # At least some circuit breakers exist
        except Exception:
            return False

    async def _are_backup_systems_ready(self) -> bool:
        """Check if backup systems are ready."""
        # This would check actual backup system status
        # For now, assume they're ready if it's not peak hours
        return await self._is_low_traffic_period()

    async def _is_rate_limiting_active(self) -> bool:
        """Check if rate limiting is active."""
        import os
        return os.environ.get("RATE_LIMIT_ENABLED", "false").lower() == "true"

    async def _is_auto_scaling_active(self) -> bool:
        """Check if auto-scaling is active."""
        import os
        return os.environ.get("AUTOSCALING_ENABLED", "false").lower() == "true"

    async def _is_monitoring_active(self) -> bool:
        """Check if monitoring is active."""
        try:
            from .observability import get_observability
            return get_observability() is not None
        except Exception:
            return False

    async def _is_message_queue_active(self) -> bool:
        """Check if message queue is active."""
        # This would check Redis streams health
        return True  # Simplified

    async def _are_retry_mechanisms_active(self) -> bool:
        """Check if retry mechanisms are active."""
        # This would check if tenacity/retry decorators are working
        return True  # Simplified

    async def _is_redis_backup_active(self) -> bool:
        """Check if Redis backup is active."""
        # This would check Redis replication/backup status
        return True  # Simplified

    async def _check_safety_conditions(self) -> bool:
        """Check safety conditions before experiment."""
        # Check system health
        try:
            # Check error rate
            current_error_rate = await self._get_current_error_rate()
            if current_error_rate > 0.05:  # 5% baseline error rate
                logger.warning("Current error rate too high for chaos experiment",
                              error_rate=current_error_rate)
                return False

            # Check response time
            current_response_time = await self._get_current_response_time()
            if current_response_time > 3000:  # 3s baseline response time
                logger.warning("Current response time too high for chaos experiment",
                              response_time_ms=current_response_time)
                return False

            return True

        except Exception as e:
            logger.error("Failed to check safety conditions", error=str(e))
            return False

    async def _get_current_error_rate(self) -> float:
        """Get current system error rate."""
        # This would integrate with metrics system
        return 0.01  # 1% baseline

    async def _get_current_response_time(self) -> float:
        """Get current system response time."""
        # This would integrate with metrics system
        return 500.0  # 500ms baseline

    async def _capture_baseline_metrics(self) -> Dict[str, float]:
        """Capture baseline metrics before experiment."""
        metrics = {
            "error_rate": await self._get_current_error_rate(),
            "response_time_p95": await self._get_current_response_time(),
            "throughput_rps": await self._get_current_throughput(),
            "cpu_utilization": await self._get_cpu_utilization(),
            "memory_utilization": await self._get_memory_utilization(),
            "active_connections": await self._get_active_connections()
        }

        self.baseline_metrics = metrics
        logger.info("Baseline metrics captured", metrics=metrics)
        return metrics

    async def _get_current_throughput(self) -> float:
        """Get current throughput in requests per second."""
        return 50.0  # Baseline RPS

    async def _get_cpu_utilization(self) -> float:
        """Get current CPU utilization."""
        import psutil
        return psutil.cpu_percent(interval=1)

    async def _get_memory_utilization(self) -> float:
        """Get current memory utilization."""
        import psutil
        return psutil.virtual_memory().percent

    async def _get_active_connections(self) -> float:
        """Get current active connections."""
        return 100.0  # Baseline connections

    async def _execute_chaos(self, experiment: ChaosExperiment) -> Dict[str, Any]:
        """Execute the chaos experiment."""
        chaos_methods = {
            ChaosType.LATENCY_INJECTION: self._inject_latency,
            ChaosType.ERROR_INJECTION: self._inject_errors,
            ChaosType.RESOURCE_EXHAUSTION: self._exhaust_resources,
            ChaosType.NETWORK_PARTITION: self._partition_network,
            ChaosType.SERVICE_UNAVAILABLE: self._make_service_unavailable,
            ChaosType.TIMEOUT_INJECTION: self._inject_timeouts
        }

        chaos_method = chaos_methods.get(experiment.chaos_type)
        if not chaos_method:
            raise ValueError(f"Unknown chaos type: {experiment.chaos_type}")

        return await chaos_method(experiment)

    async def _inject_latency(self, experiment: ChaosExperiment) -> Dict[str, Any]:
        """Inject artificial latency."""
        base_delay = 500 * experiment.intensity  # 500ms base * intensity
        variation = base_delay * 0.5  # ±50% variation

        logger.info("Injecting latency",
                   target=experiment.target_service,
                   base_delay_ms=base_delay,
                   failure_rate=experiment.failure_rate)

        # This would integrate with service mesh or application code
        # to add delays to requests

        return {
            "type": "latency_injection",
            "base_delay_ms": base_delay,
            "variation_ms": variation,
            "affected_requests": 0  # Would be updated during execution
        }

    async def _inject_errors(self, experiment: ChaosExperiment) -> Dict[str, Any]:
        """Inject artificial errors."""
        error_types = ["503", "502", "timeout", "connection_refused"]
        selected_error = random.choice(error_types)

        logger.info("Injecting errors",
                   target=experiment.target_service,
                   error_type=selected_error,
                   failure_rate=experiment.failure_rate)

        return {
            "type": "error_injection",
            "error_type": selected_error,
            "injected_errors": 0  # Would be updated during execution
        }

    async def _exhaust_resources(self, experiment: ChaosExperiment) -> Dict[str, Any]:
        """Exhaust system resources."""
        resource_type = "memory"  # Could be CPU, memory, disk, etc.
        consumption_mb = 100 * experiment.intensity  # Base consumption

        logger.info("Exhausting resources",
                   target=experiment.target_service,
                   resource_type=resource_type,
                   consumption_mb=consumption_mb)

        # This would actually consume resources
        # For demo, we'll just log it

        return {
            "type": "resource_exhaustion",
            "resource_type": resource_type,
            "consumption_mb": consumption_mb
        }

    async def _partition_network(self, experiment: ChaosExperiment) -> Dict[str, Any]:
        """Simulate network partition."""
        logger.info("Simulating network partition",
                   target=experiment.target_service)

        # This would use tools like tc (traffic control) or iptables
        # to block network traffic

        return {
            "type": "network_partition",
            "blocked_connections": 0
        }

    async def _make_service_unavailable(self, experiment: ChaosExperiment) -> Dict[str, Any]:
        """Make service temporarily unavailable."""
        logger.info("Making service unavailable",
                   target=experiment.target_service)

        # This would stop the service or block its endpoints

        return {
            "type": "service_unavailable",
            "downtime_seconds": experiment.duration_seconds
        }

    async def _inject_timeouts(self, experiment: ChaosExperiment) -> Dict[str, Any]:
        """Inject artificial timeouts."""
        timeout_ms = 10000 * experiment.intensity  # Base timeout

        logger.info("Injecting timeouts",
                   target=experiment.target_service,
                   timeout_ms=timeout_ms,
                   failure_rate=experiment.failure_rate)

        return {
            "type": "timeout_injection",
            "timeout_ms": timeout_ms,
            "affected_requests": 0
        }

    async def _monitor_experiment(self, experiment: ChaosExperiment, baseline: Dict[str, float]) -> Dict[str, Any]:
        """Monitor experiment execution."""
        start_time = time.time()
        monitoring_data = []

        while time.time() - start_time < experiment.duration_seconds:
            # Collect metrics
            current_metrics = await self._capture_baseline_metrics()

            # Check safety thresholds
            error_rate = current_metrics.get("error_rate", 0)
            response_time = current_metrics.get("response_time_p95", 0)

            if error_rate > experiment.max_error_rate:
                logger.warning("Error rate threshold exceeded",
                              current=error_rate,
                              threshold=experiment.max_error_rate)
                if experiment.rollback_on_alert:
                    break

            if response_time > experiment.max_response_time_ms:
                logger.warning("Response time threshold exceeded",
                              current=response_time,
                              threshold=experiment.max_response_time_ms)
                if experiment.rollback_on_alert:
                    break

            monitoring_data.append({
                "timestamp": time.time(),
                "metrics": current_metrics
            })

            await asyncio.sleep(10)  # Monitor every 10 seconds

        duration = time.time() - start_time

        return {
            "duration_seconds": duration,
            "monitoring_data": monitoring_data,
            "early_termination": duration < experiment.duration_seconds
        }

    async def _stop_experiment(self, experiment: ChaosExperiment):
        """Stop the chaos experiment."""
        logger.info("Stopping chaos experiment", target=experiment.target_service)

        # This would reverse the chaos injection
        # For now, just log it

    async def _emergency_rollback(self, experiment: ChaosExperiment):
        """Perform emergency rollback."""
        logger.critical("Performing emergency rollback", target=experiment.target_service)

        # This would immediately stop all chaos and restore normal operation

    async def _analyze_experiment_results(self, experiment: ChaosExperiment, baseline: Dict[str, float],
                                        chaos_result: Dict[str, Any], monitoring_result: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze experiment results."""
        monitoring_data = monitoring_result.get("monitoring_data", [])

        if not monitoring_data:
            return {"impact_level": "unknown", "analysis": "No monitoring data available"}

        # Calculate impact
        final_metrics = monitoring_data[-1]["metrics"]

        impact_scores = {}
        for metric, baseline_value in baseline.items():
            current_value = final_metrics.get(metric, baseline_value)

            if metric in ["error_rate"]:
                # Higher is worse
                impact = (current_value - baseline_value) / baseline_value if baseline_value > 0 else 0
            elif metric in ["response_time_p95"]:
                # Higher is worse
                impact = (current_value - baseline_value) / baseline_value if baseline_value > 0 else 0
            elif metric in ["throughput_rps"]:
                # Lower is worse
                impact = (baseline_value - current_value) / baseline_value if baseline_value > 0 else 0
            else:
                # Neutral
                impact = abs(current_value - baseline_value) / baseline_value if baseline_value > 0 else 0

            impact_scores[metric] = impact

        # Overall impact level
        avg_impact = sum(impact_scores.values()) / len(impact_scores)

        if avg_impact < 0.1:
            impact_level = "minimal"
        elif avg_impact < 0.3:
            impact_level = "moderate"
        elif avg_impact < 0.5:
            impact_level = "significant"
        else:
            impact_level = "severe"

        # Generate insights
        insights = []

        if impact_scores.get("error_rate", 0) > 0.2:
            insights.append("System showed poor error handling under chaos")

        if impact_scores.get("response_time_p95", 0) > 0.3:
            insights.append("Response time significantly degraded")

        if impact_scores.get("throughput_rps", 0) > 0.2:
            insights.append("Throughput noticeably reduced")

        if monitoring_result.get("early_termination", False):
            insights.append("Experiment terminated early due to safety thresholds")

        if not insights:
            insights.append("System demonstrated good resilience to chaos")

        return {
            "impact_level": impact_level,
            "impact_scores": impact_scores,
            "insights": insights,
            "recommendations": self._generate_chaos_recommendations(impact_scores, insights)
        }

    def _generate_chaos_recommendations(self, impact_scores: Dict[str, float], insights: List[str]) -> List[str]:
        """Generate recommendations based on chaos experiment results."""
        recommendations = []

        if impact_scores.get("error_rate", 0) > 0.3:
            recommendations.append("Improve error handling and circuit breaker configuration")

        if impact_scores.get("response_time_p95", 0) > 0.4:
            recommendations.append("Optimize application performance and add caching")

        if impact_scores.get("throughput_rps", 0) > 0.3:
            recommendations.append("Review auto-scaling policies and resource allocation")

        if "early_termination" in " ".join(insights):
            recommendations.append("Safety thresholds may be too conservative, review alerting")

        if not recommendations:
            recommendations.append("System performed well, consider increasing chaos intensity")

        return recommendations

    def get_experiment_report(self, experiment_id: Optional[str] = None) -> Dict[str, Any]:
        """Get experiment report."""
        if experiment_id:
            # Find specific experiment
            for result in self.experiment_history:
                if result.get("experiment_id") == experiment_id:
                    return result
            return {"error": "Experiment not found"}

        else:
            # Return summary of all experiments
            total_experiments = len(self.experiment_history)
            successful_experiments = len([r for r in self.experiment_history if r.get("status") == "completed"])

            impact_levels = [r.get("analysis", {}).get("impact_level", "unknown") for r in self.experiment_history]
            impact_summary = {level: impact_levels.count(level) for level in set(impact_levels)}

            return {
                "total_experiments": total_experiments,
                "successful_experiments": successful_experiments,
                "success_rate": (successful_experiments / total_experiments * 100) if total_experiments > 0 else 0,
                "impact_summary": impact_summary,
                "recent_experiments": self.experiment_history[-5:],  # Last 5 experiments
                "available_experiments": list(self.experiment_catalog.keys())
            }


# Global chaos engineer instance
_chaos_engineer: Optional[ChaosEngineer] = None


def get_chaos_engineer() -> ChaosEngineer:
    """Get the global chaos engineer."""
    global _chaos_engineer

    if _chaos_engineer is None:
        _chaos_engineer = ChaosEngineer()

    return _chaos_engineer