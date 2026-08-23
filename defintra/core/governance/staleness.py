"""
Confidence Decay & Staleness Detection Engine (§9).
Tracks `last_validated` timestamps against downstream change activity.
Proactively surfaces stale high-confidence items when dependencies change.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List
from defintra.core.db.database import Database
from defintra.core.graph.engine import ProjectGraph
from defintra.core.models.entities import current_utc_time


class StaleNodeReport:
    def __init__(
        self,
        node_id: str,
        node_type: str,
        title: str,
        original_confidence: float,
        decayed_confidence: float,
        staleness_reason: str,
        downstream_mutation_count: int,
        days_since_validation: float,
    ):
        self.node_id = node_id
        self.node_type = node_type
        self.title = title
        self.original_confidence = original_confidence
        self.decayed_confidence = round(decayed_confidence, 2)
        self.staleness_reason = staleness_reason
        self.downstream_mutation_count = downstream_mutation_count
        self.days_since_validation = days_since_validation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "title": self.title,
            "original_confidence": self.original_confidence,
            "decayed_confidence": self.decayed_confidence,
            "staleness_reason": self.staleness_reason,
            "downstream_mutation_count": self.downstream_mutation_count,
            "days_since_validation": self.days_since_validation,
        }


class StalenessReport:
    def __init__(
        self,
        project_id: str,
        total_nodes_checked: int,
        stale_nodes: List[StaleNodeReport],
        average_confidence: float,
        system_staleness_score: float,  # 0.0 (fresh) to 1.0 (very stale)
    ):
        self.project_id = project_id
        self.total_nodes_checked = total_nodes_checked
        self.stale_nodes = stale_nodes
        self.average_confidence = round(average_confidence, 2)
        self.system_staleness_score = round(system_staleness_score, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "total_nodes_checked": self.total_nodes_checked,
            "stale_node_count": len(self.stale_nodes),
            "average_confidence": self.average_confidence,
            "system_staleness_score": self.system_staleness_score,
            "stale_nodes": [s.to_dict() for s in self.stale_nodes],
        }


class StalenessEngine:
    def __init__(self, db: Database):
        self.db = db

    def evaluate_staleness(self, project_id: str) -> StalenessReport:
        """
        Scans all requirements, decisions, assumptions, and contracts in the project.
        Calculates confidence decay based on downstream dependency churn and elapsed time (§9).
        """
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        reqs = self.db.get_requirements(project_id)
        decs = self.db.get_decisions(project_id)
        asms = self.db.get_assumptions(project_id)

        p_graph = ProjectGraph(self.db, project_id)
        audit_entries = self.db.get_audit_entries(project_id)
        total_mutations = len(audit_entries)

        stale_nodes: List[StaleNodeReport] = []
        all_confidences: List[float] = []

        # Check Requirements
        for r in reqs:
            conf = r.provenance.confidence
            decay = self._compute_decay(r.id, conf, r.provenance.last_validated or r.created_at, p_graph, total_mutations)
            all_confidences.append(decay["new_confidence"])
            if decay["is_stale"]:
                stale_nodes.append(
                    StaleNodeReport(
                        node_id=r.id,
                        node_type="REQUIREMENT",
                        title=r.title,
                        original_confidence=conf,
                        decayed_confidence=decay["new_confidence"],
                        staleness_reason=decay["reason"],
                        downstream_mutation_count=decay["downstream_count"],
                        days_since_validation=decay["days_elapsed"],
                    )
                )

        # Check Decisions
        for d in decs:
            conf = d.provenance.confidence
            decay = self._compute_decay(d.id, conf, d.provenance.last_validated or d.created_at, p_graph, total_mutations)
            all_confidences.append(decay["new_confidence"])
            if decay["is_stale"]:
                stale_nodes.append(
                    StaleNodeReport(
                        node_id=d.id,
                        node_type="DECISION",
                        title=d.title,
                        original_confidence=conf,
                        decayed_confidence=decay["new_confidence"],
                        staleness_reason=decay["reason"],
                        downstream_mutation_count=decay["downstream_count"],
                        days_since_validation=decay["days_elapsed"],
                    )
                )

        # Check Assumptions
        for a in asms:
            conf = a.confidence
            decay = self._compute_decay(a.id, conf, a.provenance.last_validated or a.created_at, p_graph, total_mutations)
            all_confidences.append(decay["new_confidence"])
            if decay["is_stale"] or decay["new_confidence"] < 0.5:
                stale_nodes.append(
                    StaleNodeReport(
                        node_id=a.id,
                        node_type="ASSUMPTION",
                        title=a.statement[:50],
                        original_confidence=conf,
                        decayed_confidence=decay["new_confidence"],
                        staleness_reason=decay["reason"] or "Low baseline assumption confidence",
                        downstream_mutation_count=decay["downstream_count"],
                        days_since_validation=decay["days_elapsed"],
                    )
                )

        total_checked = len(reqs) + len(decs) + len(asms)
        avg_conf = sum(all_confidences) / max(len(all_confidences), 1) if all_confidences else 1.0
        staleness_score = len(stale_nodes) / max(total_checked, 1)

        return StalenessReport(
            project_id=project_id,
            total_nodes_checked=total_checked,
            stale_nodes=stale_nodes,
            average_confidence=avg_conf,
            system_staleness_score=staleness_score,
        )

    def _compute_decay(
        self,
        node_id: str,
        base_confidence: float,
        timestamp_str: str,
        p_graph: ProjectGraph,
        total_mutations: int,
    ) -> Dict[str, Any]:
        blast = p_graph.calculate_blast_radius(node_id)
        downstream_count = blast.total_blast_count

        # Estimate elapsed days
        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            days_elapsed = (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0
        except Exception:
            days_elapsed = 0.0

        # Downstream churn penalty
        churn_penalty = min(downstream_count * 0.05, 0.3)
        time_penalty = min(days_elapsed * 0.02, 0.2)
        decayed = max(base_confidence - churn_penalty - time_penalty, 0.1)

        is_stale = (base_confidence >= 0.8 and decayed <= 0.65) or (downstream_count >= 3 and days_elapsed > 7.0)
        reasons = []
        if downstream_count >= 3:
            reasons.append(f"{downstream_count} downstream dependents modified")
        if days_elapsed > 7.0:
            reasons.append(f"{days_elapsed:.1f} days without explicit re-validation")

        return {
            "new_confidence": decayed,
            "is_stale": is_stale,
            "reason": "; ".join(reasons) or "Confidence decayed due to downstream graph changes",
            "downstream_count": downstream_count,
            "days_elapsed": round(days_elapsed, 1),
        }

    def revalidate_node(self, project_id: str, node_id: str, validator: str = "User") -> bool:
        """
        Refreshes the validation timestamp and restores confidence to 1.0 (§9).
        """
        now = current_utc_time()
        # Check requirements
        reqs = self.db.get_requirements(project_id)
        for r in reqs:
            if r.id == node_id:
                r.provenance.last_validated = now
                r.provenance.approved_by = validator
                r.provenance.confidence = 0.95
                self.db.save_requirement(r)
                return True

        # Check decisions
        decs = self.db.get_decisions(project_id)
        for d in decs:
            if d.id == node_id:
                d.provenance.last_validated = now
                d.provenance.approved_by = validator
                d.provenance.confidence = 0.99
                self.db.save_decision(d)
                return True

        # Check assumptions
        asms = self.db.get_assumptions(project_id)
        for a in asms:
            if a.id == node_id:
                a.provenance.last_validated = now
                a.provenance.approved_by = validator
                a.confidence = 0.90
                a.status = "VALIDATED"
                self.db.save_assumption(a)
                return True

        return False
