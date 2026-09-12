"""
Decision Ledger Engine (§10, §15).
Manages decisions, rejected alternatives (preserved disagreement),
governance lifecycle states, and superseding workflows.
"""

from typing import List, Optional

from defintra.core.db.database import Database
from defintra.core.models.entities import (
    ApprovalLevel,
    ArtifactState,
    ChangeRisk,
    Decision,
    EntityType,
    Evidence,
    Provenance,
    RejectedAlternative,
    SourceType,
    current_utc_time,
)
from defintra.core.security.redactor import SecretRedactor


class DecisionLedger:
    def __init__(self, db: Database):
        self.db = db

    def record_decision(
        self,
        project_id: str,
        decision_id: str,
        title: str,
        decision: str,
        reason: str,
        rejected_alternatives: Optional[List[RejectedAlternative]] = None,
        approval_level: ApprovalLevel = ApprovalLevel.USER,
        change_risk: ChangeRisk = ChangeRisk.MEDIUM,
        affected_components: Optional[List[str]] = None,
        confidence: float = 0.95,
        source: str = "Human Architecture Review",
        source_type: SourceType = SourceType.USER_EXPLICIT,
    ) -> Decision:
        title = SecretRedactor.sanitize_all(title)
        decision = SecretRedactor.sanitize_all(decision)
        reason = SecretRedactor.sanitize_all(reason)
        dec = Decision(
            id=decision_id,
            project_id=project_id,
            title=title,
            decision=decision,
            reason=reason,
            rejected_alternatives=rejected_alternatives or [],
            status=ArtifactState.APPROVED if source_type == SourceType.USER_EXPLICIT else ArtifactState.PROPOSED,
            approval_level=approval_level,
            change_risk=change_risk,
            affected_components=affected_components or [],
            provenance=Provenance(
                source=source,
                source_type=source_type,
                confidence=confidence,
                approved_by="User" if source_type == SourceType.USER_EXPLICIT else None,
                last_validated=current_utc_time(),
            ),
            evidence=[
                Evidence(
                    id=f"evi_{decision_id}_{int(current_utc_time()[:10].replace('-', ''))}",
                    target_entity_type=EntityType.DECISION,
                    target_entity_id=decision_id,
                    evidence_type="DECISION_JUSTIFICATION",
                    description=reason,
                    confidence=confidence,
                    source=source,
                )
            ],
        )
        self.db.save_decision(dec)
        return dec

    def add_rejected_alternative(
        self,
        decision_id: str,
        alternative: str,
        reason_rejected: str,
        proposed_by: Optional[str] = None,
    ) -> Optional[Decision]:
        # Fetch existing decisions
        project = self.db.get_first_project()
        if not project:
            return None
        decisions = self.db.get_decisions(project.id)
        target_dec = next((d for d in decisions if d.id == decision_id), None)
        if not target_dec:
            return None

        target_dec.rejected_alternatives.append(
            RejectedAlternative(
                alternative=alternative,
                reason_rejected=reason_rejected,
                proposed_by=proposed_by,
            )
        )
        self.db.save_decision(target_dec)
        return target_dec

    def supersede_decision(
        self,
        old_decision_id: str,
        new_decision_id: str,
        new_title: str,
        new_decision: str,
        new_reason: str,
        project_id: str,
    ) -> Decision:
        """
        Supersedes an approved decision without deleting it (§15, §48).
        The old decision is marked SUPERSEDED with superseded_by = new_decision_id.
        """
        decisions = self.db.get_decisions(project_id)
        old_dec = next((d for d in decisions if d.id == old_decision_id), None)

        # Create new decision
        rejected_alts = []
        if old_dec:
            # Add old decision to rejected/superseded history
            rejected_alts.append(
                RejectedAlternative(
                    alternative=old_dec.decision,
                    reason_rejected=f"Superseded by {new_decision_id}: {new_reason}",
                    proposed_by="Previous Architecture Milestone",
                )
            )
            # Update old decision status
            old_dec.status = ArtifactState.SUPERSEDED
            old_dec.superseded_by = new_decision_id
            self.db.save_decision(old_dec)

        new_dec = Decision(
            id=new_decision_id,
            project_id=project_id,
            title=new_title,
            decision=new_decision,
            reason=new_reason,
            rejected_alternatives=rejected_alts,
            status=ArtifactState.APPROVED,
            approval_level=ApprovalLevel.USER,
            change_risk=ChangeRisk.HIGH,
            affected_components=old_dec.affected_components if old_dec else [],
            provenance=Provenance(
                source="Supersede Workflow",
                source_type=SourceType.USER_CONFIRMED,
                derived_from=[old_decision_id] if old_dec else [],
                confidence=0.98,
            ),
        )
        self.db.save_decision(new_dec)
        return new_dec

    def get_decision_history(self, project_id: str) -> List[Decision]:
        return self.db.get_decisions(project_id)
