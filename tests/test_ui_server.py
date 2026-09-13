"""
Unit and regression tests for Issue 5:
Bootstrap Token URL Leakage Mitigation & Single-Use Enforcement.

Verifies:
1. Initial GET /?token=<valid> redirects with HTTP 303 to bare path (/) and issues session cookie.
2. Following the redirect with the issued cookie returns 200 and loads dashboard HTML.
3. Subsequent attempts to reuse the bootstrap token in URL query parameter fail with 401 (single-use).
4. Invalid bootstrap tokens in URL query parameter fail with 401.
5. Token rotation resets bootstrap token single-use flag.
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


class NoRedirect(request.HTTPRedirectHandler):
    def http_error_303(self, req, fp, code, msg, headers):
        return fp

    def http_error_302(self, req, fp, code, msg, headers):
        return fp


def test_bootstrap_token_redirect_and_single_use():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "ui_server_test.db")
    db = Database(db_path)
    engine = DiscoveryEngine(db)
    engine.run_fast_path("UI Bootstrap Test", "Testing bootstrap token redirect and single use.")

    bootstrap_token = "secure-bootstrap-token-12345"
    DefintraAPIHandler.db_path = db_path
    DefintraAPIHandler.auth_token = bootstrap_token
    DefintraAPIHandler.token_created_at = 0.0
    DefintraAPIHandler.bootstrap_token_used = False
    DefintraAPIHandler.active_sessions = {}

    server = ThreadingHTTPServer(("127.0.0.1", 0), DefintraAPIHandler)
    port = server.server_address[1]
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

    base_url = f"http://127.0.0.1:{port}"
    opener = request.build_opener(NoRedirect)

    try:
        # 1. Unauthenticated request to / returns 401
        try:
            opener.open(f"{base_url}/")
            assert False, "Unauthenticated request should return 401"
        except error.HTTPError as e:
            assert e.code == 401

        # 2. Invalid token in query param returns 401
        try:
            opener.open(f"{base_url}/?token=wrong_token")
            assert False, "Invalid token in query param should return 401"
        except error.HTTPError as e:
            assert e.code == 401

        # 3. Valid bootstrap token in query param returns 303 redirect with Set-Cookie
        res = opener.open(f"{base_url}/?token={bootstrap_token}")
        assert res.status == 303
        assert res.headers.get("Location") == "/"
        cookie_header = res.headers.get("Set-Cookie", "")
        assert "defintra_session=" in cookie_header
        assert "HttpOnly" in cookie_header
        assert "SameSite=Strict" in cookie_header

        # Extract session cookie
        session_cookie = cookie_header.split(";")[0]

        # 4. Browser following redirect to bare / with session cookie loads dashboard (200)
        req_bare = request.Request(f"{base_url}/", headers={"Cookie": session_cookie})
        with opener.open(req_bare) as bare_res:
            assert bare_res.status == 200
            body = bare_res.read().decode("utf-8")
            assert "Defintra Control Center" in body

        # 5. Reusing the bootstrap token in query param is strictly rejected with 401 (single-use)
        try:
            opener.open(f"{base_url}/?token={bootstrap_token}")
            assert False, "Reusing consumed bootstrap token must fail with 401"
        except error.HTTPError as e:
            assert e.code == 401

        # 6. Rotate token enables a new bootstrap exchange with new token
        rotate_req = request.Request(
            f"{base_url}/api/token/rotate",
            data=b"{}",
            headers={"Cookie": session_cookie, "Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(rotate_req) as rot_res:
            assert rot_res.status == 200
            rot_data = json.loads(rot_res.read().decode("utf-8"))
            new_token = rot_data["new_token"]

        # New bootstrap token can be used once
        new_res = opener.open(f"{base_url}/?token={new_token}")
        assert new_res.status == 303
        assert "defintra_session=" in new_res.headers.get("Set-Cookie", "")

        # And cannot be used a second time
        try:
            opener.open(f"{base_url}/?token={new_token}")
            assert False, "Reusing new bootstrap token must fail with 401"
        except error.HTTPError as e:
            assert e.code == 401

    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(tmpdir, ignore_errors=True)
