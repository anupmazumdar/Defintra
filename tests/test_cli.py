import tempfile
import os
import pytest
from typer.testing import CliRunner
from defintra.cli.main import app

runner = CliRunner()


import gc
import shutil

def test_cli_init_and_status(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    try:
        db_file = os.path.join(tmpdir, "project.db")
        monkeypatch.setattr("defintra.cli.main.get_db", lambda: __import__("defintra.core.db.database", fromlist=["Database"]).Database(db_file))

        # Init
        res_init = runner.invoke(app, ["init", "Test Campus App"])
        assert res_init.exit_code == 0
        assert "Defintra initialized successfully" in res_init.output

        # Status
        res_status = runner.invoke(app, ["status"])
        assert res_status.exit_code == 0
        assert "Test Campus App" in res_status.output
        assert "Spec Health Score" in res_status.output
    finally:
        gc.collect()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_cli_analyze_and_graph(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    try:
        db_file = os.path.join(tmpdir, "project.db")
        monkeypatch.setattr("defintra.cli.main.get_db", lambda: __import__("defintra.core.db.database", fromlist=["Database"]).Database(db_file))

        # Analyze
        res_analyze = runner.invoke(app, ["analyze", "Build a microservice for attendance management with QR verification."])
        assert res_analyze.exit_code == 0
        assert "Analysis Summary" in res_analyze.output
        assert "Generated Requirements (EARS Syntax)" in res_analyze.output

        # Graph ASCII
        res_graph = runner.invoke(app, ["graph"])
        assert res_graph.exit_code == 0
        assert "Knowledge & Dependency Graph" in res_graph.output

        # Graph Mermaid
        res_mermaid = runner.invoke(app, ["graph", "--format", "mermaid"])
        assert res_mermaid.exit_code == 0
        assert "graph TD" in res_mermaid.output

        # Audit
        res_audit = runner.invoke(app, ["audit"])
        assert res_audit.exit_code == 0
        assert "Discovery Audit Log" in res_audit.output

        # Export
        export_dir = os.path.join(tmpdir, "export")
        res_export = runner.invoke(app, ["export", "--out", export_dir])
        assert res_export.exit_code == 0
        assert os.path.exists(os.path.join(export_dir, "dir.json"))
        assert os.path.exists(os.path.join(export_dir, "spec.md"))
    finally:
        gc.collect()
        shutil.rmtree(tmpdir, ignore_errors=True)
