import tempfile
import os
import pytest
from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.export.exporter import Exporter
from defintra.schemas.validator import validate_dir


import gc

@pytest.fixture
def populated_project():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)
    engine = DiscoveryEngine(db)
    project = engine.run_fast_path("Campus System", "Build an offline-first college attendance system.")
    yield db, project.id
    del engine
    del db
    gc.collect()
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception:
        pass


def test_dir_schema_validation(populated_project):
    db, project_id = populated_project
    exporter = Exporter(db, project_id)

    dir_payload = exporter.build_dir_payload()
    is_valid, errors = validate_dir(dir_payload)
    assert is_valid is True, f"DIR Schema validation errors: {errors}"
    assert dir_payload["schema_version"] == "1.0.0"
    assert dir_payload["project"]["id"] == project_id


def test_markdown_spec_generation(populated_project):
    db, project_id = populated_project
    exporter = Exporter(db, project_id)

    md = exporter.generate_markdown_spec()
    assert "# Campus System — Project Specification" in md
    assert "## 2. Specification Health & Entropy Status" in md
    assert "## 3. Requirements (EARS Syntax)" in md
    assert "## 4. Decision Ledger (with Preserved Disagreement)" in md
    assert "```mermaid" in md


def test_export_all_files(populated_project):
    db, project_id = populated_project
    exporter = Exporter(db, project_id)

    with tempfile.TemporaryDirectory() as out_dir:
        files = exporter.export_all(out_dir)
        assert "dir.json" in files
        assert "spec.md" in files
        assert "requirements.json" in files
        assert "decisions.json" in files
        assert os.path.exists(files["dir.json"])
        assert os.path.exists(files["spec.md"])
