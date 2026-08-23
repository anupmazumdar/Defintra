import pytest

from defintra.core.contracts.versioning import ContractVersioningEngine
from defintra.core.db.database import Database
from defintra.core.decisions.adr import ADRGenerator
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.tasks.scheduler import TaskScheduler
from defintra.core.testing.vulnerabilities import VulnerabilityLifecycleManager
from defintra.mcp.server import DefintraMCPServer


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_adr_sched.db"
    return Database(str(db_file))


def test_adr_generation(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("ADR Demo", "Build multi-tenant cloud storage with encryption")

    decs = test_db.get_decisions(project.id)
    assert len(decs) >= 1

    adr_gen = ADRGenerator(test_db)
    adr_md = adr_gen.generate_adr(project.id, decs[0].id)

    assert f"# {decs[0].id}:" in adr_md
    assert "## Multi-Dimensional Evaluation Matrix (§11)" in adr_md
    assert "## Preserved Disagreement & Rejected Alternatives (§10)" in adr_md
    assert "## Traceability & Evidence (§9)" in adr_md


def test_task_scheduler(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Scheduler Demo", "Build microservices fintech payment gateway")

    scheduler = TaskScheduler(test_db)
    sched = scheduler.schedule_project(project.id)

    assert sched.total_phases == 5
    assert len(sched.phases) == 5
    assert len(sched.critical_path) >= 3
    assert sched.parallelism_factor > 1.0

    phase1 = sched.phases[0]
    assert phase1.phase_number == 1
    assert "Database" in phase1.name
    assert len(phase1.parallel_tracks) >= 2


def test_contract_semantic_versioning(test_db):
    v_engine = ContractVersioningEngine(test_db)

    old_api = {
        "/users": {"method": "GET", "response": {"id": "str", "name": "str"}},
        "/auth/login": {"method": "POST"},
    }

    # Compatible addition -> MINOR bump
    new_api_minor = {
        "/users": {"method": "GET", "response": {"id": "str", "name": "str"}},
        "/auth/login": {"method": "POST"},
        "/users/profile": {"method": "GET"},
    }
    diff_minor = v_engine.analyze_contract_evolution("API-001", old_api, new_api_minor, "1.0.0")
    assert diff_minor.is_breaking is False
    assert diff_minor.change_level == "MINOR"
    assert diff_minor.suggested_version == "1.1.0"

    # Dropped route -> MAJOR bump
    new_api_major = {
        "/auth/login": {"method": "POST"},
    }
    diff_major = v_engine.analyze_contract_evolution("API-001", old_api, new_api_major, "1.0.0")
    assert diff_major.is_breaking is True
    assert diff_major.change_level == "MAJOR"
    assert diff_major.suggested_version == "2.0.0"


def test_vulnerability_regression_generator(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Security Demo", "Build medical HIPAA healthcare portal")

    vuln_mgr = VulnerabilityLifecycleManager(test_db)
    suite_code = vuln_mgr.generate_persistent_regression_suite(project.id)

    assert "def test_sql_injection_defense" in suite_code
    assert "def test_unauthenticated_endpoint_rejection" in suite_code
    assert "CWE-89" in suite_code


def test_mcp_extended_tools_adrs_and_scheduling(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("MCP Schedule Demo", "Build e-commerce cart")

    mcp = DefintraMCPServer(str(test_db.db_path))

    adrs_res = mcp.generate_adrs(project.id)
    assert "adrs" in adrs_res

    sched_res = mcp.schedule_phases(project.id)
    assert sched_res["total_phases"] == 5

    contracts_res = mcp.validate_contracts(project.id)
    assert "contracts" in contracts_res
