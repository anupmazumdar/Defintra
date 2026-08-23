import tempfile
import os
import pytest
from defintra.core.db.database import Database
from defintra.core.models.entities import (
    ArtifactState,
    Decision,
    EARSPattern,
    EntityType,
    Evidence,
    Project,
    Provenance,
    RejectedAlternative,
    Requirement,
    RequirementPriority,
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


def test_project_crud(temp_db):
    project = Project(
        id="proj_test",
        name="Test Project",
        objective="Verify SQLite database CRUD",
        domain="SAAS",
        source_type="idea",
    )
    temp_db.save_project(project)

    retrieved = temp_db.get_project("proj_test")
    assert retrieved is not None
    assert retrieved.name == "Test Project"
    assert retrieved.domain == "SAAS"


def test_requirement_with_evidence(temp_db):
    project = Project(id="p1", name="P1", objective="Testing")
    temp_db.save_project(project)

    req = Requirement(
        id="R-1",
        project_id="p1",
        title="Login",
        description="The System shall authenticate users.",
        ears_pattern=EARSPattern.UBIQUITOUS,
        priority=RequirementPriority.CRITICAL,
        status=ArtifactState.PROPOSED,
        affected_components=["Frontend", "Backend"],
        provenance=Provenance(source="User PRD", confidence=0.95),
        evidence=[
            Evidence(
                id="ev-1",
                target_entity_type=EntityType.REQUIREMENT,
                target_entity_id="R-1",
                evidence_type="USER_PRD",
                description="Explicitly requested in section 1",
                source="PRD",
            )
        ],
    )
    temp_db.save_requirement(req)

    retrieved_reqs = temp_db.get_requirements("p1")
    assert len(retrieved_reqs) == 1
    assert retrieved_reqs[0].title == "Login"
    assert retrieved_reqs[0].affected_components == ["Frontend", "Backend"]
    assert len(retrieved_reqs[0].evidence) == 1
    assert retrieved_reqs[0].evidence[0].source == "PRD"


def test_decision_and_preserved_disagreement(temp_db):
    project = Project(id="p1", name="P1", objective="Testing")
    temp_db.save_project(project)

    dec = Decision(
        id="D-1",
        project_id="p1",
        title="Database",
        decision="PostgreSQL",
        reason="ACID compliance",
        rejected_alternatives=[
            RejectedAlternative(alternative="MongoDB", reason_rejected="Lacks SQL ACID joins")
        ],
        status=ArtifactState.APPROVED,
    )
    temp_db.save_decision(dec)

    retrieved_decs = temp_db.get_decisions("p1")
    assert len(retrieved_decs) == 1
    assert retrieved_decs[0].decision == "PostgreSQL"
    assert len(retrieved_decs[0].rejected_alternatives) == 1
    assert retrieved_decs[0].rejected_alternatives[0].alternative == "MongoDB"
