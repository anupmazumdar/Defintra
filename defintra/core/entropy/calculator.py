"""
Spec Health & Entropy Score Engine (§18).
Calculates real-time project entropy (0.0 to 1.0) and health percentage (0% to 100%),
providing actionable breakdown of unresolved ambiguity, pending unknowns, and active conflicts.
"""

from typing import Dict, List, Any
from defintra.core.models.entities import (
    Project,
    Requirement,
    Decision,
    Assumption,
    Unknown,
    Conflict,
    ArtifactState,
)


class SpecHealthReport:
    def __init__(
        self,
        entropy: float,
        health_score: float,
        metrics: Dict[str, Any],
        recommendations: List[str],
    ):
        self.entropy = entropy
        self.health_score = health_score
        self.metrics = metrics
        self.recommendations = recommendations

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entropy": round(self.entropy, 4),
            "health_score": round(self.health_score, 2),
            "metrics": self.metrics,
            "recommendations": self.recommendations,
        }


class EntropyCalculator:
    """
    Computes spec entropy based on graph state:
    Entropy = Sum(Weighted Penalties) normalized between 0.0 (perfect clarity) and 1.0 (pure ambiguity).
    """

    @classmethod
    def compute(
        cls,
        requirements: List[Requirement],
        decisions: List[Decision],
        assumptions: List[Assumption],
        unknowns: List[Unknown],
        conflicts: List[Conflict],
    ) -> SpecHealthReport:
        penalties = 0.0
        max_possible_penalty = 10.0  # Base scale
        recommendations = []

        # 1. Unknowns penalty (High weight)
        open_unknowns = [u for u in unknowns if u.status == "OPEN"]
        high_impact_unknowns = [u for u in open_unknowns if u.impact == "HIGH"]
        med_impact_unknowns = [u for u in open_unknowns if u.impact == "MEDIUM"]
        low_impact_unknowns = [u for u in open_unknowns if u.impact == "LOW"]

        unknown_penalty = (
            len(high_impact_unknowns) * 1.5
            + len(med_impact_unknowns) * 0.8
            + len(low_impact_unknowns) * 0.3
        )
        penalties += unknown_penalty
        if high_impact_unknowns:
            recommendations.append(
                f"Resolve {len(high_impact_unknowns)} high-impact Unknown(s) in questioning."
            )

        # 2. Conflicts penalty (Critical weight)
        open_conflicts = [c for c in conflicts if c.status == "OPEN"]
        crit_conflicts = [c for c in open_conflicts if c.severity == "CRITICAL"]
        high_conflicts = [c for c in open_conflicts if c.severity == "HIGH"]
        med_conflicts = [c for c in open_conflicts if c.severity not in ["CRITICAL", "HIGH"]]

        conflict_penalty = (
            len(crit_conflicts) * 2.5
            + len(high_conflicts) * 1.8
            + len(med_conflicts) * 0.8
        )
        penalties += conflict_penalty
        if open_conflicts:
            recommendations.append(
                f"Resolve {len(open_conflicts)} active Conflict(s) between architectural choices."
            )

        # 3. Assumptions with low confidence
        active_assumptions = [a for a in assumptions if a.status == "ACTIVE"]
        low_conf_assumptions = [a for a in active_assumptions if a.confidence < 0.7]
        assumption_penalty = len(low_conf_assumptions) * 0.6 + (len(active_assumptions) - len(low_conf_assumptions)) * 0.2
        penalties += assumption_penalty
        if low_conf_assumptions:
            recommendations.append(
                f"Verify {len(low_conf_assumptions)} weak assumption(s) (confidence < 0.7)."
            )

        # 4. Unvalidated Requirements
        proposed_reqs = [r for r in requirements if r.status == ArtifactState.PROPOSED]
        if requirements:
            unvalidated_ratio = len(proposed_reqs) / len(requirements)
            penalties += unvalidated_ratio * 2.0
            if unvalidated_ratio > 0.5:
                recommendations.append("Review and approve proposed requirements.")
        else:
            # No requirements yet
            penalties += 3.0
            recommendations.append("Define initial requirements to establish specification baseline.")

        # 5. Decisions approval
        unapproved_decisions = [
            d for d in decisions if d.status in [ArtifactState.PROPOSED, ArtifactState.CONFLICTED]
        ]
        if unapproved_decisions:
            penalties += len(unapproved_decisions) * 0.5
            recommendations.append(
                f"Sign off on {len(unapproved_decisions)} unapproved/proposed architectural decision(s)."
            )

        # Scale entropy to [0.0, 1.0]
        # Dynamic denominator ensuring scaling works gracefully
        effective_capacity = max_possible_penalty + max(
            0,
            (len(requirements) + len(decisions) + len(assumptions) + len(unknowns)) * 0.4,
        )
        entropy = min(1.0, max(0.0, penalties / effective_capacity))

        # Confidence bonus
        all_confidences = (
            [r.provenance.confidence for r in requirements]
            + [d.provenance.confidence for d in decisions]
            + [a.confidence for a in active_assumptions]
        )
        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.5

        # Refine health score: 100 - (entropy * 100 * (1.2 - 0.4 * avg_confidence))
        weighted_entropy = entropy * (1.2 - 0.4 * avg_confidence)
        health_score = max(0.0, min(100.0, (1.0 - weighted_entropy) * 100.0))

        if not recommendations:
            recommendations.append("Spec is healthy! Ready for context compilation and execution.")

        metrics = {
            "requirements_total": len(requirements),
            "requirements_proposed": len(proposed_reqs),
            "decisions_total": len(decisions),
            "decisions_unapproved": len(unapproved_decisions),
            "assumptions_active": len(active_assumptions),
            "assumptions_weak": len(low_conf_assumptions),
            "unknowns_open": len(open_unknowns),
            "unknowns_high_impact": len(high_impact_unknowns),
            "conflicts_open": len(open_conflicts),
            "average_confidence": round(avg_confidence, 2),
        }

        return SpecHealthReport(
            entropy=entropy,
            health_score=health_score,
            metrics=metrics,
            recommendations=recommendations,
        )
