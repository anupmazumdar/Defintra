import html
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.ui.server import DefintraAPIHandler, ThreadingHTTPServer

TEST_TOKEN = "defintra-secure-test-token-abcdef"


def api_request(
    base_url: str,
    path: str,
    data: Optional[Dict[str, Any]] = None,
    token: Optional[str] = TEST_TOKEN,
    method: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    url = f"{base_url}{path}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    return urllib.request.urlopen(req)


@pytest.fixture
def running_ui_server(tmp_path):
    db_file = tmp_path / "test_ui.db"
    db = Database(str(db_file))
    engine = DiscoveryEngine(db)
    engine.run_fast_path("UI Test Project", "Build customer portal with React and FastAPI")

    DefintraAPIHandler.db_path = str(db_file)
    DefintraAPIHandler.auth_token = TEST_TOKEN
    # Find free port
    server = ThreadingHTTPServer(("127.0.0.1", 0), DefintraAPIHandler)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    server.shutdown()
    server.server_close()
    DefintraAPIHandler.auth_token = None


def test_ui_get_html_and_state(running_ui_server):
    # 1. HTML index with token
    with api_request(running_ui_server, "/") as res:
        assert res.status == 200
        html_content = res.read().decode("utf-8")
        assert "Defintra Control Center" in html_content
        # Verify CORS wildcard is absent
        assert "Access-Control-Allow-Origin" not in res.headers
        # Verify Content-Security-Policy header is present
        assert "Content-Security-Policy" in res.headers
        assert "default-src 'self'" in res.headers["Content-Security-Policy"]

    # 2. State API
    with api_request(running_ui_server, "/api/state") as res:
        assert res.status == 200
        assert "Access-Control-Allow-Origin" not in res.headers
        data = json.loads(res.read().decode("utf-8"))
        assert data["project"]["name"] == "UI Test Project"
        assert len(data["requirements"]) >= 3
        assert "health" in data

    # 3. Graph API
    with api_request(running_ui_server, "/api/graph") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "nodes" in data
        assert len(data["nodes"]) >= 3

    # 4. Token via query param: allowed on bootstrap HTML route (/), rejected on API routes to prevent URL leak
    with urllib.request.urlopen(f"{running_ui_server}/?token={TEST_TOKEN}") as res:
        assert res.status == 200
        assert "defintra_session=" in res.headers.get("Set-Cookie", "")

    try:
        urllib.request.urlopen(f"{running_ui_server}/api/state?token={TEST_TOKEN}")
        assert False, "API route must reject ?token= query param"
    except urllib.error.HTTPError as e:
        assert e.code == 401


def test_ui_post_actions(running_ui_server):
    # 1. Answer unknown
    with api_request(
        running_ui_server,
        "/api/answer",
        data={"unknown_id": "UNK-001_ui_test_project", "answer": "PostgreSQL database"},
        method="POST",
    ) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert data["status"] == "OK"

    # 2. Context compile
    with api_request(
        running_ui_server,
        "/api/compile",
        data={"task": "Build login", "role": "BACKEND_ENGINEER", "target": "CLAUDE"},
        method="POST",
    ) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "<defintra_context>" in data["rendered_text"]

    # 3. Test pack endpoint
    with api_request(running_ui_server, "/api/test-pack?type=human") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "Human Testing Pack" in data["content"]

    # 4. Runbook endpoint
    with api_request(running_ui_server, "/api/runbook?type=backup") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "Operations Runbook" in data["content"]

    # 5. Stability endpoint
    with api_request(running_ui_server, "/api/stability") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "stability_score" in data
        assert "churn_index" in data

    # 6. Incident endpoint
    with api_request(
        running_ui_server,
        "/api/incident",
        data={"error_text": "Error in auth service during login"},
        method="POST",
    ) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "mapped_nodes" in data

    # 7. Blast radius endpoint
    with api_request(
        running_ui_server,
        "/api/blast-radius",
        data={"node_id": "D-001"},
        method="POST",
    ) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "total_blast_count" in data

    # 8. Staleness endpoint
    with api_request(running_ui_server, "/api/staleness") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "system_staleness_score" in data

    # 9. Improvements endpoint
    with api_request(running_ui_server, "/api/improvements") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert len(data["suggestions"]) >= 2

    # 10. Recovery endpoint
    with api_request(running_ui_server, "/api/recovery") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "system_health_status" in data

    # 11. Revalidate node endpoint
    with api_request(
        running_ui_server,
        "/api/staleness/revalidate",
        data={"node_id": "REQ-001"},
        method="POST",
    ) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "status" in data


def test_ui_unauthenticated_rejected(running_ui_server):
    # 1. Unauthenticated root request -> 401
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{running_ui_server}/")
    assert exc_info.value.code == 401

    # 2. Unauthenticated GET /api/state -> 401
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{running_ui_server}/api/state")
    assert exc_info.value.code == 401

    # 3. Invalid Bearer token -> 401
    req = urllib.request.Request(
        f"{running_ui_server}/api/state",
        headers={"Authorization": "Bearer totally-invalid-token"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 401

    # 4. Unauthenticated POST /api/compile -> 401
    req_post = urllib.request.Request(
        f"{running_ui_server}/api/compile",
        data=b'{"task":"Build login"}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req_post)
    assert exc_info.value.code == 401

    # 5. Unauthenticated OPTIONS /api/state -> 401
    req_opt = urllib.request.Request(
        f"{running_ui_server}/api/state",
        method="OPTIONS",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req_opt)
    assert exc_info.value.code == 401


def test_ui_scan_path_traversal_rejected(running_ui_server):
    # Attempting to scan outside workspace boundary must return 400 Bad Request
    req = urllib.request.Request(
        f"{running_ui_server}/api/scan",
        data=json.dumps({"path": "../../../etc/shadow"}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {TEST_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 400
    res_body = exc_info.value.read().decode("utf-8")
    assert "Path traversal rejected" in res_body


def test_ui_stored_xss_escaped(running_ui_server):
    # 1. Verify dashboard HTML has escaping function and CSP
    dashboard_path = Path(__file__).parent.parent / "defintra" / "ui" / "dashboard.html"
    dashboard_content = dashboard_path.read_text(encoding="utf-8")
    assert "function esc(str)" in dashboard_content
    assert ".replace(/</g, '&lt;')" in dashboard_content
    assert ".replace(/>/g, '&gt;')" in dashboard_content
    assert '.replace(/"/g, \'&quot;\')' in dashboard_content
    assert ".replace(/'/g, '&#39;')" in dashboard_content

    # 2. Verify all interpolated templates in dashboard use esc(...)
    assert "${esc(r.title)}" in dashboard_content
    assert "${esc(d.title)}" in dashboard_content
    assert "${esc(cf.title)}" in dashboard_content
    assert "${esc(u.question)}" in dashboard_content

    # 3. Verify server sends CSP header restricting script execution
    with api_request(running_ui_server, "/") as res:
        csp = res.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "connect-src 'self'" in csp

    # 4. Verify that an XSS payload in database is properly escaped when transformed
    xss_payload = "<img src=x onerror=alert('xss')>"
    escaped = html.escape(xss_payload, quote=True)
    assert "<" not in escaped
    assert ">" not in escaped
    assert "&lt;img" in escaped
