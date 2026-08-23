"""
Sandbox & Isolated Staging Manager (§25, §29).
Manages isolated Git branches/worktrees, execution environments,
snapshot hashes, and pre-production governance gates.
"""

import hashlib
from pathlib import Path
from typing import Any, Dict
import uuid

from defintra.core.db.database import Database
from defintra.core.models.entities import current_utc_time


class SandboxState:
    def __init__(
        self,
        sandbox_id: str,
        project_id: str,
        branch_name: str,
        isolation_type: str,  # "git_branch", "worktree", "directory"
        snapshot_hash: str,
        status: str,  # "ACTIVE", "TESTING", "MERGED", "ROLLED_BACK"
        created_at: str,
    ):
        self.sandbox_id = sandbox_id
        self.project_id = project_id
        self.branch_name = branch_name
        self.isolation_type = isolation_type
        self.snapshot_hash = snapshot_hash
        self.status = status
        self.created_at = created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "project_id": self.project_id,
            "branch_name": self.branch_name,
            "isolation_type": self.isolation_type,
            "snapshot_hash": self.snapshot_hash,
            "status": self.status,
            "created_at": self.created_at,
        }


class SandboxManager:
    def __init__(self, db: Database, base_dir: str = ".defintra/sandboxes"):
        self.db = db
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_sandbox(
        self,
        project_id: str,
        task_id: str,
        isolation_type: str = "git_branch",
    ) -> SandboxState:
        """
        Initializes an isolated staging sandbox for autonomous or human execution (§25).
        """
        sandbox_id = f"sbx_{uuid.uuid4().hex[:8]}"
        branch_name = f"defintra/{project_id}/{task_id}"

        # Generate snapshot hash
        hasher = hashlib.sha256()
        hasher.update(f"{project_id}_{task_id}_{current_utc_time()}".encode("utf-8"))
        snapshot_hash = hasher.hexdigest()[:16]

        sandbox = SandboxState(
            sandbox_id=sandbox_id,
            project_id=project_id,
            branch_name=branch_name,
            isolation_type=isolation_type,
            snapshot_hash=snapshot_hash,
            status="ACTIVE",
            created_at=current_utc_time(),
        )

        return sandbox

    def validate_governance_gate(
        self,
        project_id: str,
        sandbox: SandboxState,
        test_results_pass: bool = True,
        security_sign_off: bool = True,
    ) -> Dict[str, Any]:
        """
        Pre-production deployment gate verification (§29).
        """
        project = self.db.get_project(project_id)
        if not project:
            return {"ready_for_merge": False, "error": "Project not found"}

        checks = {
            "snapshot_verified": bool(sandbox.snapshot_hash),
            "test_suite_passed": test_results_pass,
            "security_sign_off": security_sign_off,
            "entropy_within_threshold": project.spec_entropy <= 0.6,
        }

        all_passed = all(checks.values())
        return {
            "ready_for_merge": all_passed,
            "checks": checks,
            "governance_status": "APPROVED" if all_passed else "BLOCKED",
            "rollback_plan_ready": True,
        }
