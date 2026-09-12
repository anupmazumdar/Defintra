"""
Regression tests for Finding 3: Real Subprocess Execution Isolation & Staging Sandbox.
Verifies that:
1. Commands execute strictly within sandbox.worktree_path (cwd confinement).
2. Ambient host secrets (OPENAI_API_KEY, ANTHROPIC_API_KEY, AWS_*, tokens) are scrubbed.
3. Execution timeout is strictly enforced (TIMED_OUT status).
4. Policy gates block unauthorized commands from executing.
5. Path escape violations prevent command execution.
"""

import os
from pathlib import Path

from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.sandbox.manager import SandboxManager


def test_sandbox_subprocess_execution_and_cwd_confinement(tmp_path):
    db_file = tmp_path / "project.db"
    db = Database(str(db_file))
    engine = DiscoveryEngine(db)
    project = engine.run_fast_path("Sandbox Subprocess Test", "Test command execution in staging.")

    sbx_base = tmp_path / "sandboxes"
    mgr = SandboxManager(db, base_dir=str(sbx_base))
    sbx = mgr.create_sandbox(project.id, task_id="subproc_task", isolation_type="directory")

    assert sbx.worktree_path is not None
    wt_dir = Path(sbx.worktree_path).resolve()

    # 1. Execute command and verify cwd confinement
    py_check_cwd = "python -c \"import os, pathlib; print('CONFINED_CWD:', pathlib.Path.cwd().resolve())\""
    res = mgr.execute_sandbox_action(
        sbx,
        action_type="read_repository",
        context={"command": py_check_cwd},
    )
    assert res["allowed"] is True
    assert res["status"] == "EXECUTED"
    assert res["returncode"] == 0
    assert str(wt_dir) in res["stdout"]


def test_sandbox_environment_variable_scrubbing(tmp_path):
    db_file = tmp_path / "project.db"
    db = Database(str(db_file))
    engine = DiscoveryEngine(db)
    project = engine.run_fast_path("Env Scrub Test", "Test secret stripping.")

    sbx_base = tmp_path / "sandboxes"
    mgr = SandboxManager(db, base_dir=str(sbx_base))
    sbx = mgr.create_sandbox(project.id, task_id="env_task", isolation_type="directory")

    # Set ambient secrets in host environment
    os.environ["OPENAI_API_KEY"] = "sk-proj-supersecretkey123"
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-supersecretkey456"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "verysecretawskey789"
    os.environ["GITHUB_TOKEN"] = "ghp_123456789012345678901234567890123456"

    try:
        py_check_env = "python -c \"import os; print('FOUND_SECRETS:', [k for k in os.environ if any(s in k for s in ['OPENAI', 'ANTHROPIC', 'AWS_SECRET', 'GITHUB_TOKEN'])])\""
        res = mgr.execute_sandbox_action(
            sbx,
            action_type="read_repository",
            context={"command": py_check_env},
        )
        assert res["allowed"] is True
        assert res["status"] == "EXECUTED"
        assert "FOUND_SECRETS: []" in res["stdout"]
    finally:
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
        os.environ.pop("GITHUB_TOKEN", None)


def test_sandbox_execution_timeout_enforcement(tmp_path):
    db_file = tmp_path / "project.db"
    db = Database(str(db_file))
    engine = DiscoveryEngine(db)
    project = engine.run_fast_path("Timeout Test", "Test process timeout.")

    sbx_base = tmp_path / "sandboxes"
    mgr = SandboxManager(db, base_dir=str(sbx_base))
    sbx = mgr.create_sandbox(project.id, task_id="timeout_task", isolation_type="directory")

    # Run command that exceeds short timeout (1 second timeout, sleeping for 4 seconds)
    py_sleep = "python -c \"import time; time.sleep(4)\""
    res = mgr.execute_sandbox_action(
        sbx,
        action_type="read_repository",
        context={"command": py_sleep, "timeout": 1},
    )
    assert res["allowed"] is False
    assert res["status"] == "TIMED_OUT"
    assert "timed out" in res["reason"]


def test_sandbox_policy_gate_blocks_execution(tmp_path):
    db_file = tmp_path / "project.db"
    db = Database(str(db_file))
    engine = DiscoveryEngine(db)
    project = engine.run_fast_path("Policy Gate Test", "Test policy blocks dangerous actions.")

    sbx_base = tmp_path / "sandboxes"
    mgr = SandboxManager(db, base_dir=str(sbx_base))
    sbx = mgr.create_sandbox(project.id, task_id="policy_task", isolation_type="directory")

    # Destructive action with command is denied by policy
    res = mgr.execute_sandbox_action(
        sbx,
        action_type="delete_production_data",
        context={"command": "python -c \"print('DANGEROUS')\""},
    )
    assert res["allowed"] is False
    assert res["status"] == "BLOCKED"
    assert "command" not in res  # Command was never executed


def test_sandbox_path_escape_blocks_execution(tmp_path):
    db_file = tmp_path / "project.db"
    db = Database(str(db_file))
    engine = DiscoveryEngine(db)
    project = engine.run_fast_path("Path Escape Test", "Test path confinement.")

    sbx_base = tmp_path / "sandboxes"
    mgr = SandboxManager(db, base_dir=str(sbx_base))
    sbx = mgr.create_sandbox(project.id, task_id="escape_task", isolation_type="directory")

    outside_file = tmp_path / "outside.txt"
    res = mgr.execute_sandbox_action(
        sbx,
        action_type="write_code",
        context={"file": str(outside_file), "command": "python -c \"print('ESCAPE')\""},
    )
    assert res["allowed"] is False
    assert res["status"] == "BLOCKED"
    assert "Path escape violation" in res["reason"]
    assert "command" not in res  # Command was never executed
