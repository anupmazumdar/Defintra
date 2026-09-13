"""
Regression tests for Issue 6: Path Traversal / Unconfined File Writes During Rule Export.

Verifies:
1. export_agent_rules rejects paths outside workspace root (relative traversal and absolute paths).
2. export_all rejects output directories outside workspace root.
3. export_agent_rules and export_all succeed when targets reside inside workspace root.
4. Custom workspace_root parameter is respected and strictly enforced.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.export.exporter import Exporter


@pytest.fixture
def project_with_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_file = workspace / ".defintra" / "project.db"
    db_file.parent.mkdir()
    db = Database(str(db_file))
    engine = DiscoveryEngine(db)
    project = engine.run_fast_path("Export Test", "Verify export path traversal restrictions.")
    return db, project.id, workspace


def test_export_agent_rules_confinement(project_with_workspace):
    db, project_id, workspace = project_with_workspace
    exporter = Exporter(db, project_id, workspace_root=workspace)

    # 1. Valid export inside workspace succeeds
    valid_path = workspace / ".cursorrules"
    result = exporter.export_agent_rules("cursor", str(valid_path))
    assert Path(result).resolve() == valid_path.resolve()
    assert valid_path.exists()

    # Valid export into subdirectory inside workspace succeeds
    sub_dir_path = workspace / "rules" / "AGENTS.md"
    result = exporter.export_agent_rules("agents", str(sub_dir_path))
    assert Path(result).resolve() == sub_dir_path.resolve()
    assert sub_dir_path.exists()

    # 2. Path traversal escaping workspace root is rejected
    traversal_path = str(workspace / ".." / "evil.cursorrules")
    with pytest.raises(ValueError, match="Path traversal rejected"):
        exporter.export_agent_rules("cursor", traversal_path)

    # 3. Relative path traversal escaping workspace is rejected
    with pytest.raises(ValueError, match="Path traversal rejected"):
        exporter.export_agent_rules("cursor", "../../outside.cursorrules")

    # 4. Absolute path outside workspace is rejected
    outside_dir = tempfile.mkdtemp()
    try:
        outside_file = os.path.join(outside_dir, "stolen.cursorrules")
        with pytest.raises(ValueError, match="Path traversal rejected"):
            exporter.export_agent_rules("cursor", outside_file)
    finally:
        shutil.rmtree(outside_dir, ignore_errors=True)


def test_export_all_confinement(project_with_workspace):
    db, project_id, workspace = project_with_workspace
    exporter = Exporter(db, project_id, workspace_root=workspace)

    # 1. Valid export directory inside workspace succeeds
    valid_dir = workspace / "export_output"
    files = exporter.export_all(str(valid_dir))
    assert "dir.json" in files
    assert Path(files["dir.json"]).exists()
    assert valid_dir.exists()

    # 2. Traversal path escaping workspace root is rejected
    traversal_dir = str(workspace / ".." / "escaped_export")
    with pytest.raises(ValueError, match="Path traversal rejected"):
        exporter.export_all(traversal_dir)

    # 3. Relative traversal path escaping workspace root is rejected
    with pytest.raises(ValueError, match="Path traversal rejected"):
        exporter.export_all("../../escaped_export")

    # 4. Absolute path outside workspace root is rejected
    outside_dir = tempfile.mkdtemp()
    try:
        with pytest.raises(ValueError, match="Path traversal rejected"):
            exporter.export_all(outside_dir)
    finally:
        shutil.rmtree(outside_dir, ignore_errors=True)
