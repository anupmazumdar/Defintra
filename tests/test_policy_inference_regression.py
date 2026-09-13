"""
Regression tests for Issue 3: Free-text keyword matching & risk classification hardening.
Verifies that:
1. Rephrased dangerous tasks (e.g. "purge every row from the customers table") cannot
   bypass governance or execute without approval.
2. Free-text heuristics can only escalate risk; they cannot auto-approve unclassified tasks.
3. Callers attempting to disguise dangerous tasks as 'read_repository' are intercepted
   and escalated to the appropriate governed tier.
4. Arbitrary unclassified tasks without explicit action_type require human review by default.
"""

import pytest

from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.policy.engine import PolicyAction, PolicyEngine
from defintra.core.team.coordinator import AgentRole, TeamCoordinator


@pytest.fixture
def test_setup(tmp_path):
    db_file = tmp_path / "inference_test.db"
    db = Database(str(db_file))
    engine = DiscoveryEngine(db)
    project = engine.run_fast_path("Inference Hardening App", "Testing risk classification")
    coordinator = TeamCoordinator(db)
    pe = PolicyEngine(db)
    return db, project, coordinator, pe


@pytest.mark.parametrize(
    "rephrased_destructive_task",
    [
        "purge every row from the customers table",
        "erase data across all active databases",
        "clean out table users and nullify records",
        "wipe all customer profiles and flush db",
        "drop database production_primary",
    ],
)
def test_rephrased_destructive_tasks_inferred_as_delete_production_data(test_setup, rephrased_destructive_task):
    _, _, _, pe = test_setup
    inferred = pe.infer_action_from_task(rephrased_destructive_task)
    assert inferred == PolicyAction.DELETE_PRODUCTION_DATA.value


def test_rephrased_dangerous_task_cannot_execute_via_dispatch(test_setup):
    db, project, coordinator, _ = test_setup

    # Even without the literal phrase "delete production data", a rephrased destructive task
    # must be blocked and refused execution.
    dispatch = coordinator.dispatch_task(
        project_id=project.id,
        task_title="purge every row from the customers table",
        role=AgentRole.DATABASE_ENGINEER,
        execute=True,
    )
    assert dispatch["status"] == "BLOCKED_BY_POLICY"
    assert dispatch["policy_enforcement"]["allowed"] is False
    assert dispatch["policy_enforcement"]["action"] == PolicyAction.DELETE_PRODUCTION_DATA.value
    assert "POLICY BLOCKED (DENY)" in dispatch["policy_enforcement"]["reason"]


def test_disguised_read_action_is_escalated_and_blocked(test_setup):
    db, project, coordinator, _ = test_setup

    # Caller claims action_type="read_repository" (ALLOW), but payload is dangerous
    dispatch = coordinator.dispatch_task(
        project_id=project.id,
        task_title="purge every row from the customers table",
        role=AgentRole.BACKEND_ENGINEER,
        execute=True,
        action_type="read_repository",
    )
    assert dispatch["status"] == "BLOCKED_BY_POLICY"
    assert dispatch["policy_enforcement"]["allowed"] is False
    assert dispatch["policy_enforcement"]["action"] == PolicyAction.DELETE_PRODUCTION_DATA.value


def test_unclassified_free_text_without_action_type_requires_approval(test_setup):
    db, project, coordinator, _ = test_setup

    # Arbitrary task description with no explicit action_type must NOT auto-ALLOW
    dispatch = coordinator.dispatch_task(
        project_id=project.id,
        task_title="perform complex untyped data manipulation",
        role=AgentRole.BACKEND_ENGINEER,
        execute=True,
        action_type=None,
    )
    assert dispatch["status"] == "BLOCKED_BY_POLICY"
    assert dispatch["policy_enforcement"]["allowed"] is False
    assert dispatch["policy_enforcement"]["action"] == "unreviewed_task"
    assert "REQUIRES APPROVAL" in dispatch["policy_enforcement"]["reason"]


def test_explicit_valid_read_action_succeeds(test_setup):
    db, project, coordinator, _ = test_setup

    dispatch = coordinator.dispatch_task(
        project_id=project.id,
        task_title="Inspect repository AST and architecture definitions",
        role=AgentRole.SOFTWARE_ARCHITECT,
        execute=True,
        action_type="read_repository",
    )
    assert dispatch["status"] == "COMPLETED"
    assert dispatch["policy_enforcement"]["allowed"] is True
