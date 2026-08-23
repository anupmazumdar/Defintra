"""
Autonomous Agent Policy & Governance Engine (§45).
Enforces security boundaries, risk-tiered action governance,
and approval requirements before an autonomous agent executes actions.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from defintra.core.db.database import Database
from defintra.core.models.entities import ApprovalLevel, ChangeRisk, current_utc_time


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
