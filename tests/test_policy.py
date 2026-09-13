import pytest

from defintra.core.db.database import Database
from defintra.core.models.entities import ApprovalLevel, ChangeRisk, Project
from defintra.core.policy.engine import PolicyDecisionType, PolicyEngine
from defintra.core.sandbox.manager import SandboxManager


@pytest.fixture
def policy_db(tmp_path):
    db_file = tmp_path / "policy_test.db"
    db = Database(str(db_file))
    project = Project(id="proj_gov", name="Governance Project", objective="Testing policy enforcement")
    db.save_project(project)
    return db


def test_low_risk_action_allows_automatically(policy_db):
    engine = PolicyEngine(policy_db)
    decision = engine.evaluate_action("proj_gov", "read_repository")

    assert decision.decision == PolicyDecisionType.ALLOW
    assert decision.is_allowed is True
    assert decision.risk_level == ChangeRisk.LOW
    assert decision.required_approval == ApprovalLevel.NONE

    # Enforcement check
    allowed, reason, dec = engine.enforce_action("proj_gov", "read_repository")
    assert allowed is True
    assert "POLICY ALLOWED" in reason


def test_critical_risk_action_requires_approval(policy_db):
    engine = PolicyEngine(policy_db)

    # 1. Deploy action (TWO_PERSON tier)
    deploy_dec = engine.evaluate_action("proj_gov", "deploy")
    assert deploy_dec.decision == PolicyDecisionType.REQUIRES_APPROVAL
    assert deploy_dec.is_allowed is False
    assert deploy_dec.risk_level == ChangeRisk.CRITICAL
    assert deploy_dec.required_approval == ApprovalLevel.TWO_PERSON

    # Unapproved execution blocked
    allowed, reason, _ = engine.enforce_action("proj_gov", "deploy")
    assert allowed is False
    assert "REQUIRES APPROVAL" in reason

    # Unregistered / unknown approver string fails
    allowed_unknown, reason_unknown, _ = engine.enforce_action("proj_gov", "deploy", approved_by="UnknownHacker")
    assert allowed_unknown is False
    assert "not a recognized or registered approver" in reason_unknown

    # Registered single approver fails TWO_PERSON requirement
    allowed_single, reason_single, _ = engine.enforce_action("proj_gov", "deploy", approved_by="SecurityLead")
    assert allowed_single is False
    assert "TWO_PERSON" in reason_single

    # Same approver repeated twice fails TWO_PERSON requirement
    allowed_dup, reason_dup, _ = engine.enforce_action("proj_gov", "deploy", approved_by="SecurityLead, SecurityLead")
    assert allowed_dup is False
    assert "distinct" in reason_dup

    # Two distinct registered approvers succeed
    allowed_auth, reason_auth, _ = engine.enforce_action("proj_gov", "deploy", approved_by="SecurityLead, DevLead")
    assert allowed_auth is True
    assert "POLICY APPROVED" in reason_auth


def test_admin_tier_approval_differentiation(policy_db):
    engine = PolicyEngine(policy_db)

    # access_secret requires ADMIN tier
    secret_dec = engine.evaluate_action("proj_gov", "access_secret")
    assert secret_dec.decision == PolicyDecisionType.REQUIRES_APPROVAL
    assert secret_dec.required_approval == ApprovalLevel.ADMIN

    # Non-admin approver (Engineer) fails
    allowed_user, reason_user, _ = engine.enforce_action("proj_gov", "access_secret", approved_by="Engineer")
    assert allowed_user is False
    assert "admin privileges" in reason_user

    # Admin approver (SecurityLead) succeeds
    allowed_admin, reason_admin, _ = engine.enforce_action("proj_gov", "access_secret", approved_by="SecurityLead")
    assert allowed_admin is True
    assert "POLICY APPROVED" in reason_admin


def test_destructive_action_denied(policy_db):
    engine = PolicyEngine(policy_db)
    decision = engine.evaluate_action("proj_gov", "delete_production_data")

    assert decision.decision == PolicyDecisionType.DENY
    assert decision.is_allowed is False
    assert decision.risk_level == ChangeRisk.CRITICAL

    # Enforcement strictly blocks even if verified admin approvers are provided
    allowed, reason, _ = engine.enforce_action("proj_gov", "delete_production_data", approved_by="SecurityLead, DevLead")
    assert allowed is False
    assert "POLICY BLOCKED (DENY)" in reason


def test_custom_project_policy_override(policy_db):
    engine = PolicyEngine(policy_db)

    # Custom override: strictly DENY shell execution for this project
    engine.set_policy(
        project_id="proj_gov",
        action_type="execute_shell",
        decision=PolicyDecisionType.DENY,
        risk_level=ChangeRisk.HIGH,
        required_approval=ApprovalLevel.ADMIN,
        description="Shell execution strictly prohibited in compliance environment",
    )

    decision = engine.evaluate_action("proj_gov", "execute_shell")
    assert decision.decision == PolicyDecisionType.DENY
    assert "strictly prohibited" in decision.reason

    allowed, reason, _ = engine.enforce_action("proj_gov", "execute_shell")
    assert allowed is False


def test_infer_action_from_task():
    assert PolicyEngine.infer_action_from_task("Drop table users and wipe data") == "delete_production_data"
    assert PolicyEngine.infer_action_from_task("Deploy release to prod cluster") == "deploy"
    assert PolicyEngine.infer_action_from_task("Fetch env secret for stripe key") == "access_secret"
    assert PolicyEngine.infer_action_from_task("Inspect repo files and AST") == "read_repository"
    assert PolicyEngine.infer_action_from_task("Build responsive authentication view") == "modify_file"


def test_sandbox_evaluates_and_enforces_policy(policy_db):
    sbx = SandboxManager(policy_db)
    sandbox = sbx.create_sandbox("proj_gov", task_id="task_123")

    assert "read_repository" in sandbox.allowed_actions
    assert "delete_production_data" in sandbox.denied_actions

    # Execute allowed action without command payload (policy evaluation only)
    res1 = sbx.execute_sandbox_action(sandbox, "read_repository")
    assert res1["allowed"] is True
    assert res1["status"] == "POLICY_APPROVED"
    assert res1["executed"] is False

    # Execute denied action
    res2 = sbx.execute_sandbox_action(sandbox, "delete_production_data")
    assert res2["allowed"] is False
    assert res2["status"] == "BLOCKED"
    assert res2["executed"] is False

    # Execute approval-required action without vs with approval
    res3 = sbx.execute_sandbox_action(sandbox, "deploy")
    assert res3["allowed"] is False
    assert res3["status"] in ("BLOCKED", "POLICY_DENIED")
    assert res3["executed"] is False

    res4_fail = sbx.execute_sandbox_action(sandbox, "deploy", approved_by="SecurityLead")
    assert res4_fail["allowed"] is False
    assert res4_fail["status"] == "POLICY_DENIED"

    res4 = sbx.execute_sandbox_action(sandbox, "deploy", approved_by="SecurityLead, DevLead")
    assert res4["allowed"] is True
    assert res4["status"] == "POLICY_APPROVED"
    assert res4["executed"] is False

    gate_result = sbx.validate_governance_gate("proj_gov", sandbox)
    assert gate_result["checks"]["policy_governance_satisfied"] is True
