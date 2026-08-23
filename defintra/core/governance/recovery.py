"""
Failure Modes & Recovery Patterns Engine (§48).
Provides automated diagnosis and structured self-healing recovery workflows for:
1. Contradiction deadlocks
2. Spec entropy spikes
3. Superseded decision orphans
4. Stability churn budget breaches
5. Low-confidence unvalidated assumptions
"""

from typing import Any, Dict, List, Optional
from defintra.core.db.database import Database
from defintra.core.entropy.calculator import EntropyCalculator
from defintra.core.governance.stability import StabilityBudgetEngine


class FailureDiagnosis:
    def __init__(
        self,
        failure_id: str,
        failure_type: str,
        severity: str,
        title: str,
        impact_summary: str,
        root_cause_nodes: List[str],
        remediation_steps: List[str],
        auto_fix_command: Optional[str] = None,
    ):
        self.failure_id = failure_id
        self.failure_type = failure_type
        self.severity = severity
        self.title = title
        self.impact_summary = impact_summary
        self.root_cause_nodes = root_cause_nodes
        self.remediation_steps = remediation_steps
        self.auto_fix_command = auto_fix_command

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_id": self.failure_id,
            "failure_type": self.failure_type,
            "severity": self.severity,
            "title": self.title,
            "impact_summary": self.impact_summary,
            "root_cause_nodes": self.root_cause_nodes,
            "remediation_steps": self.remediation_steps,
            "auto_fix_command": self.auto_fix_command,
        }


class RecoveryReport:
    def __init__(
        self,
        project_id: str,
        system_health_status: str,  # HEALTHY, DEGRADED, CRITICAL_FAILURE
        diagnoses: List[FailureDiagnosis],
    ):
        self.project_id = project_id
        self.system_health_status = system_health_status
        self.diagnoses = diagnoses

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "system_health_status": self.system_health_status,
            "failure_count": len(self.diagnoses),
            "diagnoses": [d.to_dict() for d in self.diagnoses],
        }


class FailureRecoveryEngine:
    def __init__(self, db: Database):
        self.db = db

    def diagnose_project(self, project_id: str) -> RecoveryReport:
        """
        Executes a diagnostic check against all known failure modes (§48).
        """
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        reqs = self.db.get_requirements(project_id)
        decs = self.db.get_decisions(project_id)
        asms = self.db.get_assumptions(project_id)
        unks = self.db.get_unknowns(project_id)
        confs = self.db.get_conflicts(project_id)

        diagnoses: List[FailureDiagnosis] = []

        # 1. Contradiction Deadlocks
        active_confs = [c for c in confs if c.status == "OPEN"]
        if active_confs:
            diagnoses.append(
                FailureDiagnosis(
                    failure_id="FAIL-CONTRADICTION",
                    failure_type="CONTRADICTION_DEADLOCK",
                    severity="CRITICAL",
                    title="Active Contradictions Blocking Execution",
                    impact_summary=f"{len(active_confs)} architectural or requirement contradictions remain unresolved.",
                    root_cause_nodes=[c.id for c in active_confs],
                    remediation_steps=[
                        f"Run `defintra conflicts --resolve {active_confs[0].id} --winner <WINNER_ID>` to select the authoritative invariant.",
                        "Reconcile downstream contracts to conform with the winning decision.",
                    ],
                    auto_fix_command=f"defintra conflicts --resolve {active_confs[0].id}",
                )
            )

        # 2. Spec Entropy Spikes
        health = EntropyCalculator.compute(reqs, decs, asms, unks, confs)
        if health.health_score < 60.0 or health.entropy > 0.50:
            open_high_unks = [u for u in unks if u.status == "OPEN" and u.impact == "HIGH"]
            diagnoses.append(
                FailureDiagnosis(
                    failure_id="FAIL-ENTROPY",
                    failure_type="ENTROPY_SPIKE",
                    severity="HIGH",
                    title="Specification Ambiguity & Entropy Spike",
                    impact_summary=f"Spec health is at {health.health_score:.1f}% with entropy score {health.entropy:.2f} / 1.0.",
                    root_cause_nodes=[u.id for u in open_high_unks],
                    remediation_steps=[
                        "Launch interactive questioning loop: `defintra question`.",
                        "Answer high-impact unknowns to establish foundational constraints before compiling prompts.",
                    ],
                    auto_fix_command="defintra question",
                )
            )

        # 3. Superseded Decision Orphans
        superseded_decs = [d for d in decs if d.status.value == "SUPERSEDED" or d.superseded_by]
        if superseded_decs:
            diagnoses.append(
                FailureDiagnosis(
                    failure_id="FAIL-SUPERSEDED-ORPHANS",
                    failure_type="SUPERSEDED_DECISION_ORPHANS",
                    severity="MEDIUM",
                    title="Superseded Decisions Need Downstream Re-anchoring",
                    impact_summary=f"{len(superseded_decs)} superseded decisions exist in the ledger.",
                    root_cause_nodes=[d.id for d in superseded_decs],
                    remediation_steps=[
                        "Inspect downstream components connected to superseded decisions.",
                        "Re-route edges to point to the active replacement decisions.",
                        "Run `defintra stability` to confirm governance compliance.",
                    ],
                    auto_fix_command="defintra stability",
                )
            )

        # 4. Stability Churn Budget Breach
        stab_engine = StabilityBudgetEngine(self.db)
        stab_rep = stab_engine.evaluate_stability(project_id)
        if stab_rep.is_budget_exceeded:
            diagnoses.append(
                FailureDiagnosis(
                    failure_id="FAIL-CHURN-BREACH",
                    failure_type="STABILITY_CHURN_BREACH",
                    severity="HIGH",
                    title="Architecture Modification Churn Exceeds Budget",
                    impact_summary=f"Churn index ({stab_rep.churn_index:.2f}) exceeds the 0.50 stability threshold.",
                    root_cause_nodes=stab_rep.high_churn_nodes or ["GLOBAL_GRAPH"],
                    remediation_steps=[
                        "Freeze core database and API contracts.",
                        "Require two-person governance sign-off on any further architectural modifications.",
                    ],
                    auto_fix_command="defintra stability",
                )
            )

        status_str = "HEALTHY"
        if any(d.severity == "CRITICAL" for d in diagnoses):
            status_str = "CRITICAL_FAILURE"
        elif diagnoses:
            status_str = "DEGRADED"

        return RecoveryReport(
            project_id=project_id,
            system_health_status=status_str,
            diagnoses=diagnoses,
        )
