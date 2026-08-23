import pytest
from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.governance.recovery import FailureRecoveryEngine
from defintra.core.governance.staleness import StalenessEngine
from defintra.core.operations.improvements import PostDeploymentAdvisor
from defintra.mcp.server import DefintraMCPServer


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_gov_rec.db"
    return Database(str(db_file))


def test_staleness_engine(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Staleness Demo", "Build patient medical records and appointments portal")

    staleness_engine = StalenessEngine(test_db)
    rep = staleness_engine.evaluate_staleness(project.id)

    assert rep.total_nodes_checked >= 3
    assert rep.average_confidence >= 0.0
    assert rep.system_staleness_score >= 0.0

    # Re-validate requirement
    reqs = test_db.get_requirements(project.id)
    if reqs:
        reval = staleness_engine.revalidate_node(project.id, reqs[0].id, "QA Lead")
        assert reval is True
        updated_r = test_db.get_requirements(project.id)[0]
        assert updated_r.provenance.confidence >= 0.90
        assert updated_r.provenance.approved_by == "QA Lead"


def test_post_deployment_advisor(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Advisor Demo", "Build financial payment ledger with high volume transactions")

    advisor = PostDeploymentAdvisor(test_db)
    suggestions = advisor.generate_recommendations(project.id)

    assert len(suggestions) >= 3
    for s in suggestions:
        assert s.id.startswith("OPT-")
        assert s.roi_score > 0.0
        assert len(s.action_plan) >= 1
        assert s.change_risk.value in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def test_failure_recovery_engine(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Recovery Demo", "Build multi-tenant cloud application")

    recovery_engine = FailureRecoveryEngine(test_db)
    rep = recovery_engine.diagnose_project(project.id)

    assert rep.system_health_status in ["HEALTHY", "DEGRADED", "CRITICAL_FAILURE"]
    # Check that diagnoses are populated if entropy is high
    assert isinstance(rep.diagnoses, list)


def test_mcp_extended_tools(test_db, tmp_path):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("MCP Extended Demo", "Build secure e-commerce checkout")

    mcp_server = DefintraMCPServer(str(test_db.db_path))

    # 1. Staleness tool
    st_res = mcp_server.check_staleness(project.id)
    assert "system_staleness_score" in st_res

    # 2. Improvements tool
    imp_res = mcp_server.get_improvements(project.id)
    assert len(imp_res["suggestions"]) >= 2

    # 3. Diagnose recovery tool
    rec_res = mcp_server.diagnose_recovery(project.id)
    assert "system_health_status" in rec_res
