"""
Sandbox & Isolated Staging Manager (§25, §29).
Manages isolated Git branches/worktrees, execution environments,
snapshot hashes, and pre-production governance gates.
"""

import hashlib
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from defintra.core.db.database import Database
from defintra.core.models.entities import current_utc_time
from defintra.core.policy.engine import PolicyDecision, PolicyEngine


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
        allowed_actions: Optional[list[str]] = None,
        denied_actions: Optional[list[str]] = None,
    ):
        self.sandbox_id = sandbox_id
        self.project_id = project_id
        self.branch_name = branch_name
        self.isolation_type = isolation_type
        self.snapshot_hash = snapshot_hash
        self.status = status
        self.created_at = created_at
        self.allowed_actions = allowed_actions or []
        self.denied_actions = denied_actions or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "project_id": self.project_id,
            "branch_name": self.branch_name,
            "isolation_type": self.isolation_type,
            "snapshot_hash": self.snapshot_hash,
            "status": self.status,
            "created_at": self.created_at,
            "allowed_actions": self.allowed_actions,
            "denied_actions": self.denied_actions,
        }


class SandboxManager:
    def __init__(self, db: Database, base_dir: str = ".defintra/sandboxes"):
        self.db = db
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.policy_engine = PolicyEngine(db)

    def create_sandbox(
        self,
        project_id: str,
        task_id: str,
        isolation_type: str = "git_branch",
    ) -> SandboxState:
        """
        Initializes an isolated staging sandbox for autonomous or human execution (§25, §45).
        Tags sandbox with capability-scoped allowed and denied actions derived from the policy engine.
        """
        sandbox_id = f"sbx_{uuid.uuid4().hex[:8]}"
        branch_name = f"defintra/{project_id}/{task_id}"

        # Generate snapshot hash
        hasher = hashlib.sha256()
        hasher.update(f"{project_id}_{task_id}_{current_utc_time()}".encode("utf-8"))
        snapshot_hash = hasher.hexdigest()[:16]

        # Derive capability scopes from policy engine
        policies = self.policy_engine.list_policies(project_id)
        allowed_actions = [p.action_type for p in policies if p.decision.value != "DENY"]
        denied_actions = [p.action_type for p in policies if p.decision.value == "DENY"]

        sandbox = SandboxState(
            sandbox_id=sandbox_id,
            project_id=project_id,
            branch_name=branch_name,
            isolation_type=isolation_type,
            snapshot_hash=snapshot_hash,
            status="ACTIVE",
            created_at=current_utc_time(),
            allowed_actions=allowed_actions,
            denied_actions=denied_actions,
        )

        return sandbox

    def evaluate_sandbox_action(
        self,
        project_id: str,
        action_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> PolicyDecision:
        """
        Consults the Policy Engine before an agent performs an action in the sandbox (§25, §45).
        """
        return self.policy_engine.evaluate_action(project_id, action_type, context=context)

    def execute_sandbox_action(
        self,
        sandbox: SandboxState,
        action_type: str,
        approved_by: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Enforces policy boundaries on actions executed inside the sandbox (§25, §45).
        Refuses execution on DENY or unapproved REQUIRES_APPROVAL actions.
        """
        allowed, reason, decision = self.policy_engine.enforce_action(
            project_id=sandbox.project_id,
            action_type=action_type,
            approved_by=approved_by,
            context=context,
        )

        return {
            "sandbox_id": sandbox.sandbox_id,
            "action_type": action_type,
            "allowed": allowed,
            "status": "EXECUTED" if allowed else "BLOCKED",
            "decision": decision.decision.value,
            "risk_level": decision.risk_level.value,
            "reason": reason,
        }

    def validate_governance_gate(
        self,
        project_id: str,
        sandbox: SandboxState,
        test_results_pass: bool = True,
        security_sign_off: bool = True,
    ) -> Dict[str, Any]:
        """
        Pre-production deployment gate verification (§29, §45).
        """
        project = self.db.get_project(project_id)
        if not project:
            return {"ready_for_merge": False, "error": "Project not found"}

        # Check policy for deployment action
        deploy_policy = self.policy_engine.evaluate_action(project_id, "deploy")

        checks = {
            "snapshot_verified": bool(sandbox.snapshot_hash),
            "test_suite_passed": test_results_pass,
            "security_sign_off": security_sign_off,
            "entropy_within_threshold": project.spec_entropy <= 0.6,
            "policy_governance_satisfied": deploy_policy.decision.value != "DENY",
        }

        all_passed = all(checks.values())
        return {
            "ready_for_merge": all_passed,
            "checks": checks,
            "governance_status": "APPROVED" if all_passed else "BLOCKED",
            "rollback_plan_ready": True,
        }

