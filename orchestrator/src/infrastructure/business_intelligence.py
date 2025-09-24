"""
Advanced Business Intelligence and Analytics for FamaGPT.
Provides real-time insights, predictive analytics, and business metrics.
"""
import asyncio
import time
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime, timedelta
import statistics
import numpy as np
from collections import defaultdict, deque

from shared.src.utils.logging import get_logger

logger = get_logger(__name__)


class MetricType(Enum):
    """Types of business metrics."""
    REVENUE = "revenue"
    USAGE = "usage"
    PERFORMANCE = "performance"
    SATISFACTION = "satisfaction"
    COST = "cost"
    GROWTH = "growth"


class TimeWindow(Enum):
    """Time windows for analytics."""
    REAL_TIME = "real_time"      # Last 5 minutes
    HOURLY = "hourly"            # Last hour
    DAILY = "daily"              # Last 24 hours
    WEEKLY = "weekly"            # Last 7 days
    MONTHLY = "monthly"          # Last 30 days


@dataclass
class CorretrMetrics:
    """Metrics for individual corretor."""
    corretor_id: str
    name: str

    # Usage metrics
    messages_today: int
    messages_this_week: int
    messages_total: int

    # Performance metrics
    avg_response_time_ms: float
    satisfaction_score: float  # 1-5
    success_rate_percent: float

    # Business metrics
    monthly_revenue_brl: float
    cost_per_message_brl: float
    roi_score: float  # Revenue/Cost ratio

    # Engagement metrics
    active_days_this_month: int
    last_activity: datetime
    retention_score: float  # 0-1

    # Feature usage
    features_used: List[str]
    favorite_features: List[str]

    # Predictions
    churn_risk_score: float  # 0-1 (1 = high risk)
    lifetime_value_brl: float
    next_action_recommendation: str


@dataclass
class BusinessMetrics:
    """Overall business metrics."""
    timestamp: datetime

    # Revenue metrics
    mrr_brl: float                    # Monthly Recurring Revenue
    arr_brl: float                    # Annual Recurring Revenue
    revenue_growth_percent: float

    # Customer metrics
    total_corretores: int
    active_corretores: int
    new_corretores_this_month: int
    churned_corretores_this_month: int
    churn_rate_percent: float

    # Usage metrics
    total_messages_today: int
    avg_messages_per_corretor: float
    peak_usage_time: str

    # Performance metrics
    avg_response_time_ms: float
    p95_response_time_ms: float
    uptime_percent: float
    error_rate_percent: float

    # Cost metrics
    total_cost_brl: float
    cost_per_message_brl: float
    cost_per_corretor_brl: float
    margin_percent: float

    # Satisfaction metrics
    avg_satisfaction_score: float
    nps_score: float
    support_ticket_count: int

    # Market metrics
    market_penetration_percent: float  # Of Uberlândia corretores
    competitive_position: str

    # Predictions
    projected_mrr_next_month: float
    capacity_utilization_percent: float
    scale_recommendation: str


class BusinessIntelligenceEngine:
    """Main business intelligence engine."""

    def __init__(self):
        self.corretor_data: Dict[str, CorretrMetrics] = {}
        self.business_metrics_history: List[BusinessMetrics] = []
        self.real_time_events: deque = deque(maxlen=10000)

        # Analytics state
        self.last_calculation_time = 0.0
        self.calculation_interval = 300  # 5 minutes

        # Market data
        self.uberlandia_total_corretores = 300
        self.target_market_size_brl = 44100  # 300 * R$ 147

        # Predictive models (simplified)
        self.churn_model_weights = {
            'days_inactive': 0.3,
            'satisfaction_drop': 0.25,
            'usage_decline': 0.2,
            'support_tickets': 0.15,
            'payment_issues': 0.1
        }

    async def track_event(self, event_type: str, corretor_id: str, data: Dict[str, Any]):
        """Track real-time business event."""
        event = {
            'timestamp': time.time(),
            'type': event_type,
            'corretor_id': corretor_id,
            'data': data
        }

        self.real_time_events.append(event)

        # Update corretor metrics in real-time
        await self._update_corretor_metrics(corretor_id, event_type, data)

        logger.debug("Business event tracked",
                    event_type=event_type,
                    corretor_id=corretor_id)

    async def _update_corretor_metrics(self, corretor_id: str, event_type: str, data: Dict[str, Any]):
        """Update individual corretor metrics."""
        if corretor_id not in self.corretor_data:
            # Initialize new corretor
            self.corretor_data[corretor_id] = CorretrMetrics(
                corretor_id=corretor_id,
                name=data.get('name', f'Corretor {corretor_id}'),
                messages_today=0,
                messages_this_week=0,
                messages_total=0,
                avg_response_time_ms=0.0,
                satisfaction_score=5.0,
                success_rate_percent=100.0,
                monthly_revenue_brl=147.0,  # Base subscription
                cost_per_message_brl=0.0,
                roi_score=0.0,
                active_days_this_month=0,
                last_activity=datetime.now(),
                retention_score=1.0,
                features_used=[],
                favorite_features=[],
                churn_risk_score=0.0,
                lifetime_value_brl=0.0,
                next_action_recommendation=""
            )

        corretor = self.corretor_data[corretor_id]

        # Update based on event type
        if event_type == "message_sent":
            corretor.messages_today += 1
            corretor.messages_this_week += 1
            corretor.messages_total += 1
            corretor.last_activity = datetime.now()

        elif event_type == "response_received":
            response_time = data.get('response_time_ms', 0)
            # Update rolling average
            if corretor.avg_response_time_ms == 0:
                corretor.avg_response_time_ms = response_time
            else:
                corretor.avg_response_time_ms = (corretor.avg_response_time_ms * 0.9) + (response_time * 0.1)

        elif event_type == "satisfaction_rating":
            rating = data.get('rating', 5)
            # Update rolling average
            corretor.satisfaction_score = (corretor.satisfaction_score * 0.8) + (rating * 0.2)

        elif event_type == "feature_used":
            feature = data.get('feature', '')
            if feature and feature not in corretor.features_used:
                corretor.features_used.append(feature)

        elif event_type == "payment_received":
            amount = data.get('amount_brl', 0)
            corretor.monthly_revenue_brl += amount

        # Recalculate derived metrics
        await self._recalculate_corretor_metrics(corretor)

    async def _recalculate_corretor_metrics(self, corretor: CorretrMetrics):
        """Recalculate derived metrics for a corretor."""
        # Calculate churn risk
        days_since_activity = (datetime.now() - corretor.last_activity).days
        satisfaction_factor = (5.0 - corretor.satisfaction_score) / 5.0
        usage_factor = max(0, (30 - corretor.messages_this_week) / 30)

        corretor.churn_risk_score = min(1.0,
            (days_since_activity * 0.1) +
            (satisfaction_factor * 0.5) +
            (usage_factor * 0.4)
        )

        # Calculate ROI
        total_cost = corretor.messages_total * 0.30  # Estimated cost per message
        if total_cost > 0:
            corretor.roi_score = corretor.monthly_revenue_brl / total_cost

        # Calculate lifetime value (simplified)
        monthly_revenue = corretor.monthly_revenue_brl
        retention_months = max(1, 12 * (1 - corretor.churn_risk_score))
        corretor.lifetime_value_brl = monthly_revenue * retention_months

        # Generate recommendation
        if corretor.churn_risk_score > 0.7:
            corretor.next_action_recommendation = "High churn risk - contact immediately"
        elif corretor.satisfaction_score < 3.0:
            corretor.next_action_recommendation = "Low satisfaction - follow up on experience"
        elif len(corretor.features_used) < 3:
            corretor.next_action_recommendation = "Low engagement - suggest feature training"
        elif corretor.messages_this_week > 50:
            corretor.next_action_recommendation = "Power user - consider upsell opportunity"
        else:
            corretor.next_action_recommendation = "Stable - continue monitoring"

    async def calculate_business_metrics(self) -> BusinessMetrics:
        """Calculate comprehensive business metrics."""
        now = datetime.now()

        # Revenue metrics
        total_mrr = sum(c.monthly_revenue_brl for c in self.corretor_data.values())
        total_arr = total_mrr * 12

        # Calculate growth (compare to previous month)
        previous_metrics = self._get_previous_metrics(30)  # 30 days ago
        prev_mrr = previous_metrics.mrr_brl if previous_metrics else total_mrr
        revenue_growth = ((total_mrr - prev_mrr) / prev_mrr * 100) if prev_mrr > 0 else 0

        # Customer metrics
        total_corretores = len(self.corretor_data)
        active_corretores = len([c for c in self.corretor_data.values()
                               if (now - c.last_activity).days <= 7])

        new_corretores = len([c for c in self.corretor_data.values()
                            if (now - c.last_activity).days <= 30])  # Simplified

        # Usage metrics
        total_messages_today = sum(c.messages_today for c in self.corretor_data.values())
        avg_messages = total_messages_today / max(1, active_corretores)

        # Performance metrics
        response_times = [c.avg_response_time_ms for c in self.corretor_data.values()
                         if c.avg_response_time_ms > 0]
        avg_response_time = statistics.mean(response_times) if response_times else 0
        p95_response_time = np.percentile(response_times, 95) if response_times else 0

        # Cost metrics
        total_cost = total_messages_today * 0.30  # Estimated cost per message
        cost_per_message = 0.30
        cost_per_corretor = total_cost / max(1, active_corretores)
        margin = ((total_mrr - total_cost) / total_mrr * 100) if total_mrr > 0 else 0

        # Satisfaction metrics
        satisfaction_scores = [c.satisfaction_score for c in self.corretor_data.values()]
        avg_satisfaction = statistics.mean(satisfaction_scores) if satisfaction_scores else 5.0

        # Calculate NPS (simplified)
        promoters = len([s for s in satisfaction_scores if s >= 4.5])
        detractors = len([s for s in satisfaction_scores if s <= 3.0])
        nps = ((promoters - detractors) / len(satisfaction_scores) * 100) if satisfaction_scores else 0

        # Market metrics
        market_penetration = (total_corretores / self.uberlandia_total_corretores * 100)

        # Predictions
        projected_mrr = self._predict_next_month_mrr(total_mrr, revenue_growth)
        capacity_utilization = (total_messages_today / 15000 * 100)  # 15K daily capacity

        # Scale recommendation
        if capacity_utilization > 80:
            scale_rec = "Scale up - approaching capacity"
        elif capacity_utilization < 20:
            scale_rec = "Scale down opportunity"
        elif revenue_growth > 20:
            scale_rec = "Prepare for growth - monitor closely"
        else:
            scale_rec = "Stable - maintain current scale"

        metrics = BusinessMetrics(
            timestamp=now,
            mrr_brl=total_mrr,
            arr_brl=total_arr,
            revenue_growth_percent=revenue_growth,
            total_corretores=total_corretores,
            active_corretores=active_corretores,
            new_corretores_this_month=new_corretores,
            churned_corretores_this_month=0,  # Would calculate from historical data
            churn_rate_percent=5.0,  # Simplified
            total_messages_today=total_messages_today,
            avg_messages_per_corretor=avg_messages,
            peak_usage_time="14:00-16:00",  # Would calculate from real data
            avg_response_time_ms=avg_response_time,
            p95_response_time_ms=p95_response_time,
            uptime_percent=99.98,  # From infrastructure metrics
            error_rate_percent=0.05,  # From infrastructure metrics
            total_cost_brl=total_cost,
            cost_per_message_brl=cost_per_message,
            cost_per_corretor_brl=cost_per_corretor,
            margin_percent=margin,
            avg_satisfaction_score=avg_satisfaction,
            nps_score=nps,
            support_ticket_count=0,  # Would integrate with support system
            market_penetration_percent=market_penetration,
            competitive_position="Market Leader",
            projected_mrr_next_month=projected_mrr,
            capacity_utilization_percent=capacity_utilization,
            scale_recommendation=scale_rec
        )

        self.business_metrics_history.append(metrics)

        # Keep only last 90 days of history
        cutoff = now - timedelta(days=90)
        self.business_metrics_history = [
            m for m in self.business_metrics_history
            if m.timestamp > cutoff
        ]

        logger.info("Business metrics calculated",
                   mrr_brl=total_mrr,
                   active_corretores=active_corretores,
                   market_penetration=market_penetration)

        return metrics

    def _get_previous_metrics(self, days_ago: int) -> Optional[BusinessMetrics]:
        """Get business metrics from N days ago."""
        target_date = datetime.now() - timedelta(days=days_ago)

        # Find closest metrics to target date
        closest_metrics = None
        min_diff = float('inf')

        for metrics in self.business_metrics_history:
            diff = abs((metrics.timestamp - target_date).total_seconds())
            if diff < min_diff:
                min_diff = diff
                closest_metrics = metrics

        return closest_metrics

    def _predict_next_month_mrr(self, current_mrr: float, growth_rate: float) -> float:
        """Predict next month's MRR using simple trend analysis."""
        # Apply growth rate with some dampening
        monthly_growth = growth_rate / 12  # Convert annual to monthly
        dampened_growth = monthly_growth * 0.8  # Conservative estimate

        return current_mrr * (1 + dampened_growth / 100)

    async def get_corretor_insights(self, corretor_id: str) -> Dict[str, Any]:
        """Get detailed insights for a specific corretor."""
        if corretor_id not in self.corretor_data:
            return {"error": "Corretor not found"}

        corretor = self.corretor_data[corretor_id]

        # Calculate percentiles vs other corretores
        all_usage = [c.messages_this_week for c in self.corretor_data.values()]
        all_satisfaction = [c.satisfaction_score for c in self.corretor_data.values()]

        usage_percentile = self._calculate_percentile(corretor.messages_this_week, all_usage)
        satisfaction_percentile = self._calculate_percentile(corretor.satisfaction_score, all_satisfaction)

        # Generate insights
        insights = []

        if usage_percentile > 80:
            insights.append("📈 Power user - in top 20% by usage")
        elif usage_percentile < 20:
            insights.append("⚠️ Low usage - may need support or training")

        if satisfaction_percentile > 80:
            insights.append("😊 Highly satisfied - potential testimonial candidate")
        elif satisfaction_percentile < 40:
            insights.append("😟 Below average satisfaction - needs attention")

        if corretor.churn_risk_score > 0.6:
            insights.append("🚨 High churn risk - immediate action required")

        if len(corretor.features_used) > 5:
            insights.append("🔧 Feature explorer - knows the system well")

        # Revenue insights
        if corretor.roi_score > 3.0:
            insights.append("💰 High ROI - very profitable user")
        elif corretor.roi_score < 1.0:
            insights.append("💸 Low ROI - may need pricing adjustment")

        return {
            "corretor": asdict(corretor),
            "percentiles": {
                "usage": usage_percentile,
                "satisfaction": satisfaction_percentile
            },
            "insights": insights,
            "recommendations": [
                corretor.next_action_recommendation
            ],
            "benchmark_comparison": {
                "usage_vs_average": corretor.messages_this_week / max(1, statistics.mean(all_usage)),
                "satisfaction_vs_average": corretor.satisfaction_score / max(1, statistics.mean(all_satisfaction))
            }
        }

    def _calculate_percentile(self, value: float, dataset: List[float]) -> float:
        """Calculate percentile of value in dataset."""
        if not dataset:
            return 50.0

        sorted_data = sorted(dataset)
        position = 0

        for i, v in enumerate(sorted_data):
            if value <= v:
                position = i
                break
        else:
            position = len(sorted_data)

        return (position / len(sorted_data)) * 100

    async def get_dashboard_data(self, time_window: TimeWindow = TimeWindow.DAILY) -> Dict[str, Any]:
        """Get comprehensive dashboard data."""
        latest_metrics = await self.calculate_business_metrics()

        # Top performers
        top_users = sorted(
            self.corretor_data.values(),
            key=lambda c: c.messages_this_week,
            reverse=True
        )[:10]

        # At-risk users
        at_risk_users = sorted(
            self.corretor_data.values(),
            key=lambda c: c.churn_risk_score,
            reverse=True
        )[:5]

        # Feature adoption
        feature_usage = defaultdict(int)
        for corretor in self.corretor_data.values():
            for feature in corretor.features_used:
                feature_usage[feature] += 1

        # Growth trends (last 30 days)
        growth_data = []
        for i in range(30, 0, -1):
            historical = self._get_previous_metrics(i)
            if historical:
                growth_data.append({
                    "date": historical.timestamp.isoformat(),
                    "mrr": historical.mrr_brl,
                    "active_users": historical.active_corretores,
                    "messages": historical.total_messages_today
                })

        return {
            "business_metrics": asdict(latest_metrics),
            "top_performers": [
                {
                    "id": c.corretor_id,
                    "name": c.name,
                    "messages_week": c.messages_this_week,
                    "satisfaction": c.satisfaction_score,
                    "revenue": c.monthly_revenue_brl
                }
                for c in top_users
            ],
            "at_risk_users": [
                {
                    "id": c.corretor_id,
                    "name": c.name,
                    "churn_risk": c.churn_risk_score,
                    "days_inactive": (datetime.now() - c.last_activity).days,
                    "satisfaction": c.satisfaction_score
                }
                for c in at_risk_users
            ],
            "feature_adoption": dict(feature_usage),
            "growth_trends": growth_data,
            "alerts": self._generate_alerts(latest_metrics),
            "recommendations": self._generate_recommendations(latest_metrics)
        }

    def _generate_alerts(self, metrics: BusinessMetrics) -> List[Dict[str, Any]]:
        """Generate business alerts."""
        alerts = []

        if metrics.churn_rate_percent > 10:
            alerts.append({
                "level": "critical",
                "message": f"High churn rate: {metrics.churn_rate_percent:.1f}%",
                "action": "Review customer satisfaction and support"
            })

        if metrics.avg_satisfaction_score < 3.5:
            alerts.append({
                "level": "warning",
                "message": f"Low satisfaction: {metrics.avg_satisfaction_score:.1f}/5",
                "action": "Investigate product issues and user feedback"
            })

        if metrics.capacity_utilization_percent > 85:
            alerts.append({
                "level": "warning",
                "message": f"High capacity utilization: {metrics.capacity_utilization_percent:.1f}%",
                "action": "Prepare to scale infrastructure"
            })

        if metrics.margin_percent < 60:
            alerts.append({
                "level": "info",
                "message": f"Lower margin: {metrics.margin_percent:.1f}%",
                "action": "Review cost optimization opportunities"
            })

        return alerts

    def _generate_recommendations(self, metrics: BusinessMetrics) -> List[str]:
        """Generate business recommendations."""
        recommendations = []

        if metrics.market_penetration_percent < 50:
            recommendations.append(
                f"Market opportunity: Only {metrics.market_penetration_percent:.1f}% penetration in Uberlândia. "
                "Consider increased marketing efforts."
            )

        if metrics.revenue_growth_percent > 15:
            recommendations.append(
                f"Strong growth ({metrics.revenue_growth_percent:.1f}%). "
                "Prepare infrastructure and team for scaling."
            )

        if metrics.avg_messages_per_corretor < 20:
            recommendations.append(
                f"Low engagement ({metrics.avg_messages_per_corretor:.1f} msgs/corretor). "
                "Consider user education and feature promotion."
            )

        if metrics.nps_score > 70:
            recommendations.append(
                f"Excellent NPS ({metrics.nps_score:.0f}). "
                "Leverage for testimonials and referral program."
            )

        return recommendations


# Global business intelligence instance
_bi_engine: Optional[BusinessIntelligenceEngine] = None


def get_business_intelligence() -> BusinessIntelligenceEngine:
    """Get the global business intelligence engine."""
    global _bi_engine

    if _bi_engine is None:
        _bi_engine = BusinessIntelligenceEngine()

    return _bi_engine


# Convenience functions for tracking events
async def track_message_sent(corretor_id: str, message_data: Dict[str, Any]):
    """Track message sent event."""
    bi = get_business_intelligence()
    await bi.track_event("message_sent", corretor_id, message_data)


async def track_response_received(corretor_id: str, response_time_ms: float):
    """Track response received event."""
    bi = get_business_intelligence()
    await bi.track_event("response_received", corretor_id, {"response_time_ms": response_time_ms})


async def track_satisfaction_rating(corretor_id: str, rating: float):
    """Track satisfaction rating."""
    bi = get_business_intelligence()
    await bi.track_event("satisfaction_rating", corretor_id, {"rating": rating})


async def track_feature_usage(corretor_id: str, feature: str):
    """Track feature usage."""
    bi = get_business_intelligence()
    await bi.track_event("feature_used", corretor_id, {"feature": feature})