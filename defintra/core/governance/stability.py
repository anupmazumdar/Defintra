"""
Architecture Stability Budget & Churn Engine (§33).
Calculates architectural stability, tracks modification velocity of decisions
and contracts, and triggers alerts when churn exceeds stability budgets.
"""

from typing import Any, Dict, List, Optional
from defintra.core.db.database import Database
from defintra.core.models.entities import ArtifactState


class StabilityReport:
    def __init__(
        self,
        churn_index: float,
        stability_score: float,
        is_budget_exceeded: bool,
        metrics: Dict[str, Any],
        warnings: List[str],
        recommendations: List[str],
        high_churn_nodes: Optional[List[str]] = None,
    ):
        self.churn_index = churn_index
        self.stability_score = stability_score
        self.is_budget_exceeded = is_budget_exceeded
        self.metrics = metrics
        self.warnings = warnings
        self.recommendations = recommendations
        self.high_churn_nodes = high_churn_nodes or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "churn_index": round(self.churn_index, 3),
            "stability_score": round(self.stability_score, 1),
            "is_budget_exceeded": self.is_budget_exceeded,
            "metrics": self.metrics,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "high_churn_nodes": self.high_churn_nodes,
        }


class StabilityBudgetEngine:
    def __init__(self, db: Database):
        self.db = db

    def evaluate_stability(self, project_id: str, max_churn_threshold: float = 0.5) -> StabilityReport:
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        reqs = self.db.get_requirements(project_id)
        decs = self.db.get_decisions(project_id)
        comps = self.db.get_components(project_id)
        contracts = self.db.get_contracts(project_id)

        # Count state distribution
        superseded_decs = [d for d in decs if d.status == ArtifactState.SUPERSEDED]
        proposed_decs = [d for d in decs if d.status == ArtifactState.PROPOSED]
        approved_decs = [d for d in decs if d.status == ArtifactState.APPROVED]

        implemented_comps = [c for c in comps if c.stability_state == ArtifactState.IMPLEMENTED]
        proposed_comps = [c for c in comps if c.stability_state == ArtifactState.PROPOSED]

        # Calculate Churn Index
        total_decisions = len(decs)
        total_components = len(comps)

        churn_weight = 0.0
        if total_decisions > 0:
            superseded_ratio = len(superseded_decs) / total_decisions
            proposed_ratio = len(proposed_decs) / total_decisions
            churn_weight += (superseded_ratio * 0.6) + (proposed_ratio * 0.3)

        if total_components > 0:
            comp_proposed_ratio = len(proposed_comps) / total_components
            churn_weight += comp_proposed_ratio * 0.3

        churn_index = min(1.0, max(0.0, churn_weight))
        stability_score = max(0.0, (1.0 - churn_index) * 100.0)
        is_budget_exceeded = churn_index > max_churn_threshold

        warnings = []
        recommendations = []

        if is_budget_exceeded:
            warnings.append(f"Architecture churn index ({churn_index:.2f}) exceeds allowed stability budget ({max_churn_threshold:.2f}).")
            recommendations.append("Freeze foundational decisions and require two-person governance review before modifying core contracts.")

        if superseded_decs:
            recommendations.append(f"Review {len(superseded_decs)} superseded architectural decisions to ensure all downstream implementations have been refactored.")

        if not warnings:
            recommendations.append("Architecture is highly stable. Safe for rapid feature implementation.")

        high_churn = [d.id for d in superseded_decs] + [c.id for c in proposed_comps]

        metrics = {
            "total_decisions": total_decisions,
            "approved_decisions": len(approved_decs),
            "superseded_decisions": len(superseded_decs),
            "total_components": total_components,
            "implemented_components": len(implemented_comps),
            "total_contracts": len(contracts),
        }

        return StabilityReport(
            churn_index=churn_index,
            stability_score=stability_score,
            is_budget_exceeded=is_budget_exceeded,
            metrics=metrics,
            warnings=warnings,
            recommendations=recommendations,
            high_churn_nodes=high_churn,
        )
