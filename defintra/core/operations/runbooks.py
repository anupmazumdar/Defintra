"""
Operations & Maintenance Runbook Engine (§31).
Generates operational runbooks for backup, disaster recovery,
failover, and zero-downtime deployment.
"""

from typing import Any, List

from defintra.core.db.database import Database


class RunbookGenerator:
    def __init__(self, db: Database):
        self.db = db

    def generate_runbook(self, project_id: str, runbook_type: str = "BACKUP_RESTORE") -> str:
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        reqs = self.db.get_requirements(project_id)
        decs = self.db.get_decisions(project_id)
        comps = self.db.get_components(project_id)

        rb_type = runbook_type.upper().strip()

        if rb_type in ["BACKUP", "BACKUP_RESTORE"]:
            return self._backup_restore_runbook(project, decs, comps)
        elif rb_type in ["FAILOVER", "DISASTER_RECOVERY", "DR"]:
            return self._disaster_recovery_runbook(project, comps)
        elif rb_type in ["ROLLBACK", "ZERO_DOWNTIME"]:
            return self._rollback_runbook(project, comps)
        else:
            return self._general_operations_runbook(project, reqs, decs, comps)

    def _backup_restore_runbook(self, project: Any, decs: List[Any], comps: List[Any]) -> str:
        db_choice = next((d.decision for d in decs if "database" in d.title.lower()), "Relational Database")
        lines = [
            "# Operations Runbook: Database Backup & Restore",
            f"> **Project:** {project.name} | **Target Storage:** {db_choice}",
            "",
            "## 1. Automated Snapshot Schedule",
            "- **Daily Snapshot:** Executed at 02:00 UTC with 30-day retention.",
            "- **Continuous WAL Archiving:** Point-in-time recovery (PITR) enabled with 7-day lookback.",
            "",
            "## 2. Emergency Backup Execution",
            "```bash",
            "# Step 1: Create ad-hoc point-in-time snapshot",
            "defintra sandbox create --task emergency_backup",
            "# Step 2: Flush pending WAL logs and dump schema + data",
            "# Step 3: Verify SHA-256 integrity hash",
            "```",
            "",
            "## 3. Restore Verification Walkthrough",
            "1. Provision a clean staging database instance.",
            "2. Download latest verified snapshot from encrypted backup storage.",
            "3. Restore schema, tables, and sequence constraints.",
            "4. Run smoke test suite to verify data consistency and read/write access.",
        ]
        return "\n".join(lines)

    def _disaster_recovery_runbook(self, project: Any, comps: List[Any]) -> str:
        lines = [
            "# Operations Runbook: Failover & Disaster Recovery",
            f"> **Project:** {project.name} | **Components:** {len(comps)}",
            "",
            "## 1. Incident Severity Triage",
            "- **Severity 1 (Full Outage):** Primary region unreachable; initiate regional failover.",
            "- **Severity 2 (Degraded Performance):** Read-replica saturation; scale horizontal replicas.",
            "",
            "## 2. Failover Sequence",
            "1. **DNS Cutover:** Update Cloudflare/Route53 routing to Standby Region.",
            "2. **Database Promotion:** Promote read-replica in standby region to primary read-write node.",
            "3. **Service Startup:** Bring up container tasks in standby region with active health checks.",
            "4. **Post-Failover Audit:** Verify error rate falls below 0.1%.",
        ]
        return "\n".join(lines)

    def _rollback_runbook(self, project: Any, comps: List[Any]) -> str:
        lines = [
            "# Operations Runbook: Zero-Downtime Rollback Procedure",
            f"> **Project:** {project.name}",
            "",
            "## 1. Rollback Triggers",
            "- Error rate spike > 1% over 5 minutes post-deployment.",
            "- Database migration failure or connection pool exhaustion.",
            "- Security anomaly detection alert triggered.",
            "",
            "## 2. Execution Steps",
            "1. Shift 100% of ingress traffic to Previous Stable Deployment Slot (Blue/Green).",
            "2. If schema migration is backward-compatible, leave schema intact; otherwise execute down-migration script.",
            "3. Notify on-call engineering lead and log post-mortem action items.",
        ]
        return "\n".join(lines)

    def _general_operations_runbook(self, project: Any, reqs: List[Any], decs: List[Any], comps: List[Any]) -> str:
        lines = [
            f"# Standard Operations Runbook — {project.name}",
            f"> **Objective:** {project.objective}",
            "",
            "## 1. Architecture Components Overview",
        ]
        for c in comps:
            lines.append(f"- **`{c.id}` ({c.name})**: {c.component_type} — *Status: {c.stability_state.value}*")

        lines.extend([
            "",
            "## 2. Health Monitoring & Metrics",
            "- Service Latency (p95 < 200ms, p99 < 500ms)",
            "- HTTP 5xx Error Rate (< 0.05%)",
            "- Database Connection Utilization (< 70%)",
        ])
        return "\n".join(lines)
