import tempfile
import os
import gc
import pytest
from defintra.core.db.database import Database
from defintra.core.graph.engine import ProjectGraph
from defintra.core.models.entities import (
    ArtifactState,
    Component,
    Decision,
    DependencyEdge,
    EARSPattern,
    EntityType,
    Project,
    Provenance,
    Requirement,
    RequirementPriority,
)


@pytest.fixture
def populated_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)

    project = Project(id="proj_1", name="Test Graph Project", objective="Test Graph Engine")
    db.save_project(project)

    # Components
    c1 = Component(id="COMP-AUTH", project_id="proj_1", name="Auth Service", component_type="AUTH", stability_state=ArtifactState.APPROVED)
    c2 = Component(id="COMP-DB", project_id="proj_1", name="Database", component_type="DATABASE", stability_state=ArtifactState.APPROVED)
    c3 = Component(id="COMP-UI", project_id="proj_1", name="Frontend", component_type="FRONTEND", stability_state=ArtifactState.PROPOSED)
    c4 = Component(id="COMP-BILLING", project_id="proj_1", name="Billing Service", component_type="PAYMENT", stability_state=ArtifactState.PROPOSED)
    db.save_component(c1)
    db.save_component(c2)
    db.save_component(c3)
    db.save_component(c4)

    # Decisions
    d1 = Decision(id="D-1", project_id="proj_1", title="Database Engine", decision="PostgreSQL", reason="ACID", status=ArtifactState.APPROVED, affected_components=["Database"])
    db.save_decision(d1)

    # Requirements
    r1 = Requirement(
        id="R-1",
        project_id="proj_1",
        title="User Login",
        description="The System shall authenticate users.",
        ears_pattern=EARSPattern.UBIQUITOUS,
        priority=RequirementPriority.CRITICAL,
        affected_components=["Auth Service"],
        provenance=Provenance(source="User", confidence=0.95),
    )
    r2 = Requirement(
        id="R-2",
        project_id="proj_1",
        title="Dashboard View",
        description="WHEN logged in, the System shall display user attendance.",
        ears_pattern=EARSPattern.EVENT_DRIVEN,
        affected_components=["Frontend"],
        provenance=Provenance(source="User", confidence=0.8),
    )
    db.save_requirement(r1)
    db.save_requirement(r2)

    # Dependencies: D-1 -> COMP-DB -> COMP-AUTH -> R-1 -> R-2 -> COMP-UI
    db.save_dependency(DependencyEdge(id="dep1", project_id="proj_1", source_type=EntityType.DECISION, source_id="D-1", target_type=EntityType.COMPONENT, target_id="COMP-DB"))
    db.save_dependency(DependencyEdge(id="dep2", project_id="proj_1", source_type=EntityType.COMPONENT, source_id="COMP-DB", target_type=EntityType.COMPONENT, target_id="COMP-AUTH"))
    db.save_dependency(DependencyEdge(id="dep3", project_id="proj_1", source_type=EntityType.COMPONENT, source_id="COMP-AUTH", target_type=EntityType.REQUIREMENT, target_id="R-1"))
    db.save_dependency(DependencyEdge(id="dep4", project_id="proj_1", source_type=EntityType.REQUIREMENT, source_id="R-1", target_type=EntityType.REQUIREMENT, target_id="R-2"))
    db.save_dependency(DependencyEdge(id="dep5", project_id="proj_1", source_type=EntityType.REQUIREMENT, source_id="R-2", target_type=EntityType.COMPONENT, target_id="COMP-UI"))

    yield db, "proj_1"

    del db
    gc.collect()
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception:
        pass


def test_blast_radius_calculation(populated_db):
    db, project_id = populated_db
    p_graph = ProjectGraph(db, project_id)

    # Calculate blast radius if D-1 changes
    report = p_graph.calculate_blast_radius("D-1")
    assert report.total_blast_count >= 4
    affected_ids = [n["id"] for n in report.affected_nodes]
    assert "COMP-DB" in affected_ids
    assert "COMP-AUTH" in affected_ids
    assert "R-1" in affected_ids
    assert "R-2" in affected_ids
    assert "COMP-UI" in affected_ids

    # Unaffected components must include Billing Service
    assert "Billing Service" in report.unaffected_components


def test_reverse_traceability_origin(populated_db):
    db, project_id = populated_db
    p_graph = ProjectGraph(db, project_id)

    # Trace upstream ancestors for COMP-UI
    origins = p_graph.trace_origin("COMP-UI")
    origin_ids = [o["id"] for o in origins]
    assert "D-1" in origin_ids
    assert "R-1" in origin_ids
    assert "R-2" in origin_ids


def test_visual_renderings(populated_db):
    db, project_id = populated_db
    p_graph = ProjectGraph(db, project_id)

    mermaid = p_graph.to_mermaid()
    assert "graph TD" in mermaid
    assert "D-1" in mermaid
    assert "COMP-DB" in mermaid

    ascii_tree = p_graph.to_ascii_tree()
    assert "├──" in ascii_tree
