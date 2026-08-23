import pytest
from defintra.core.db.database import Database
from defintra.core.diff.engine import SpecDiffEngine
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.governance.stability import StabilityBudgetEngine
from defintra.export.exporter import Exporter


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_stab_diff.db"
    return Database(str(db_file))


def test_stability_budget_engine(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Stability App", "Build analytics backend with PostgreSQL")

    stab_engine = StabilityBudgetEngine(test_db)
    rep = stab_engine.evaluate_stability(project.id)

    assert rep.churn_index >= 0.0
    assert rep.stability_score <= 100.0
    assert "total_decisions" in rep.metrics


def test_spec_diff_engine(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Diff App", "Build student directory with search")

    exporter = Exporter(test_db, project.id)
    dir_v1 = exporter.build_dir_payload()

    # Create modified dir_v2
    import copy
    dir_v2 = copy.deepcopy(dir_v1)

    # Add a requirement
    dir_v2["requirements"].append({
        "id": "R-NEW-01",
        "title": "Search Filtering",
        "description": "The system shall filter records by tag",
        "ears_pattern": "UBIQUITOUS",
        "priority": "MEDIUM",
        "status": "PROPOSED",
        "category": "FUNCTIONAL",
        "affected_components": [],
        "constraints": [],
        "acceptance_criteria": [],
    })

    # Supersede a decision
    if dir_v2["decisions"]:
        dir_v2["decisions"][0]["status"] = "SUPERSEDED"
        dir_v2["decisions"][0]["superseded_by"] = "D-NEW-99"

    diff_report = SpecDiffEngine.diff_dirs(dir_v1, dir_v2)

    assert len(diff_report.added_requirements) == 1
    assert len(diff_report.superseded_decisions) >= 1
    md = diff_report.render_markdown()
    assert "# Defintra Semantic Specification Diff" in md
    assert "Added Requirements" in md
