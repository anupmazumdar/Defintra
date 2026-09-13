"""
Regression tests for Issue 2: Approver identity verification and ApprovalLevel tier differentiation.
Verifies that:
1. Random/unregistered approver strings fail authorization.
2. Valid approver identities stored in project database succeed for their tier.
3. ADMIN-tier actions require at least one verified approver with admin privileges.
4. TWO_PERSON-tier actions require two distinct, verified approvers (rejecting single approvers or repeated names).
5. Unconditional DENY actions (e.g. delete_production_data) remain blocked regardless of approver credentials.
"""

import pytest

from defintra.core.db.database import Database
from defintra.core.models.entities import ApprovalLevel, ChangeRisk, Project
from defintra.core.policy.engine import PolicyDecisionType, PolicyEngine


@pytest.fixture
def gov_engine(tmp_path):
    db_file = tmp_path / "gov_test.db"
    db = Database(str(db_file))
    project = Project(id="proj_sec_test", name="Security Test Project", objective="Testing Approver Tiers")
    db.save_project(project)  # Seeds DevLead (ADMIN), SecurityLead (ADMIN), Engineer (USER)
    return PolicyEngine(db)


def test_unregistered_approver_string_is_rejected(gov_engine):
    # Action requiring USER approval (modify_file)
    allowed, reason, dec = gov_engine.enforce_action(
        project_id="proj_sec_test",
        action_type="modify_file",
        approved_by="RandomAttacker",
    )
    assert allowed is False
    assert "not a recognized or registered approver" in reason


def test_user_tier_accepts_any_registered_approver(gov_engine):
    # Engineer (USER role) can approve USER-tier action
    allowed, reason, dec = gov_engine.enforce_action(
        project_id="proj_sec_test",
        action_type="modify_file",
        approved_by="Engineer",
    )
    assert allowed is True
    assert "POLICY APPROVED" in reason
    assert "USER tier" in reason


def test_admin_tier_rejects_non_admin_and_accepts_admin(gov_engine):
    # access_secret requires ADMIN tier
    # 1. Non-admin rejection
    allowed_user, reason_user, _ = gov_engine.enforce_action(
        project_id="proj_sec_test",
        action_type="access_secret",
        approved_by="Engineer",
    )
    assert allowed_user is False
    assert "admin privileges" in reason_user

    # 2. Admin acceptance
    allowed_admin, reason_admin, _ = gov_engine.enforce_action(
        project_id="proj_sec_test",
        action_type="access_secret",
        approved_by="SecurityLead",
    )
    assert allowed_admin is True
    assert "POLICY APPROVED" in reason_admin
    assert "ADMIN tier" in reason_admin


def test_two_person_tier_strict_dual_approver_enforcement(gov_engine):
    # deploy requires TWO_PERSON approval
    # 1. Single approver fails
    allowed_1, reason_1, _ = gov_engine.enforce_action(
        project_id="proj_sec_test",
        action_type="deploy",
        approved_by="SecurityLead",
    )
    assert allowed_1 is False
    assert "TWO_PERSON" in reason_1

    # 2. Same approver repeated twice fails (not distinct)
    allowed_repeat, reason_repeat, _ = gov_engine.enforce_action(
        project_id="proj_sec_test",
        action_type="deploy",
        approved_by="SecurityLead, SecurityLead",
    )
    assert allowed_repeat is False
    assert "distinct" in reason_repeat

    # 3. One valid and one unknown approver fails
    allowed_mixed, reason_mixed, _ = gov_engine.enforce_action(
        project_id="proj_sec_test",
        action_type="deploy",
        approved_by="SecurityLead, GhostUser",
    )
    assert allowed_mixed is False
    assert "not a recognized or registered approver" in reason_mixed

    # 4. Two distinct verified approvers (comma-separated string) succeed
    allowed_dual, reason_dual, _ = gov_engine.enforce_action(
        project_id="proj_sec_test",
        action_type="deploy",
        approved_by="SecurityLead, DevLead",
    )
    assert allowed_dual is True
    assert "POLICY APPROVED" in reason_dual
    assert "TWO_PERSON tier" in reason_dual

    # 5. Two distinct verified approvers (list of strings) succeed
    allowed_list, reason_list, _ = gov_engine.enforce_action(
        project_id="proj_sec_test",
        action_type="deploy",
        approved_by=["DevLead", "SecurityLead"],
    )
    assert allowed_list is True
    assert "POLICY APPROVED" in reason_list


def test_custom_registered_approver(gov_engine):
    # Register new approver with custom ID and role
    gov_engine.register_approver(
        project_id="proj_sec_test",
        name="ComplianceDirector",
        role="ADMIN",
        is_admin=True,
    )

    allowed, reason, _ = gov_engine.enforce_action(
        project_id="proj_sec_test",
        action_type="modify_infrastructure",
        approved_by="ComplianceDirector",
    )
    assert allowed is True
    assert "POLICY APPROVED" in reason


def test_delete_production_data_unconditionally_denied(gov_engine):
    allowed, reason, _ = gov_engine.enforce_action(
        project_id="proj_sec_test",
        action_type="delete_production_data",
        approved_by="DevLead, SecurityLead",
    )
    assert allowed is False
    assert "POLICY BLOCKED (DENY)" in reason
