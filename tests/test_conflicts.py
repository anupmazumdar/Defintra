import pytest
from defintra.core.conflicts.engine import ConflictEngine
from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.models.entities import (
    ApprovalLevel,
    ArtifactState,
    ChangeRisk,
    Decision,
)


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_conflicts.db"
    return Database(str(db_file))


def test_conflict_detection_and_resolution(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Conflict App", "Build offline mobile app")

    # Add conflicting decision
    dec = Decision(
        id="D-STATELESS_test",
        project_id=project.id,
        title="Architecture",
        decision="Enforce stateless only with no local storage allowed",
        reason="Pure server-side rendering mandate",
        status=ArtifactState.APPROVED,
        approval_level=ApprovalLevel.USER,
        change_risk=ChangeRisk.HIGH,
    )
    test_db.save_decision(dec)

    conflict_engine = ConflictEngine(test_db)
    confs = conflict_engine.detect_conflicts(project.id)

    assert len(confs) >= 1
    target_conflict = confs[0]
    assert target_conflict.status == "OPEN"

    # Resolve conflict
    resolved = conflict_engine.resolve_conflict(
        project_id=project.id,
        conflict_id=target_conflict.id,
        resolution_notes="Approved local SQLite caching for offline mode",
        winning_entity_id=target_conflict.entity_a_ref,
    )
    assert resolved.status == "RESOLVED"
    assert resolved.resolution is not None
