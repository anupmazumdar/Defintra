import io
import json
import threading
import time
import urllib.request
import pytest
from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.ui.server import DefintraAPIHandler, ThreadingHTTPServer


@pytest.fixture
def running_ui_server(tmp_path):
    db_file = tmp_path / "test_ui.db"
    db = Database(str(db_file))
    engine = DiscoveryEngine(db)
    engine.run_fast_path("UI Test Project", "Build customer portal with React and FastAPI")

    DefintraAPIHandler.db_path = str(db_file)
    # Find free port
    server = ThreadingHTTPServer(("127.0.0.1", 0), DefintraAPIHandler)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    server.shutdown()
    server.server_close()


def test_ui_get_html_and_state(running_ui_server):
    # 1. HTML index
    with urllib.request.urlopen(f"{running_ui_server}/") as res:
        assert res.status == 200
        html = res.read().decode("utf-8")
        assert "Defintra Control Center" in html

    # 2. State API
    with urllib.request.urlopen(f"{running_ui_server}/api/state") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert data["project"]["name"] == "UI Test Project"
        assert len(data["requirements"]) >= 3
        assert "health" in data

    # 3. Graph API
    with urllib.request.urlopen(f"{running_ui_server}/api/graph") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "nodes" in data
        assert len(data["nodes"]) >= 3


def test_ui_post_actions(running_ui_server):
    # 1. Answer unknown
    req = urllib.request.Request(
        f"{running_ui_server}/api/answer",
        data=json.dumps({"unknown_id": "UNK-001_ui_test_project", "answer": "PostgreSQL database"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert data["status"] == "OK"

    # 2. Context compile
    req_comp = urllib.request.Request(
        f"{running_ui_server}/api/compile",
        data=json.dumps({"task": "Build login", "role": "BACKEND_ENGINEER", "target": "CLAUDE"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req_comp) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "<defintra_context>" in data["rendered_text"]
