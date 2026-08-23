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
