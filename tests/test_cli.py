import tempfile
import os
import gc
import json
import shutil
import pytest
from typer.testing import CliRunner
from defintra.cli.main import app

runner = CliRunner()


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


def test_cli_expanded_commands(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    try:
        db_file = os.path.join(tmpdir, "project.db")
        monkeypatch.setattr("defintra.cli.main.get_db", lambda: __import__("defintra.core.db.database", fromlist=["Database"]).Database(db_file))

        runner.invoke(app, ["init", "Test Suite App"])

        # 1. Compile
        res_compile = runner.invoke(app, ["compile", "Build student registration API", "--target", "claude", "--role", "BACKEND_ENGINEER"])
        assert res_compile.exit_code == 0
        assert "Context Compilation Metrics" in res_compile.output
        assert "<defintra_context>" in res_compile.output

        # 2. Conflicts
        res_conflicts = runner.invoke(app, ["conflicts"])
        assert res_conflicts.exit_code == 0

        # 3. Test Pack
        res_test_pack = runner.invoke(app, ["test-pack", "--type", "human"])
        assert res_test_pack.exit_code == 0
        assert "Human Testing Pack" in res_test_pack.output

        # 4. Sandbox
        res_sandbox = runner.invoke(app, ["sandbox", "create", "--task", "task_01"])
        assert res_sandbox.exit_code == 0
        assert "Isolated Sandbox Created" in res_sandbox.output

        # 5. Scan
        res_scan = runner.invoke(app, ["scan", tmpdir, "--name", "Tmp Scanned"])
        assert res_scan.exit_code == 0
        assert "Repository Ingested Successfully" in res_scan.output

        # 6. Team Dispatch
        res_team = runner.invoke(app, ["team", "Design API Gateway", "--role", "SOFTWARE_ARCHITECT"])
        assert res_team.exit_code == 0
        assert "AI Team Collaboration Dispatch" in res_team.output

        # 7. Incident Traceback
        res_incident = runner.invoke(app, ["incident", "Database connection timeout during authentication"])
        assert res_incident.exit_code == 0
        assert "Production Incident Traceback" in res_incident.output

        # 8. Runbook
        res_runbook = runner.invoke(app, ["runbook", "--type", "backup"])
        assert res_runbook.exit_code == 0
        assert "Operations Runbook" in res_runbook.output

        # 9. Stability Budget
        res_stab = runner.invoke(app, ["stability"])
        assert res_stab.exit_code == 0
        assert "Architecture Stability Budget" in res_stab.output

        # 10. Spec Diff
        f1 = os.path.join(tmpdir, "dir1.json")
        f2 = os.path.join(tmpdir, "dir2.json")
        with open(f1, "w") as f:
            json.dump({"requirements": [], "contracts": [], "decisions": []}, f)
        with open(f2, "w") as f:
            json.dump({"requirements": [{"id": "R-1", "title": "Auth", "description": "System shall auth"}], "contracts": [], "decisions": []}, f)

        res_diff = runner.invoke(app, ["diff", f1, f2])
        assert res_diff.exit_code == 0
        assert "Added Requirements" in res_diff.output
    finally:
        gc.collect()
        shutil.rmtree(tmpdir, ignore_errors=True)
