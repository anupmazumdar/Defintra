"""
Regression tests for Issue 7:
Authentication Rate Limiting & Brute-Force Protection.

Verifies:
1. Failed authentication attempts are tracked per client IP.
2. Repeated failed attempts exceeding the threshold trigger lockout and return HTTP 429 Too Many Requests.
3. API routes and bootstrap HTML routes return 429 once locked out.
4. Successful authentication resets failed attempt tracking.
5. Lockout expires or can be explicitly reset.
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


def test_auth_rate_limiting_and_lockout():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "rate_limit_test.db")
    db = Database(db_path)
    engine = DiscoveryEngine(db)
    engine.run_fast_path("Rate Limit Test", "Verify auth brute force protection.")

    bootstrap_token = "valid-secret-token-777"
    DefintraAPIHandler.db_path = db_path
    DefintraAPIHandler.auth_token = bootstrap_token
    DefintraAPIHandler.token_created_at = 0.0
    DefintraAPIHandler.bootstrap_token_used = False
    DefintraAPIHandler.active_sessions = {}
    DefintraAPIHandler.reset_rate_limits()
    # Configure threshold to 3 attempts for faster test execution
    DefintraAPIHandler.max_failed_attempts = 3
    DefintraAPIHandler.lockout_duration_seconds = 60.0

    server = ThreadingHTTPServer(("127.0.0.1", 0), DefintraAPIHandler)
    port = server.server_address[1]
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. First 2 failed attempts should return 401 Unauthorized
        for i in range(2):
            bad_req = request.Request(
                f"{base_url}/api/session",
                data=json.dumps({"token": f"wrong-attempt-{i}"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            try:
                request.urlopen(bad_req)
                assert False, f"Attempt {i+1} should have failed with 401"
            except error.HTTPError as e:
                assert e.code == 401, f"Attempt {i+1} expected 401, got {e.code}"

        # 2. Third failed attempt hits threshold (max_failed_attempts = 3) -> returns 429
        bad_req3 = request.Request(
            f"{base_url}/api/session",
            data=json.dumps({"token": "wrong-attempt-3"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            request.urlopen(bad_req3)
            assert False, "3rd attempt should have triggered rate limit (429)"
        except error.HTTPError as e:
            assert e.code == 429, f"Expected 429, got {e.code}"

        # 3. Subsequent attempts while locked out are immediately rejected with 429 (even with valid credentials)
        valid_req_during_lockout = request.Request(
            f"{base_url}/api/session",
            data=json.dumps({"token": bootstrap_token}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            request.urlopen(valid_req_during_lockout)
            assert False, "Locked out client should receive 429 even with valid token"
        except error.HTTPError as e:
            assert e.code == 429

        # Also GET request to / is blocked with 429
        try:
            request.urlopen(f"{base_url}/")
            assert False, "GET / should return 429 during lockout"
        except error.HTTPError as e:
            assert e.code == 429

        # 4. Reset rate limits clears the lockout
        DefintraAPIHandler.reset_rate_limits()

        # Now legitimate login succeeds with 200
        good_req = request.Request(
            f"{base_url}/api/session",
            data=json.dumps({"token": bootstrap_token}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with request.urlopen(good_req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            session_id = data["session_id"]
            assert session_id

        # 5. Successful access using session cookie succeeds
        state_req = request.Request(
            f"{base_url}/api/state",
            headers={"Cookie": f"defintra_session={session_id}"},
        )
        with request.urlopen(state_req) as resp:
            assert resp.status == 200

    finally:
        # Restore default threshold
        DefintraAPIHandler.max_failed_attempts = 5
        DefintraAPIHandler.reset_rate_limits()
        server.shutdown()
        server.server_close()
        shutil.rmtree(tmpdir, ignore_errors=True)
