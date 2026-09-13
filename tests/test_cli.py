import gc
import json
import os
import shutil
import tempfile

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
        res_scan = runner.invoke(app, ["scan", tmpdir, "--name", "Tmp Scanned", "--allow-external"])
        assert res_scan.exit_code == 0
        assert "Repository Ingested Successfully" in res_scan.output

        # 6. Team Dispatch
        res_team = runner.invoke(app, ["team", "Design API Gateway", "--role", "SOFTWARE_ARCHITECT"])
        assert res_team.exit_code == 0
        assert "AI Team Collaboration" in res_team.output
        assert "Agent Execution Response Snippet" in res_team.output

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


def test_cli_governance_and_new_commands(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    try:
        db_file = os.path.join(tmpdir, "project.db")
        monkeypatch.setattr("defintra.cli.main.get_db", lambda: __import__("defintra.core.db.database", fromlist=["Database"]).Database(db_file))

        # 1. Initialize healthy project with low entropy
        runner.invoke(app, ["init", "Gov Suite App"])
        runner.invoke(app, ["analyze", "Build an offline-first mobile app for college attendance."])

        db = __import__("defintra.core.db.database", fromlist=["Database"]).Database(db_file)
        proj = db.get_first_project()
        decs = db.get_decisions(proj.id)
        first_dec_id = decs[0].id if decs else "D-001"

        # Test ADR command (Success & Failure)
        res_adr_all = runner.invoke(app, ["adr", "--out", os.path.join(tmpdir, "adr")])
        assert res_adr_all.exit_code == 0
        assert "Architecture Decision Records" in res_adr_all.output

        res_adr_single = runner.invoke(app, ["adr", "--id", first_dec_id])
        assert res_adr_single.exit_code == 0
        assert "Multi-Dimensional Evaluation Matrix" in res_adr_single.output

        # Test Schedule command
        res_sched = runner.invoke(app, ["schedule"])
        assert res_sched.exit_code == 0
        assert "Multi-Agent Implementation Roadmap" in res_sched.output
        assert "Phase 1" in res_sched.output

        # Test Contracts command
        res_contracts = runner.invoke(app, ["contracts"])
        assert res_contracts.exit_code == 0
        assert "Shared Component Contracts" in res_contracts.output

        # Test Staleness command (Success, Revalidate Success, Revalidate Failure)
        res_stale = runner.invoke(app, ["staleness"])
        assert res_stale.exit_code == 0
        assert "Confidence Decay & Staleness Report" in res_stale.output

        res_reval_ok = runner.invoke(app, ["staleness", "--revalidate", first_dec_id])
        assert res_reval_ok.exit_code == 0
        assert "successfully re-validated" in res_reval_ok.output

        res_reval_fail = runner.invoke(app, ["staleness", "--revalidate", "NON_EXISTENT_NODE_XYZ"])
        assert res_reval_fail.exit_code == 1
        assert "not found" in res_reval_fail.output

        # Test Advise command
        res_advise = runner.invoke(app, ["advise"])
        assert res_advise.exit_code == 0
        assert "Post-Deployment Continuous Improvement Advisory" in res_advise.output

        # Test Recover command
        res_recover = runner.invoke(app, ["recover"])
        assert res_recover.exit_code == 0
        assert "System Failure Diagnosis & Recovery Engine" in res_recover.output

        # Test Snapshot command (Create, List, Restore, Restore Failure)
        res_snap_create = runner.invoke(app, ["snapshot", "--create", "v1.0.0", "--desc", "Test v1 checkpoint"])
        assert res_snap_create.exit_code == 0
        assert "Cryptographic Snapshot Created" in res_snap_create.output
        assert "SHA-256 Checksum" in res_snap_create.output

        res_snap_list = runner.invoke(app, ["snapshot"])
        assert res_snap_list.exit_code == 0
        assert "Immutable Project Snapshots" in res_snap_list.output

        res_snap_restore_fail = runner.invoke(app, ["snapshot", "--restore", "non_existent_snapshot_id"])
        assert res_snap_restore_fail.exit_code == 1
        assert "not found" in res_snap_restore_fail.output

        # Test Metrics command
        res_metrics = runner.invoke(app, ["metrics"])
        assert res_metrics.exit_code == 0
        assert "Production Metrics & SLO Performance" in res_metrics.output
        assert "Service Availability" in res_metrics.output

        # Test Gate command (Happy path & Blocked path)
        # Set entropy to 0.40 so gate check passes
        db = __import__("defintra.core.db.database", fromlist=["Database"]).Database(db_file)
        proj = db.get_first_project()
        proj.spec_entropy = 0.40
        db.save_project(proj)

        res_gate_pass = runner.invoke(app, ["gate"])
        assert res_gate_pass.exit_code == 0
        assert "APPROVED / READY" in res_gate_pass.output
        assert "Safe to merge and deploy" in res_gate_pass.output

        # Now simulate an entropy breach > 0.60 to test Gate BLOCKED path
        proj.spec_entropy = 0.85
        db.save_project(proj)

        res_gate_block = runner.invoke(app, ["gate"])
        assert res_gate_block.exit_code == 1
        assert "ACTION REQUIRED" in res_gate_block.output
        assert "Release blocked by governance policies" in res_gate_block.output

        # Test Events command & Route command
        runner.invoke(app, ["team", "Design API Gateway", "--role", "SOFTWARE_ARCHITECT"])
        res_events = runner.invoke(app, ["events"])
        assert res_events.exit_code == 0
        assert "Multi-Agent Structured Coordination Event Log" in res_events.output

        res_route = runner.invoke(app, ["route", "BACKEND_ENGINEER", "--complexity", "HIGH"])
        assert res_route.exit_code == 0
        assert "AI Model Routing Recommendation" in res_route.output
        # Test Policy CLI commands (§45)
        res_policy_check_allow = runner.invoke(app, ["policy", "check", "read_repository"])
        assert res_policy_check_allow.exit_code == 0
        assert "ALLOW" in res_policy_check_allow.output

        res_policy_check_approval = runner.invoke(app, ["policy", "check", "deploy"])
        assert res_policy_check_approval.exit_code == 0
        assert "REQUIRES_APPROVAL" in res_policy_check_approval.output

        res_policy_list = runner.invoke(app, ["policy", "list"])
        assert res_policy_list.exit_code == 0
        assert "Autonomous Agent Governance & Action Policy Table" in res_policy_list.output

        # Test Team execution & policy block
        res_team_exec = runner.invoke(app, ["team", "Design microservice API", "--role", "BACKEND_ENGINEER", "--execute"])
        assert res_team_exec.exit_code == 0
        assert "AI Execution Engine" in res_team_exec.output

        res_team_blocked = runner.invoke(app, ["team", "delete production data and drop all tables", "--role", "BACKEND_ENGINEER", "--execute"])
        assert res_team_blocked.exit_code == 1
        assert "EXECUTION REFUSED BY POLICY ENGINE" in res_team_blocked.output

        # Test Sandbox policy evaluation and real execution
        res_sbx_eval = runner.invoke(app, ["sandbox", "exec", "read_repository"])
        assert res_sbx_eval.exit_code == 0
        assert "Sandbox Policy Evaluation" in res_sbx_eval.output
        assert "POLICY_APPROVED" in res_sbx_eval.output

        # Test Sandbox real command execution requires execute_shell with approval
        res_sbx_exec = runner.invoke(app, ["sandbox", "exec", "execute_shell", "--approved-by", "DevLead", "-c", "python -c \"print('SBX_OK')\""])
        assert res_sbx_exec.exit_code == 0
        assert "Sandbox Action Executed" in res_sbx_exec.output
        assert "SBX_OK" in res_sbx_exec.output

        # Test Sandbox command payload under non-shell action is rejected
        res_sbx_bypass = runner.invoke(app, ["sandbox", "exec", "read_repository", "-c", "python -c \"print('FAIL')\""])
        assert res_sbx_bypass.exit_code == 1
        assert "SANDBOX ACTION REFUSED BY POLICY ENGINE" in res_sbx_bypass.output

        # Test Sandbox authorize command
        res_sbx_auth = runner.invoke(app, ["sandbox", "authorize", "read_repository"])
        assert res_sbx_auth.exit_code == 0
        assert "Policy Evaluation: APPROVED" in res_sbx_auth.output

        res_sbx_exec_deny = runner.invoke(app, ["sandbox", "exec", "delete_production_data"])
        assert res_sbx_exec_deny.exit_code == 1
        assert "SANDBOX ACTION REFUSED BY POLICY ENGINE" in res_sbx_exec_deny.output

        # Test Benchmark CLI commands (§40, §46)
        res_bm_run = runner.invoke(app, ["benchmark", "run", "--input", "Build real-time collaborative code editor with WebSockets"])
        assert res_bm_run.exit_code == 0
        assert "Empirical Intelligence Benchmark Comparison" in res_bm_run.output
        assert "Requirements Coverage" in res_bm_run.output

        res_bm_hist = runner.invoke(app, ["benchmark", "history"])
        assert res_bm_hist.exit_code == 0
        assert "Benchmark Historical Trends" in res_bm_hist.output

        # Test failure case on missing project
        res_gate_no_proj = runner.invoke(app, ["gate", "--project", "non_existent_proj_id"])
        assert res_gate_no_proj.exit_code == 1
    finally:
        gc.collect()
        shutil.rmtree(tmpdir, ignore_errors=True)


