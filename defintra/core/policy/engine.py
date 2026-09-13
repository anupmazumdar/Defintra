"""
Autonomous Agent Policy & Governance Engine (§45).
Enforces security boundaries, risk-tiered action governance,
and approval requirements before an autonomous agent executes actions.
"""

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from defintra.core.db.database import Database
from defintra.core.models.entities import ApprovalLevel, Approver, ChangeRisk, current_utc_time


class PolicyDecisionType(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


class PolicyAction(str, Enum):
    READ_REPOSITORY = "read_repository"
    MODIFY_FILE = "modify_file"
    EXECUTE_SHELL = "execute_shell"
    ACCESS_INTERNET = "access_internet"
    INSTALL_PACKAGE = "install_package"
    ACCESS_DATABASE = "access_database"
    ACCESS_SECRET = "access_secret"
    DEPLOY = "deploy"
    MODIFY_INFRASTRUCTURE = "modify_infrastructure"
    DELETE_PRODUCTION_DATA = "delete_production_data"


class PolicyRule:
    def __init__(
        self,
        action_type: str,
        decision: PolicyDecisionType,
        risk_level: ChangeRisk,
        required_approval: ApprovalLevel,
        description: str = "",
    ):
        self.action_type = action_type
        self.decision = decision
        self.risk_level = risk_level
        self.required_approval = required_approval
        self.description = description

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "decision": self.decision.value,
            "risk_level": self.risk_level.value,
            "required_approval": self.required_approval.value,
            "description": self.description,
        }


class PolicyDecision:
    def __init__(
        self,
        action_type: str,
        decision: PolicyDecisionType,
        risk_level: ChangeRisk,
        required_approval: ApprovalLevel,
        reason: str,
    ):
        self.action_type = action_type
        self.decision = decision
        self.risk_level = risk_level
        self.required_approval = required_approval
        self.reason = reason
        self.is_allowed = (decision == PolicyDecisionType.ALLOW)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "decision": self.decision.value,
            "risk_level": self.risk_level.value,
            "required_approval": self.required_approval.value,
            "reason": self.reason,
            "is_allowed": self.is_allowed,
        }


# Standard Canonical Default Policy Table (§45)
DEFAULT_POLICY_RULES: List[PolicyRule] = [
    PolicyRule(
        action_type=PolicyAction.READ_REPOSITORY.value,
        decision=PolicyDecisionType.ALLOW,
        risk_level=ChangeRisk.LOW,
        required_approval=ApprovalLevel.NONE,
        description="Read workspace repository files and AST definitions",
    ),
    PolicyRule(
        action_type=PolicyAction.MODIFY_FILE.value,
        decision=PolicyDecisionType.REQUIRES_APPROVAL,
        risk_level=ChangeRisk.MEDIUM,
        required_approval=ApprovalLevel.USER,
        description="Write or patch code files in workspace",
    ),
    PolicyRule(
        action_type=PolicyAction.EXECUTE_SHELL.value,
        decision=PolicyDecisionType.REQUIRES_APPROVAL,
        risk_level=ChangeRisk.HIGH,
        required_approval=ApprovalLevel.USER,
        description="Execute local terminal or shell commands",
    ),
    PolicyRule(
        action_type=PolicyAction.ACCESS_INTERNET.value,
        decision=PolicyDecisionType.REQUIRES_APPROVAL,
        risk_level=ChangeRisk.MEDIUM,
        required_approval=ApprovalLevel.USER,
        description="Outbound HTTP/HTTPS network requests",
    ),
    PolicyRule(
        action_type=PolicyAction.INSTALL_PACKAGE.value,
        decision=PolicyDecisionType.REQUIRES_APPROVAL,
        risk_level=ChangeRisk.MEDIUM,
        required_approval=ApprovalLevel.USER,
        description="Install external third-party dependencies (pip/npm)",
    ),
    PolicyRule(
        action_type=PolicyAction.ACCESS_DATABASE.value,
        decision=PolicyDecisionType.REQUIRES_APPROVAL,
        risk_level=ChangeRisk.HIGH,
        required_approval=ApprovalLevel.USER,
        description="Direct database schema mutations or query execution",
    ),
    PolicyRule(
        action_type=PolicyAction.ACCESS_SECRET.value,
        decision=PolicyDecisionType.REQUIRES_APPROVAL,
        risk_level=ChangeRisk.CRITICAL,
        required_approval=ApprovalLevel.ADMIN,
        description="Read environment secrets or production API keys",
    ),
    PolicyRule(
        action_type=PolicyAction.DEPLOY.value,
        decision=PolicyDecisionType.REQUIRES_APPROVAL,
        risk_level=ChangeRisk.CRITICAL,
        required_approval=ApprovalLevel.TWO_PERSON,
        description="Deploy artifacts to staging or production environment",
    ),
    PolicyRule(
        action_type=PolicyAction.MODIFY_INFRASTRUCTURE.value,
        decision=PolicyDecisionType.REQUIRES_APPROVAL,
        risk_level=ChangeRisk.CRITICAL,
        required_approval=ApprovalLevel.ADMIN,
        description="Terraform, Kubernetes, or cloud resource provisioning",
    ),
    PolicyRule(
        action_type=PolicyAction.DELETE_PRODUCTION_DATA.value,
        decision=PolicyDecisionType.DENY,
        risk_level=ChangeRisk.CRITICAL,
        required_approval=ApprovalLevel.ADMIN,
        description="Destructive table truncation or production data deletion",
    ),
]


class PolicyEngine:
    def __init__(self, db: Database):
        self.db = db

    def evaluate_action(
        self,
        project_id: str,
        action_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> PolicyDecision:
        """
        Evaluates an agent action request against the project policy table (§45).
        Returns ALLOW, DENY, or REQUIRES_APPROVAL with risk and approval requirements.
        """
        normalized_action = action_type.lower().strip()

        # 1. Check project-specific override from database
        with self.db._get_connection() as conn:
            row = conn.execute(
                "SELECT action_type, decision, risk_level, required_approval, description FROM policies WHERE project_id = ? AND action_type = ?",
                (project_id, normalized_action),
            ).fetchone()

        if row:
            decision_type = PolicyDecisionType(row["decision"])
            risk_level = ChangeRisk(row["risk_level"])
            required_approval = ApprovalLevel(row["required_approval"])
            description = row["description"] or f"Configured project policy for '{normalized_action}'"
        else:
            # 2. Check default canonical rules
            default_rule = next((r for r in DEFAULT_POLICY_RULES if r.action_type == normalized_action), None)
            if default_rule:
                decision_type = default_rule.decision
                risk_level = default_rule.risk_level
                required_approval = default_rule.required_approval
                description = default_rule.description
            else:
                # Unknown action defaults to safe containment
                decision_type = PolicyDecisionType.REQUIRES_APPROVAL
                risk_level = ChangeRisk.HIGH
                required_approval = ApprovalLevel.USER
                description = f"Unregistered action type '{normalized_action}' requires human review."

        reason = f"Action '{normalized_action}' evaluated as {decision_type.value} (Risk: {risk_level.value}, Approval: {required_approval.value}). {description}"
        return PolicyDecision(
            action_type=normalized_action,
            decision=decision_type,
            risk_level=risk_level,
            required_approval=required_approval,
            reason=reason,
        )

    def list_policies(self, project_id: Optional[str] = None) -> List[PolicyRule]:
        """
        Lists effective policy rules for the project, merging defaults with custom overrides (§45).
        """
        rules_map: Dict[str, PolicyRule] = {r.action_type: r for r in DEFAULT_POLICY_RULES}

        if project_id:
            with self.db._get_connection() as conn:
                rows = conn.execute(
                    "SELECT action_type, decision, risk_level, required_approval, description FROM policies WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
                for r in rows:
                    rules_map[r["action_type"]] = PolicyRule(
                        action_type=r["action_type"],
                        decision=PolicyDecisionType(r["decision"]),
                        risk_level=ChangeRisk(r["risk_level"]),
                        required_approval=ApprovalLevel(r["required_approval"]),
                        description=r["description"] or "Custom project policy",
                    )

        return list(rules_map.values())

    def set_policy(
        self,
        project_id: str,
        action_type: str,
        decision: PolicyDecisionType,
        risk_level: ChangeRisk = ChangeRisk.MEDIUM,
        required_approval: ApprovalLevel = ApprovalLevel.USER,
        description: str = "",
    ):
        """
        Configures or overrides a policy rule for a project (§45).
        """
        normalized_action = action_type.lower().strip()
        rule_id = f"pol_{project_id}_{normalized_action}"
        created_at = current_utc_time()

        with self.db._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO policies (id, project_id, action_type, decision, risk_level, required_approval, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, action_type) DO UPDATE SET
                    decision=excluded.decision,
                    risk_level=excluded.risk_level,
                    required_approval=excluded.required_approval,
                    description=excluded.description
                """,
                (
                    rule_id,
                    project_id,
                    normalized_action,
                    decision.value,
                    risk_level.value,
                    required_approval.value,
                    description,
                    created_at,
                ),
            )
            conn.commit()

    def register_approver(
        self,
        project_id: str,
        name: str,
        role: str = "USER",
        is_admin: bool = False,
        approver_id: Optional[str] = None,
    ) -> Approver:
        """
        Registers a verified approver identity for a project (§45).
        """
        aid = approver_id or f"appr_{project_id}_{uuid.uuid4().hex[:8]}"
        approver = Approver(
            id=aid,
            project_id=project_id,
            name=name,
            role=role,
            is_admin=is_admin or (role.upper() == "ADMIN"),
            created_at=current_utc_time(),
        )
        self.db.save_approver(approver)
        return approver

    def list_approvers(self, project_id: str) -> List[Approver]:
        """
        Lists registered approvers for a project (§45).
        """
        return self.db.get_approvers(project_id)

    @staticmethod
    def infer_action_from_task(task_description: str) -> str:
        """
        Infers the canonical policy action or risk tier from a task description (§45).
        Evaluates task text against risk patterns. Defaults to 'unreviewed_task' (REQUIRES_APPROVAL)
        for arbitrary or unclassified free-text, ensuring free-text inference alone never auto-approves.
        """
        task_lower = task_description.lower()

        # 1. Destructive data operations (DENY / CRITICAL)
        if any(w in task_lower for w in [
            "delete production data", "drop table", "truncate", "destroy database", "wipe data",
            "purge", "erase data", "wipe all", "clear table", "drop database", "clean out table",
            "purge every row", "remove all rows", "delete from", "destroy table", "nullify records",
            "flush database", "flush db",
        ]):
            return PolicyAction.DELETE_PRODUCTION_DATA.value

        # 2. Deployments (TWO_PERSON / CRITICAL)
        elif any(w in task_lower for w in [
            "deploy", "release to prod", "production deployment", "promote to production",
            "push to prod", "ship to prod", "production release",
        ]):
            return PolicyAction.DEPLOY.value

        # 3. Infrastructure mutations (ADMIN / CRITICAL)
        elif any(w in task_lower for w in [
            "terraform", "kubernetes", "provision infrastructure", "cloud resource",
            "aws", "gcp", "azure", "cluster provision", "k8s manifest", "create bucket",
        ]):
            return PolicyAction.MODIFY_INFRASTRUCTURE.value

        # 4. Secrets access (ADMIN / CRITICAL)
        elif any(w in task_lower for w in [
            "read secret", "env secret", "api key", "access token", "credentials",
            "access_secret", "private key", "auth token", "vault secret",
        ]):
            return PolicyAction.ACCESS_SECRET.value

        # 5. Shell execution (USER / HIGH)
        elif any(w in task_lower for w in [
            "run shell", "bash", "execute shell", "terminal command", "exec ",
            "powershell", "spawn process", "system command", "run command",
        ]):
            return PolicyAction.EXECUTE_SHELL.value

        # 6. Third-party package installation (USER / MEDIUM)
        elif any(w in task_lower for w in [
            "pip install", "npm install", "install package", "add dependency",
            "yarn add", "cargo add", "npm i ",
        ]):
            return PolicyAction.INSTALL_PACKAGE.value

        # 7. Database mutations / migrations (USER / HIGH)
        elif any(w in task_lower for w in [
            "execute migration", "apply migration", "database migration", "schema migration",
            "alter table", "database mutation", "create table",
        ]):
            return PolicyAction.ACCESS_DATABASE.value

        # 8. Outbound network / HTTP requests (USER / MEDIUM)
        elif any(w in task_lower for w in [
            "http request", "fetch url", "access internet", "outbound network",
            "curl ", "wget ", "download from",
        ]):
            return PolicyAction.ACCESS_INTERNET.value

        # 9. Source code modifications (USER / MEDIUM)
        elif any(w in task_lower for w in [
            "build", "implement", "modify", "write", "patch", "create file",
            "code", "refactor", "edit file", "update code", "fix bug",
        ]):
            return PolicyAction.MODIFY_FILE.value

        # 10. Explicit read / inspection tasks
        elif any(w in task_lower for w in [
            "read repo", "read repository", "inspect repo", "inspect repository",
            "scan repo", "scan repository", "view file", "analyze architecture",
            "inspect repo files and ast", "design", "review security posture",
            "analyze", "audit",
        ]):
            return PolicyAction.READ_REPOSITORY.value

        # Safe default: unclassified free-text requires human review, NEVER auto-ALLOW
        return "unreviewed_task"

    @staticmethod
    def escalate_action_from_task(requested_action: Optional[str], task_description: str) -> str:
        """
        Applies keyword risk escalation heuristics to ensure free-text tasks are never auto-approved
        without human review and cannot hide dangerous operations behind safe action tags (§45).
        - If no explicit action_type is provided, unreviewed tasks require approval.
        - Keyword matches can only ESCALATE risk; they never downgrade or auto-ALLOW.
        """
        inferred = PolicyEngine.infer_action_from_task(task_description)

        if not requested_action:
            if inferred == PolicyAction.READ_REPOSITORY.value:
                return "unreviewed_task"
            return inferred

        req = requested_action.strip().lower()
        # If caller requested read_repository (auto-ALLOW), but keyword heuristic detected
        # any non-read action, escalate to the inferred risk tier.
        if req == PolicyAction.READ_REPOSITORY.value and inferred != PolicyAction.READ_REPOSITORY.value:
            return inferred

        return req


    def enforce_action(
        self,
        project_id: str,
        action_type: str,
        approved_by: Optional[Union[str, List[str]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str, PolicyDecision]:
        """
        Enforces governance policy for an action (§45).
        Returns (is_allowed, rationale_message, policy_decision).
        Blocks action on DENY, requires verified approver(s) matching the required
        ApprovalLevel tier on REQUIRES_APPROVAL, and allows on ALLOW.
        """
        decision = self.evaluate_action(project_id, action_type, context=context)

        # 1. DENY (unconditional)
        if decision.decision == PolicyDecisionType.DENY:
            reason = f"POLICY BLOCKED (DENY): Action '{action_type}' is prohibited. Rationale: {decision.reason}"
            return False, reason, decision

        # 2. REQUIRES_APPROVAL
        if decision.decision == PolicyDecisionType.REQUIRES_APPROVAL:
            # Parse approver identifiers (supports list or comma-separated string)
            approver_raw_list: List[str] = []
            if isinstance(approved_by, list):
                approver_raw_list = [str(a).strip() for a in approved_by if str(a).strip()]
            elif isinstance(approved_by, str) and approved_by.strip():
                approver_raw_list = [a.strip() for a in approved_by.split(",") if a.strip()]

            if not approver_raw_list:
                reason = (
                    f"POLICY REQUIRES APPROVAL: Action '{action_type}' requires '{decision.required_approval.value}' approval. "
                    f"Provide verified --approved-by <name> to execute."
                )
                return False, reason, decision

            # Verify every approver against known project approver identities
            verified_approvers = []
            for name in approver_raw_list:
                approver = self.db.get_approver(project_id, name)
                if not approver:
                    reason = f"POLICY BLOCKED: Approver '{name}' is not a recognized or registered approver for project '{project_id}'."
                    return False, reason, decision
                verified_approvers.append(approver)

            # Differentiate ApprovalLevel tiers
            if decision.required_approval == ApprovalLevel.USER:
                # USER tier: any verified registered approver is authorized
                names_str = ", ".join(a.name for a in verified_approvers)
                reason = f"POLICY APPROVED: Action '{action_type}' permitted with authorization from '{names_str}' (USER tier)."
                return True, reason, decision

            elif decision.required_approval == ApprovalLevel.ADMIN:
                # ADMIN tier: must have at least one approver flagged as an administrator
                admins = [a for a in verified_approvers if a.is_admin or a.role.upper() == "ADMIN"]
                if not admins:
                    names_str = ", ".join(a.name for a in verified_approvers)
                    reason = (
                        f"POLICY BLOCKED: Action '{action_type}' requires ADMIN-tier approval, "
                        f"but none of the provided approvers ({names_str}) have admin privileges."
                    )
                    return False, reason, decision
                names_str = ", ".join(a.name for a in admins)
                reason = f"POLICY APPROVED: Action '{action_type}' permitted with authorization from '{names_str}' (ADMIN tier)."
                return True, reason, decision

            elif decision.required_approval == ApprovalLevel.TWO_PERSON:
                # TWO_PERSON tier: requires two distinct, verified approvers recorded against this invocation
                distinct_ids = {a.id for a in verified_approvers}
                distinct_names = {a.name.lower() for a in verified_approvers}
                if len(distinct_ids) < 2 or len(distinct_names) < 2:
                    reason = (
                        f"POLICY BLOCKED: Action '{action_type}' requires TWO_PERSON approval. "
                        f"At least two distinct, verified approvers are required (received: {len(distinct_names)})."
                    )
                    return False, reason, decision
                names_str = ", ".join(a.name for a in verified_approvers)
                reason = f"POLICY APPROVED: Action '{action_type}' permitted with dual authorization from '{names_str}' (TWO_PERSON tier)."
                return True, reason, decision

            else:
                return True, f"POLICY APPROVED: Action '{action_type}' permitted.", decision

        # 3. ALLOW
        reason = f"POLICY ALLOWED: Action '{action_type}' permitted automatically ({decision.risk_level.value} risk)."
        return True, reason, decision

