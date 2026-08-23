import pytest

from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.operations.feedback import IncidentTracer
from defintra.core.operations.runbooks import RunbookGenerator


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_ops.db"
    return Database(str(db_file))


def test_incident_tracer(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Incident App", "Build authentication and database records service")

    tracer = IncidentTracer(test_db)
    report = tracer.trace_incident(
        incident_text="NullPointerException in authentication service during token verification",
        project_id=project.id,
    )

    assert len(report.mapped_nodes) > 0
    assert len(report.recommended_regression_tests) > 0
    assert report.blast_radius_risk in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def test_runbook_generator(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Runbook App", "Build high availability database service")

    gen = RunbookGenerator(test_db)

    # 1. Backup Runbook
    backup_rb = gen.generate_runbook(project.id, "BACKUP")
    assert "# Operations Runbook: Database Backup & Restore" in backup_rb

    # 2. Disaster Recovery Runbook
    dr_rb = gen.generate_runbook(project.id, "FAILOVER")
    assert "Failover & Disaster Recovery" in dr_rb

    # 3. Rollback Runbook
    rb_rb = gen.generate_runbook(project.id, "ROLLBACK")
    assert "Zero-Downtime Rollback Procedure" in rb_rb
