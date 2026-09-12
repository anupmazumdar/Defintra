"""
Regression tests for Finding 2: Session Token URL Leakage Mitigation & HTTP-Only Cookie Exchange.
Verifies that:
1. POST /api/session exchanges bootstrap token for HttpOnly, SameSite=Strict session cookie.
2. Subsequent API requests authenticate via session cookie.
3. API endpoints strictly reject ?token= query parameter to prevent URL leakage.
4. Initial HTML GET /?token= sets session cookie and authorizes first-load.
5. DELETE /api/session logs out and expires cookie.
"""

import json
import os
import shutil
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib import error, request

from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.ui.server import DefintraAPIHandler


def test_session_token_exchange_and_url_leak_prevention():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "session_test.db")
    db = Database(db_path)
    engine = DiscoveryEngine(db)
    engine.run_fast_path("Session Project", "Test session cookie authentication.")

    bootstrap_token = "sec-bootstrap-token-999"
    DefintraAPIHandler.db_path = db_path
    DefintraAPIHandler.auth_token = bootstrap_token
    DefintraAPIHandler.active_sessions = {}

    server = ThreadingHTTPServer(("127.0.0.1", 0), DefintraAPIHandler)
    port = server.server_address[1]
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Reject invalid bootstrap token at /api/session
        bad_req = request.Request(
            f"{base_url}/api/session",
            data=json.dumps({"token": "wrong-token"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            request.urlopen(bad_req)
            assert False, "Should have failed with 401"
        except error.HTTPError as e:
            assert e.code == 401

        # 2. Successfully exchange valid bootstrap token at /api/session
        good_req = request.Request(
            f"{base_url}/api/session",
            data=json.dumps({"token": bootstrap_token}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with request.urlopen(good_req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "authenticated"
            session_id = data["session_id"]
            cookie_header = resp.headers.get("Set-Cookie", "")
            assert "defintra_session=" in cookie_header
            assert "HttpOnly" in cookie_header
            assert "SameSite=Strict" in cookie_header

        # 3. Authenticate to /api/state using the session cookie
        state_req = request.Request(
            f"{base_url}/api/state",
            headers={"Cookie": f"defintra_session={session_id}"},
        )
        with request.urlopen(state_req) as resp:
            assert resp.status == 200
            state_data = json.loads(resp.read().decode("utf-8"))
            assert state_data["project"]["name"] == "Session Project"

        # 4. Strict check: API endpoint MUST REJECT ?token= query param (Finding 2 prevention)
        leak_attempt_url = f"{base_url}/api/state?token={bootstrap_token}"
        leak_req = request.Request(leak_attempt_url)
        try:
            request.urlopen(leak_req)
            assert False, "API route should have rejected ?token= query param with 401"
        except error.HTTPError as e:
            assert e.code == 401

        # 5. Bootstrap HTML route (/) accepts ?token= and attaches session cookie
        html_bootstrap_url = f"{base_url}/?token={bootstrap_token}"
        with request.urlopen(html_bootstrap_url) as resp:
            assert resp.status == 200
            cookie_header = resp.headers.get("Set-Cookie", "")
            assert "defintra_session=" in cookie_header

        # 6. Logout / DELETE /api/session expires session
        delete_req = request.Request(
            f"{base_url}/api/session",
            headers={"Cookie": f"defintra_session={session_id}"},
            method="DELETE",
        )
        with request.urlopen(delete_req) as resp:
            assert resp.status == 200
            cookie_header = resp.headers.get("Set-Cookie", "")
            assert "Max-Age=0" in cookie_header

        # Session id is now revoked
        revoked_req = request.Request(
            f"{base_url}/api/state",
            headers={"Cookie": f"defintra_session={session_id}"},
        )
        try:
            request.urlopen(revoked_req)
            assert False, "Revoked session should return 401"
        except error.HTTPError as e:
            assert e.code == 401

    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(tmpdir, ignore_errors=True)
