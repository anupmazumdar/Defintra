import gc
import os
import tempfile

import pytest

from defintra.core.discovery.engine import DiscoveryEngine
from defintra.mcp.server import DefintraMCPServer


@pytest.fixture
def mcp_server():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    server = DefintraMCPServer(db_path)
    engine = DiscoveryEngine(server.db)
    engine.run_fast_path("MCP Project", "Build a customer feedback analytics portal.")

    yield server

    del engine
    del server
    gc.collect()
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception:
        pass


def test_mcp_get_project_state(mcp_server):
    state = mcp_server.get_project_state()
    assert "project_id" in state
    assert state["name"] == "MCP Project"
    assert "health" in state
    assert state["summary"]["requirements_count"] >= 3


def test_mcp_propose_decision(mcp_server):
    res = mcp_server.propose_decision(
        decision_id="D-MCP-01",
        title="Vector Database",
        decision="Qdrant",
        reason="Native filtering and high search throughput",
        rejected_alternatives=[
            {"alternative": "Pinecone", "reason_rejected": "Closed-source / vendor lock-in"}
        ],
    )
    assert res["status"] == "PROPOSED"
    assert res["decision_id"] == "D-MCP-01"
    assert res["requires_user_approval"] is True


def test_mcp_compile_context(mcp_server):
    ctx = mcp_server.compile_context("Implement user authentication and JWT login flow", target_format="claude")
    assert "compiled_data" in ctx
    assert "rendered_context" in ctx
    assert "<defintra_context>" in ctx["rendered_context"]


def test_mcp_expanded_tools(mcp_server, tmp_path):
    import shutil
    from pathlib import Path

    # 1. Test conflicts
    confs = mcp_server.detect_conflicts()
    assert isinstance(confs, list)

    # 2. Test generate test pack
    pack = mcp_server.generate_test_pack(pack_type="human")
    assert "Human Testing Pack" in pack["content"]

    # 3. Test scan repository inside workspace
    mock_sub = Path(".defintra/test_mcp_mock_sub").resolve()
    mock_sub.mkdir(parents=True, exist_ok=True)
    (mock_sub / "test.py").write_text("print('hello')", encoding="utf-8")
    try:
        scan_res = mcp_server.scan_repository(str(mock_sub), name="Sub Repo")
        assert scan_res["files_scanned"] >= 1
    finally:
        shutil.rmtree(mock_sub, ignore_errors=True)

    # 4. Test path traversal rejected outside workspace
    traversal_res = mcp_server.scan_repository(str(tmp_path), name="External Target")
    assert "error" in traversal_res
    assert "Path traversal rejected" in traversal_res["error"]

    # 5. Test secret redaction on decision proposal
    dec_res = mcp_server.propose_decision(
        decision_id="D-SEC-01",
        title="Payment API Key",
        decision="Use Stripe key sk-proj-111222333444555666777",
        reason="Admin access password: 'SecretAdminPassword123'",
        rejected_alternatives=[],
    )
    assert dec_res["status"] == "PROPOSED"
    assert "sk-proj-" not in dec_res["message"]
    saved_dec = mcp_server.db.get_decisions(mcp_server.db.get_first_project().id)
    sec_dec = [d for d in saved_dec if d.id == "D-SEC-01"][0]
    assert "sk-proj-" not in sec_dec.decision
    assert "[REDACTED_SECRET:" in sec_dec.decision

