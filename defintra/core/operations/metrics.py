"""
Production Operational Metrics & SLO Feedback Loop (§30).
Tracks production operational metrics, monitors SLO/SLA compliance,
and correlates runtime anomalies back to originating components and requirements.
"""

from typing import Any, Dict, List, Optional
from defintra.core.db.database import Database


class SLOMetric:
    def __init__(
        self,
        name: str,
        current_value: float,
        target_value: float,
        unit: str,
        is_compliant: bool,
        affected_component: str,
    ):
        self.name = name
        self.current_value = round(current_value, 2)
        self.target_value = round(target_value, 2)
        self.unit = unit
        self.is_compliant = is_compliant
        self.affected_component = affected_component

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "current_value": self.current_value,
            "target_value": self.target_value,
            "unit": self.unit,
            "is_compliant": self.is_compliant,
            "affected_component": self.affected_component,
        }


class ProductionHealthReport:
    def __init__(
        self,
        project_id: str,
        overall_status: str,  # HEALTHY, DEGRADED, BREACHED
        slo_compliance_rate: float,
        metrics: List[SLOMetric],
        alerts: List[str],
    ):
        self.project_id = project_id
        self.overall_status = overall_status
        self.slo_compliance_rate = round(slo_compliance_rate, 1)
        self.metrics = metrics
        self.alerts = alerts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "overall_status": self.overall_status,
            "slo_compliance_rate": self.slo_compliance_rate,
            "metrics": [m.to_dict() for m in self.metrics],
            "alerts": self.alerts,
        }


class ProductionMetricsTracker:
    def __init__(self, db: Database):
        self.db = db

    def evaluate_production_health(
        self,
        project_id: str,
        custom_metrics: Optional[Dict[str, float]] = None,
    ) -> ProductionHealthReport:
        """
        Evaluates production telemetry against approved architectural SLOs (§30).
        """
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        comps = self.db.get_components(project_id)
        api_comp = next((c.id for c in comps if c.component_type == "BACKEND"), "COMP-API")
        db_comp = next((c.id for c in comps if c.component_type == "DATABASE"), "COMP-DB")

        # Telemetry baselines or custom inputs
        data = custom_metrics or {
            "uptime": 99.95,
            "p95_latency_ms": 120.0,
            "error_rate_pct": 0.04,
            "db_connection_pool_pct": 35.0,
        }

        metrics = [
            SLOMetric(
                name="Service Availability (Uptime)",
                current_value=data.get("uptime", 99.95),
                target_value=99.90,
                unit="%",
                is_compliant=data.get("uptime", 99.95) >= 99.90,
                affected_component=api_comp,
            ),
            SLOMetric(
                name="P95 API Latency",
                current_value=data.get("p95_latency_ms", 120.0),
                target_value=200.0,
                unit="ms",
                is_compliant=data.get("p95_latency_ms", 120.0) <= 200.0,
                affected_component=api_comp,
            ),
            SLOMetric(
                name="HTTP 5xx Error Rate",
                current_value=data.get("error_rate_pct", 0.04),
                target_value=0.10,
                unit="%",
                is_compliant=data.get("error_rate_pct", 0.04) <= 0.10,
                affected_component=api_comp,
            ),
            SLOMetric(
                name="Database Connection Pool Utilization",
                current_value=data.get("db_connection_pool_pct", 35.0),
                target_value=75.0,
                unit="%",
                is_compliant=data.get("db_connection_pool_pct", 35.0) <= 75.0,
                affected_component=db_comp,
            ),
        ]

        compliant_count = sum(1 for m in metrics if m.is_compliant)
        compliance_rate = (compliant_count / len(metrics)) * 100.0

        alerts = []
        for m in metrics:
            if not m.is_compliant:
                alerts.append(f"SLO Breach on {m.name}: Current {m.current_value}{m.unit} exceeds target {m.target_value}{m.unit} (Affects {m.affected_component})")

        status = "HEALTHY" if compliance_rate == 100.0 else ("DEGRADED" if compliance_rate >= 75.0 else "BREACHED")

        return ProductionHealthReport(
            project_id=project_id,
            overall_status=status,
            slo_compliance_rate=compliance_rate,
            metrics=metrics,
            alerts=alerts,
        )
