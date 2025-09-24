"""
Auto-scaling preparedness for FamaGPT Orchestrator.
Provides HPA-ready metrics and Kubernetes scaling support.
"""
import asyncio
import time
import psutil
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import json

from shared.src.utils.logging import get_logger

logger = get_logger(__name__)


class ScalingTrigger(Enum):
    """Types of scaling triggers."""
    CPU_UTILIZATION = "cpu"
    MEMORY_UTILIZATION = "memory"
    REQUEST_RATE = "request_rate"
    QUEUE_DEPTH = "queue_depth"
    RESPONSE_TIME = "response_time"
    COST_EFFICIENCY = "cost_efficiency"
    BUSINESS_HOURS = "business_hours"


@dataclass
class ScalingMetrics:
    """Metrics for auto-scaling decisions."""
    timestamp: float

    # Resource metrics
    cpu_utilization_percent: float
    memory_utilization_percent: float
    memory_usage_mb: float

    # Performance metrics
    request_rate_rpm: float
    avg_response_time_ms: float
    p95_response_time_ms: float
    error_rate_percent: float

    # Business metrics
    active_corretores: int
    messages_per_minute: float
    cost_per_minute_brl: float

    # Queue metrics
    redis_queue_depth: int
    pending_workflows: int

    # Scaling recommendations
    recommended_replicas: int
    scaling_reason: str
    confidence_score: float  # 0-1


@dataclass
class ScalingConfig:
    """Configuration for auto-scaling behavior."""

    # HPA-style thresholds
    target_cpu_utilization: float = 70.0        # %
    target_memory_utilization: float = 80.0     # %
    target_request_rate: float = 80.0            # RPM per replica
    target_response_time_p95: float = 2000.0     # ms

    # Business thresholds
    max_corretores_per_replica: int = 50
    target_cost_efficiency_brl_per_msg: float = 0.30

    # Scaling behavior
    min_replicas: int = 2
    max_replicas: int = 20
    scale_up_threshold: float = 0.8    # Scale up at 80% of target
    scale_down_threshold: float = 0.4  # Scale down at 40% of target

    # Time windows
    scale_up_cooldown_seconds: int = 300    # 5 minutes
    scale_down_cooldown_seconds: int = 600  # 10 minutes
    metrics_window_seconds: int = 300       # 5 minute window

    # Business hours scaling
    business_hours_start: int = 8   # 8 AM
    business_hours_end: int = 18    # 6 PM
    business_hours_min_replicas: int = 3
    off_hours_min_replicas: int = 1


class AutoScalingManager:
    """Manages auto-scaling metrics and recommendations."""

    def __init__(self, config: ScalingConfig):
        self.config = config
        self.current_replicas = 1
        self.last_scale_time = 0.0
        self.metrics_history: List[ScalingMetrics] = []
        self.redis_client = None

        # Performance tracking
        self._request_count = 0
        self._total_response_time = 0.0
        self._response_times = []
        self._error_count = 0
        self._cost_total = 0.0

    async def collect_metrics(self) -> ScalingMetrics:
        """Collect comprehensive scaling metrics."""
        timestamp = time.time()

        # System resource metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_mb = memory.used / 1024 / 1024

        # Performance metrics
        request_rate = self._calculate_request_rate()
        avg_response_time = self._calculate_avg_response_time()
        p95_response_time = self._calculate_p95_response_time()
        error_rate = self._calculate_error_rate()

        # Business metrics
        active_corretores = await self._get_active_corretores()
        messages_per_minute = await self._get_messages_per_minute()
        cost_per_minute = self._calculate_cost_per_minute()

        # Queue metrics
        queue_depth = await self._get_queue_depth()
        pending_workflows = await self._get_pending_workflows()

        # Calculate scaling recommendation
        recommended_replicas, reason, confidence = self._calculate_scaling_recommendation(
            cpu_percent, memory_percent, request_rate, p95_response_time,
            active_corretores, queue_depth
        )

        metrics = ScalingMetrics(
            timestamp=timestamp,
            cpu_utilization_percent=cpu_percent,
            memory_utilization_percent=memory_percent,
            memory_usage_mb=memory_mb,
            request_rate_rpm=request_rate,
            avg_response_time_ms=avg_response_time,
            p95_response_time_ms=p95_response_time,
            error_rate_percent=error_rate,
            active_corretores=active_corretores,
            messages_per_minute=messages_per_minute,
            cost_per_minute_brl=cost_per_minute,
            redis_queue_depth=queue_depth,
            pending_workflows=pending_workflows,
            recommended_replicas=recommended_replicas,
            scaling_reason=reason,
            confidence_score=confidence
        )

        # Store metrics
        self.metrics_history.append(metrics)

        # Keep only recent metrics (within window)
        cutoff_time = timestamp - self.config.metrics_window_seconds
        self.metrics_history = [
            m for m in self.metrics_history
            if m.timestamp > cutoff_time
        ]

        logger.info("Scaling metrics collected",
                   cpu=cpu_percent,
                   memory=memory_percent,
                   request_rate=request_rate,
                   recommended_replicas=recommended_replicas,
                   reason=reason)

        return metrics

    def _calculate_request_rate(self) -> float:
        """Calculate current request rate (RPM)."""
        if not self.metrics_history:
            return 0.0

        # Calculate requests in last minute
        current_time = time.time()
        one_minute_ago = current_time - 60

        recent_requests = sum(
            1 for m in self.metrics_history
            if m.timestamp > one_minute_ago
        )

        return float(recent_requests)

    def _calculate_avg_response_time(self) -> float:
        """Calculate average response time."""
        if not self._response_times:
            return 0.0
        return sum(self._response_times) / len(self._response_times)

    def _calculate_p95_response_time(self) -> float:
        """Calculate P95 response time."""
        if not self._response_times:
            return 0.0
        sorted_times = sorted(self._response_times)
        p95_index = int(0.95 * len(sorted_times))
        return sorted_times[p95_index] if p95_index < len(sorted_times) else sorted_times[-1]

    def _calculate_error_rate(self) -> float:
        """Calculate error rate percentage."""
        total_requests = self._request_count + self._error_count
        if total_requests == 0:
            return 0.0
        return (self._error_count / total_requests) * 100

    def _calculate_cost_per_minute(self) -> float:
        """Calculate cost per minute in BRL."""
        if not self.metrics_history:
            return 0.0

        # Calculate cost in last minute
        current_time = time.time()
        one_minute_ago = current_time - 60

        recent_cost = sum(
            getattr(m, 'cost_delta', 0.0) for m in self.metrics_history
            if m.timestamp > one_minute_ago
        )

        return recent_cost

    async def _get_active_corretores(self) -> int:
        """Get number of active corretores."""
        # This would integrate with memory service to get active users
        # For now, simulate based on request rate
        request_rate = self._calculate_request_rate()
        # Assume each corretor makes ~2 requests per minute when active
        estimated_corretores = max(1, int(request_rate / 2))
        return min(estimated_corretores, 300)  # Cap at max expected

    async def _get_messages_per_minute(self) -> float:
        """Get WhatsApp messages per minute."""
        # This would integrate with webhooks service
        # For now, correlate with request rate
        return self._calculate_request_rate() * 0.8  # ~80% of requests are messages

    async def _get_queue_depth(self) -> int:
        """Get Redis queue depth."""
        if not self.redis_client:
            return 0

        try:
            # Check various Redis queues
            queue_keys = [
                "messages:stream",
                "workflows:pending",
                "tasks:queue"
            ]

            total_depth = 0
            for key in queue_keys:
                length = await self.redis_client.llen(key)
                total_depth += length

            return total_depth

        except Exception as e:
            logger.warning("Failed to get queue depth", error=str(e))
            return 0

    async def _get_pending_workflows(self) -> int:
        """Get number of pending workflows."""
        # This would integrate with orchestrator workflow repository
        # For now, estimate based on queue depth
        queue_depth = await self._get_queue_depth()
        return max(0, queue_depth - 10)  # Subtract baseline queue

    def _calculate_scaling_recommendation(
        self,
        cpu_percent: float,
        memory_percent: float,
        request_rate: float,
        p95_response_time: float,
        active_corretores: int,
        queue_depth: int
    ) -> tuple[int, str, float]:
        """Calculate scaling recommendation."""

        current_time = time.time()

        # Check cooldown periods
        time_since_last_scale = current_time - self.last_scale_time

        scale_up_reasons = []
        scale_down_reasons = []
        confidence_factors = []

        # CPU-based scaling
        if cpu_percent > self.config.target_cpu_utilization * self.config.scale_up_threshold:
            scale_up_reasons.append(f"CPU {cpu_percent:.1f}% > {self.config.target_cpu_utilization * self.config.scale_up_threshold:.1f}%")
            confidence_factors.append(0.9)
        elif cpu_percent < self.config.target_cpu_utilization * self.config.scale_down_threshold:
            scale_down_reasons.append(f"CPU {cpu_percent:.1f}% < {self.config.target_cpu_utilization * self.config.scale_down_threshold:.1f}%")
            confidence_factors.append(0.7)

        # Memory-based scaling
        if memory_percent > self.config.target_memory_utilization * self.config.scale_up_threshold:
            scale_up_reasons.append(f"Memory {memory_percent:.1f}% > {self.config.target_memory_utilization * self.config.scale_up_threshold:.1f}%")
            confidence_factors.append(0.8)
        elif memory_percent < self.config.target_memory_utilization * self.config.scale_down_threshold:
            scale_down_reasons.append(f"Memory {memory_percent:.1f}% < {self.config.target_memory_utilization * self.config.scale_down_threshold:.1f}%")
            confidence_factors.append(0.6)

        # Request rate-based scaling
        target_rps_per_replica = self.config.target_request_rate
        current_rps_per_replica = request_rate / max(1, self.current_replicas)

        if current_rps_per_replica > target_rps_per_replica * self.config.scale_up_threshold:
            scale_up_reasons.append(f"RPS/replica {current_rps_per_replica:.1f} > {target_rps_per_replica * self.config.scale_up_threshold:.1f}")
            confidence_factors.append(0.9)
        elif current_rps_per_replica < target_rps_per_replica * self.config.scale_down_threshold:
            scale_down_reasons.append(f"RPS/replica {current_rps_per_replica:.1f} < {target_rps_per_replica * self.config.scale_down_threshold:.1f}")
            confidence_factors.append(0.8)

        # Response time-based scaling
        if p95_response_time > self.config.target_response_time_p95:
            scale_up_reasons.append(f"P95 response time {p95_response_time:.0f}ms > {self.config.target_response_time_p95:.0f}ms")
            confidence_factors.append(0.8)

        # Business load-based scaling
        corretores_per_replica = active_corretores / max(1, self.current_replicas)
        if corretores_per_replica > self.config.max_corretores_per_replica:
            scale_up_reasons.append(f"Corretores/replica {corretores_per_replica:.1f} > {self.config.max_corretores_per_replica}")
            confidence_factors.append(0.7)

        # Queue depth-based scaling
        if queue_depth > 50:  # High queue depth
            scale_up_reasons.append(f"Queue depth {queue_depth} > 50")
            confidence_factors.append(0.6)

        # Business hours consideration
        current_hour = int(time.strftime('%H'))
        is_business_hours = self.config.business_hours_start <= current_hour < self.config.business_hours_end

        min_replicas = (self.config.business_hours_min_replicas if is_business_hours
                       else self.config.off_hours_min_replicas)

        # Determine recommendation
        if scale_up_reasons and time_since_last_scale > self.config.scale_up_cooldown_seconds:
            recommended_replicas = min(self.current_replicas + 1, self.config.max_replicas)
            reason = f"Scale up: {'; '.join(scale_up_reasons)}"
            confidence = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5

        elif scale_down_reasons and time_since_last_scale > self.config.scale_down_cooldown_seconds:
            recommended_replicas = max(self.current_replicas - 1, min_replicas)
            reason = f"Scale down: {'; '.join(scale_down_reasons)}"
            confidence = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5

        else:
            recommended_replicas = max(self.current_replicas, min_replicas)
            if time_since_last_scale <= max(self.config.scale_up_cooldown_seconds, self.config.scale_down_cooldown_seconds):
                reason = f"Cooldown active ({int(time_since_last_scale)}s)"
            else:
                reason = "Stable"
            confidence = 0.9

        return recommended_replicas, reason, confidence

    def record_request(self, response_time_ms: float, success: bool = True):
        """Record request metrics for scaling calculations."""
        self._request_count += 1
        self._response_times.append(response_time_ms)

        if not success:
            self._error_count += 1

        # Keep only recent response times (last 1000 requests)
        if len(self._response_times) > 1000:
            self._response_times = self._response_times[-1000:]

    def record_cost(self, cost_brl: float):
        """Record cost for scaling calculations."""
        self._cost_total += cost_brl

    def get_hpa_metrics(self) -> Dict[str, Any]:
        """Get metrics in Horizontal Pod Autoscaler format."""
        if not self.metrics_history:
            return {}

        latest = self.metrics_history[-1]

        return {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "name": "famagpt-orchestrator-hpa",
                "namespace": "default"
            },
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": "famagpt-orchestrator"
                },
                "minReplicas": self.config.min_replicas,
                "maxReplicas": self.config.max_replicas,
                "metrics": [
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": int(self.config.target_cpu_utilization)
                            }
                        }
                    },
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "memory",
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": int(self.config.target_memory_utilization)
                            }
                        }
                    },
                    {
                        "type": "Pods",
                        "pods": {
                            "metric": {
                                "name": "requests_per_minute"
                            },
                            "target": {
                                "type": "AverageValue",
                                "averageValue": str(int(self.config.target_request_rate))
                            }
                        }
                    }
                ]
            },
            "status": {
                "currentReplicas": self.current_replicas,
                "desiredReplicas": latest.recommended_replicas,
                "currentMetrics": [
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "current": {
                                "averageUtilization": int(latest.cpu_utilization_percent)
                            }
                        }
                    },
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "memory",
                            "current": {
                                "averageUtilization": int(latest.memory_utilization_percent)
                            }
                        }
                    }
                ]
            }
        }

    def get_scaling_dashboard_data(self) -> Dict[str, Any]:
        """Get data for scaling dashboard."""
        if not self.metrics_history:
            return {"status": "no_data"}

        latest = self.metrics_history[-1]

        # Calculate trends
        if len(self.metrics_history) >= 2:
            previous = self.metrics_history[-2]
            cpu_trend = latest.cpu_utilization_percent - previous.cpu_utilization_percent
            memory_trend = latest.memory_utilization_percent - previous.memory_utilization_percent
            request_trend = latest.request_rate_rpm - previous.request_rate_rpm
        else:
            cpu_trend = memory_trend = request_trend = 0.0

        return {
            "timestamp": latest.timestamp,
            "current_state": {
                "replicas": self.current_replicas,
                "recommended_replicas": latest.recommended_replicas,
                "scaling_reason": latest.scaling_reason,
                "confidence": latest.confidence_score
            },
            "resource_utilization": {
                "cpu_percent": latest.cpu_utilization_percent,
                "cpu_trend": cpu_trend,
                "memory_percent": latest.memory_utilization_percent,
                "memory_trend": memory_trend,
                "memory_mb": latest.memory_usage_mb
            },
            "performance_metrics": {
                "request_rate_rpm": latest.request_rate_rpm,
                "request_trend": request_trend,
                "avg_response_time_ms": latest.avg_response_time_ms,
                "p95_response_time_ms": latest.p95_response_time_ms,
                "error_rate_percent": latest.error_rate_percent
            },
            "business_metrics": {
                "active_corretores": latest.active_corretores,
                "messages_per_minute": latest.messages_per_minute,
                "cost_per_minute_brl": latest.cost_per_minute_brl
            },
            "scaling_config": asdict(self.config),
            "scaling_status": {
                "scale_up_threshold": self.config.scale_up_threshold,
                "scale_down_threshold": self.config.scale_down_threshold,
                "time_since_last_scale": time.time() - self.last_scale_time,
                "scale_up_cooldown": self.config.scale_up_cooldown_seconds,
                "scale_down_cooldown": self.config.scale_down_cooldown_seconds
            }
        }


# Global auto-scaling manager
_autoscaling_manager: Optional[AutoScalingManager] = None


def get_autoscaling_manager() -> Optional[AutoScalingManager]:
    """Get the global auto-scaling manager."""
    return _autoscaling_manager


def initialize_autoscaling(config: Optional[ScalingConfig] = None) -> AutoScalingManager:
    """Initialize global auto-scaling manager."""
    global _autoscaling_manager

    if config is None:
        config = ScalingConfig()

    _autoscaling_manager = AutoScalingManager(config)

    logger.info("Auto-scaling manager initialized",
               min_replicas=config.min_replicas,
               max_replicas=config.max_replicas,
               target_cpu=config.target_cpu_utilization)

    return _autoscaling_manager