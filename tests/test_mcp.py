import tempfile
import os
import pytest
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.mcp.server import DefintraMCPServer


import gc

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
    ctx = mcp_server.compile_context("Implement user authentication and JWT login flow")
    assert "included_requirements" in ctx
    assert "explainable_exclusions" in ctx
    assert len(ctx["included_requirements"]) >= 1
