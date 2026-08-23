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


def test_critical_risk_action_requires_approval(policy_db):
    engine = PolicyEngine(policy_db)

    # 1. Deploy action
    deploy_dec = engine.evaluate_action("proj_gov", "deploy")
    assert deploy_dec.decision == PolicyDecisionType.REQUIRES_APPROVAL
    assert deploy_dec.is_allowed is False
    assert deploy_dec.risk_level == ChangeRisk.CRITICAL
    assert deploy_dec.required_approval == ApprovalLevel.TWO_PERSON

    # 2. Access secret action
    secret_dec = engine.evaluate_action("proj_gov", "access_secret")
    assert secret_dec.decision == PolicyDecisionType.REQUIRES_APPROVAL
    assert secret_dec.is_allowed is False
    assert secret_dec.risk_level == ChangeRisk.CRITICAL
    assert secret_dec.required_approval == ApprovalLevel.ADMIN


def test_destructive_action_denied(policy_db):
    engine = PolicyEngine(policy_db)
    decision = engine.evaluate_action("proj_gov", "delete_production_data")

    assert decision.decision == PolicyDecisionType.DENY
    assert decision.is_allowed is False
    assert decision.risk_level == ChangeRisk.CRITICAL


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


def test_sandbox_evaluates_policy_engine(policy_db):
    sbx = SandboxManager(policy_db)
    sandbox = sbx.create_sandbox("proj_gov", task_id="task_123")

    read_dec = sbx.evaluate_sandbox_action("proj_gov", "read_repository")
    assert read_dec.decision == PolicyDecisionType.ALLOW

    gate_result = sbx.validate_governance_gate("proj_gov", sandbox)
    assert gate_result["checks"]["policy_governance_satisfied"] is True
