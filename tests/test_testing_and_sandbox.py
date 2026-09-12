import pytest

from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.sandbox.manager import SandboxManager
from defintra.core.testing.test_packs import TestPackGenerator


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_testing_sandbox.db"
    return Database(str(db_file))


def test_test_pack_generator(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Testing Demo", "Build payment checkout workflow")

    gen = TestPackGenerator(test_db)

    # 1. Human testing pack
    human_pack = gen.generate_human_testing_pack(project.id)
    assert "# Human Testing Pack" in human_pack
    assert "## 2. Requirement Acceptance Verification Walkthrough" in human_pack

    # 2. Automated test suite
    auto_tests = gen.generate_automated_test_scaffold(project.id)
    assert "import pytest" in auto_tests
    assert "def test_requirement_" in auto_tests

    # 3. Security regression suite
    sec_tests = gen.generate_security_regression_suite(project.id)
    assert "Security Regression Suite" in sec_tests


def test_sandbox_manager(test_db, tmp_path):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Sandbox Demo", "Build microservice architecture")

    sbx_dir = tmp_path / "sandboxes"
    mgr = SandboxManager(test_db, base_dir=str(sbx_dir))

    sbx = mgr.create_sandbox(project.id, task_id="auth_service_impl")
    assert sbx.sandbox_id.startswith("sbx_")
    assert "auth_service_impl" in sbx.branch_name
    assert len(sbx.snapshot_hash) == 16

    gate = mgr.validate_governance_gate(project.id, sbx, test_results_pass=True, security_sign_off=True)
    assert gate["governance_status"] == "APPROVED"
    assert gate["ready_for_merge"] is True


def test_sandbox_worktree_isolation_and_confinement(test_db, tmp_path):
    from pathlib import Path
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Sandbox Worktree Demo", "Build microservice architecture")

    sbx_dir = tmp_path / "sandboxes"
    mgr = SandboxManager(test_db, base_dir=str(sbx_dir))

    # 1. Create worktree sandbox
    sbx = mgr.create_sandbox(project.id, task_id="feature_branch", isolation_type="worktree")
    assert sbx.worktree_path is not None
    assert Path(sbx.worktree_path).exists()

    # 2. Block action attempting path escape
    escaped_action = mgr.execute_sandbox_action(
        sbx,
        action_type="write_code",
        context={"path": str(tmp_path / "outside_sandbox.py")},
    )
    assert escaped_action["allowed"] is False
    assert escaped_action["status"] == "BLOCKED"
    assert "Path escape violation" in escaped_action["reason"]

    # 3. Allow action inside worktree path (policy check)
    inside_path = Path(sbx.worktree_path) / "app.py"
    allowed_action = mgr.execute_sandbox_action(
        sbx,
        action_type="read_repository",
        context={"path": str(inside_path)},
    )
    assert allowed_action["allowed"] is True
    assert allowed_action["status"] == "POLICY_APPROVED"
    assert allowed_action["executed"] is False

    # 3b. Real file modification inside sandbox worktree
    mod_action = mgr.execute_sandbox_action(
        sbx,
        action_type="modify_file",
        approved_by="Engineer",
        context={"file": "app.py", "content": "print('hello world')\n"},
    )
    assert mod_action["allowed"] is True
    assert mod_action["status"] == "EXECUTED"
    assert mod_action["executed"] is True
    assert inside_path.exists()
    assert inside_path.read_text(encoding="utf-8") == "print('hello world')\n"

    # 4. Clean up sandbox
    cleaned = mgr.cleanup_sandbox(sbx)
    assert cleaned is True
    assert sbx.status == "CLEANED"
    assert not Path(sbx.worktree_path).exists()

