"""
Discovery Audit Logger (§17).
Records silent assumptions that the discovery/questioning engine made without asking the user,
explaining why they were skipped, their risk rating, and category.
"""

from typing import List

from defintra.core.db.database import Database
from defintra.core.models.entities import ChangeRisk, DiscoveryAuditEntry, current_utc_time


class DiscoveryAuditLogger:
    def __init__(self, db: Database):
        self.db = db

    def record_silent_assumption(
        self,
        project_id: str,
        entry_id: str,
        silent_assumption: str,
        reason_skipped: str,
        risk_level: ChangeRisk = ChangeRisk.LOW,
        category: str = "GENERAL",
    ) -> DiscoveryAuditEntry:
        entry = DiscoveryAuditEntry(
            id=entry_id,
            project_id=project_id,
            silent_assumption=silent_assumption,
            reason_skipped=reason_skipped,
            risk_level=risk_level,
            category=category,
            created_at=current_utc_time(),
        )
        self.db.save_audit_entry(entry)
        return entry

    def get_audit_log(self, project_id: str) -> List[DiscoveryAuditEntry]:
        return self.db.get_audit_entries(project_id)
