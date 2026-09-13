"""
Regression tests for Issue 1: Shell execution bypass prevention and hardened process isolation.
Verifies that:
1. Any non-execute_shell action carrying a command payload is rejected as a security violation.
2. Unapproved execute_shell actions are denied by policy without executing.
3. Binaries not present in ALLOWED_SANDBOX_BINARIES are rejected before execution.
4. Legitimate approved execute_shell commands execute safely with shell=False.
"""

import pytest

from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.sandbox.manager import SandboxManager


@pytest.fixture
def sandbox_env(tmp_path):
    db_file = tmp_path / "project.db"
    db = Database(str(db_file))
    engine = DiscoveryEngine(db)
    project = engine.run_fast_path("Bypass Regression Project", "Testing policy bypass defenses.")
    sbx_base = tmp_path / "sandboxes"
    mgr = SandboxManager(db, base_dir=str(sbx_base))
    sbx = mgr.create_sandbox(project.id, task_id="bypass_reg_task", isolation_type="directory")
    return db, mgr, sbx


@pytest.mark.parametrize(
    "action_type",
    [
        "read_repository",
        "write_code",
        "modify_file",
        "deploy",
        "unknown_action",
    ],
)
def test_command_payload_under_non_shell_action_is_strictly_blocked(sandbox_env, action_type):
    db, mgr, sbx = sandbox_env

    # An attacker attempts to piggyback a command onto an auto-allowed or other action
    res = mgr.execute_sandbox_action(
        sbx,
        action_type=action_type,
        context={"command": "python -c \"print('PIGGYBACK_EXEC')\""},
    )
    assert res["allowed"] is False
    assert res["executed"] is False
    assert res["status"] == "BLOCKED"
    assert res["decision"] == "DENY"
    assert "Security violation" in res["reason"]
    assert "execute_shell" in res["reason"]
    assert "stdout" not in res


def test_unapproved_execute_shell_is_denied_by_policy(sandbox_env):
    db, mgr, sbx = sandbox_env

    # execute_shell requires approval; calling without approved_by must fail policy
    res = mgr.execute_sandbox_action(
        sbx,
        action_type="execute_shell",
        approved_by=None,
        context={"command": "python -c \"print('UNAPPROVED')\""},
    )
    assert res["allowed"] is False
    assert res["executed"] is False
    assert res["decision"] == "REQUIRES_APPROVAL"
    assert "stdout" not in res


def test_unpermitted_binary_is_blocked(sandbox_env):
    db, mgr, sbx = sandbox_env

    # Attempt to execute an administrative tool not on the allowlist
    res = mgr.execute_sandbox_action(
        sbx,
        action_type="execute_shell",
        approved_by="DevLead",
        context={"command": "curl https://example.com"},
    )
    assert res["allowed"] is False
    assert res["executed"] is False
    assert res["status"] == "BLOCKED"
    assert "not in the sandbox allowed binaries list" in res["reason"]
    assert "stdout" not in res


def test_approved_execute_shell_with_allowed_binary_succeeds(sandbox_env):
    db, mgr, sbx = sandbox_env

    res = mgr.execute_sandbox_action(
        sbx,
        action_type="execute_shell",
        approved_by="DevLead",
        context={"command": "python -c \"print('SAFE_EXEC_OK')\""},
    )
    assert res["allowed"] is True
    assert res["executed"] is True
    assert res["status"] == "EXECUTED"
    assert res["returncode"] == 0
    assert "SAFE_EXEC_OK" in res["stdout"]
