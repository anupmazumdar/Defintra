import tempfile
import os
import pytest
from defintra.core.db.database import Database
from defintra.core.decisions.ledger import DecisionLedger
from defintra.core.models.entities import (
    ApprovalLevel,
    ArtifactState,
    ChangeRisk,
    Project,
    RejectedAlternative,
)


import gc

@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)
    yield db
    del db
    gc.collect()
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception:
        pass


def test_decision_ledger_record_and_preserve_disagreement(temp_db):
    project = Project(id="p1", name="Attendance System", objective="Test")
    temp_db.save_project(project)

    ledger = DecisionLedger(temp_db)
    dec = ledger.record_decision(
        project_id="p1",
        decision_id="D-101",
        title="Primary Database",
        decision="PostgreSQL",
        reason="ACID transactions and relational student-course schema",
        rejected_alternatives=[
            RejectedAlternative(
                alternative="MongoDB",
                reason_rejected="Document store causes integrity anomalies in grade computation",
                proposed_by="AI Model A",
            ),
            RejectedAlternative(
                alternative="MySQL",
                reason_rejected="Less robust JSON querying support",
                proposed_by="Architect",
            ),
        ],
    )

    history = ledger.get_decision_history("p1")
    assert len(history) == 1
    assert history[0].id == "D-101"
    assert len(history[0].rejected_alternatives) == 2
    assert history[0].rejected_alternatives[0].alternative == "MongoDB"


def test_decision_supersede_preserves_history(temp_db):
    project = Project(id="p1", name="Attendance System", objective="Test")
    temp_db.save_project(project)

    ledger = DecisionLedger(temp_db)
    d1 = ledger.record_decision(
        project_id="p1",
        decision_id="D-01",
        title="Cache Layer",
        decision="In-Memory Dict",
        reason="Fast prototyping",
    )

    # Supersede D-01 with Redis
    d2 = ledger.supersede_decision(
        old_decision_id="D-01",
        new_decision_id="D-02",
        new_title="Cache Layer",
        new_decision="Redis Cluster",
        new_reason="Scale to multiple API backend instances",
        project_id="p1",
    )

    history = ledger.get_decision_history("p1")
    assert len(history) == 2

    old_dec = next(d for d in history if d.id == "D-01")
    new_dec = next(d for d in history if d.id == "D-02")

    assert old_dec.status == ArtifactState.SUPERSEDED
    assert old_dec.superseded_by == "D-02"
    assert new_dec.status == ArtifactState.APPROVED
    assert len(new_dec.rejected_alternatives) >= 1
    assert "In-Memory Dict" in new_dec.rejected_alternatives[0].alternative
