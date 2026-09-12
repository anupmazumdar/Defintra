"""

Defintra Embedded Web Dashboard Server (§5, §7, §21, §22).
Serves the rich dark-mode Defintra Control Center and provides JSON REST API.
"""

import json
import secrets
import time
import urllib.parse
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from defintra.context.compiler import AgentRole, ContextCompiler, TargetFormat
from defintra.core.conflicts.engine import ConflictEngine
from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.entropy.calculator import EntropyCalculator
from defintra.core.governance.stability import StabilityBudgetEngine
from defintra.core.graph.engine import ProjectGraph
from defintra.core.operations.feedback import IncidentTracer
from defintra.core.operations.runbooks import RunbookGenerator
from defintra.core.security.redactor import SecretRedactor
from defintra.core.team.coordinator import TeamCoordinator


class DefintraAPIHandler(BaseHTTPRequestHandler):
    db_path: str = ".defintra/project.db"
    auth_token: Optional[str] = None
    token_created_at: float = 0.0
    token_ttl_seconds: float = 8 * 3600  # Master token expires after 8 hours
    active_sessions: Dict[str, float] = {}  # session_id -> last_activity_timestamp
    session_inactivity_ttl: float = 8 * 3600  # Inactivity timeout (8 hours)

    def _get_db(self) -> Database:
        return Database(self.db_path)

    def _check_auth(self) -> bool:
        if self.auth_token is None:
            return False

        now = time.time()
        # Master token lifetime expiration check
        if self.token_created_at > 0 and (now - self.token_created_at > self.token_ttl_seconds):
            return False

        # 1. Check Session Cookie: defintra_session=<session_id>
        cookie_header = self.headers.get("Cookie", "")
        if cookie_header:
            cookies = SimpleCookie()
            try:
                cookies.load(cookie_header)
                if "defintra_session" in cookies:
                    session_id = cookies["defintra_session"].value
                    if session_id in self.active_sessions:
                        last_active = self.active_sessions[session_id]
                        if (now - last_active) > self.session_inactivity_ttl:
                            self.active_sessions.pop(session_id, None)
                            return False
                        # Update rolling activity timestamp
                        self.active_sessions[session_id] = now
                        return True
            except Exception:
                pass

        # 2. Check Authorization header: Bearer <token>
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if secrets.compare_digest(token, self.auth_token):
                return True

        # 3. Check X-Defintra-Token header
        custom_header = self.headers.get("X-Defintra-Token", "").strip()
        if custom_header and secrets.compare_digest(custom_header, self.auth_token):
            return True

        # 4. Check query param ?token= ONLY on the initial bootstrap HTML load (/ or /index.html)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            query = urllib.parse.parse_qs(parsed.query)
            q_token = query.get("token", [""])[0]
            if q_token and secrets.compare_digest(q_token, self.auth_token):
                return True

        return False

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content: str, status: int = 200, set_cookie: Optional[str] = None):
        body = html_content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self';",
        )
        self.send_header("Referrer-Policy", "no-referrer")
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not self._check_auth():
            self.send_response(401)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"error": "Unauthorized: Valid session token required"}')
            return
        self.send_response(204)
        self.end_headers()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/session":
            cookie_header = self.headers.get("Cookie", "")
            if cookie_header:
                cookies = SimpleCookie()
                try:
                    cookies.load(cookie_header)
                    if "defintra_session" in cookies:
                        sess_id = cookies["defintra_session"].value
                        self.active_sessions.pop(sess_id, None)
                except Exception:
                    pass
            body = json.dumps({"status": "logged_out"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Set-Cookie",
                "defintra_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0",
            )
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404, "Not Found")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            if not self._check_auth():
                unauth_html = (
                    "<!DOCTYPE html><html><head><title>401 Unauthorized - Defintra</title>"
                    "<style>body{background:#0b0f19;color:#f3f4f6;font-family:sans-serif;text-align:center;padding:80px;}"
                    "code{color:#38bdf8;background:rgba(255,255,255,0.08);padding:3px 8px;border-radius:4px;}</style></head>"
                    "<body><h2>401 Unauthorized</h2><p>Valid session token required. Run <code>defintra ui</code> in your terminal and use the authenticated link.</p></body></html>"
                )
                self._send_html(unauth_html, status=401)
                return

            # Attach session cookie if authenticated via query param token
            cookie_hdr = None
            query = urllib.parse.parse_qs(parsed.query)
            q_token = query.get("token", [""])[0]
            if q_token and self.auth_token and secrets.compare_digest(q_token, self.auth_token):
                session_id = secrets.token_urlsafe(32)
                self.active_sessions[session_id] = time.time()
                cookie_hdr = f"defintra_session={session_id}; HttpOnly; SameSite=Strict; Path=/"

            html_file = Path(__file__).parent / "dashboard.html"
            if html_file.exists():
                self._send_html(html_file.read_text(encoding="utf-8"), set_cookie=cookie_hdr)
            else:
                self._send_html("<h1>Defintra Dashboard Loading...</h1>", set_cookie=cookie_hdr)
            return

        if not self._check_auth():
            self._send_json({"error": "Unauthorized: Valid session token required"}, 401)
            return

        db = self._get_db()
        project = db.get_first_project()

        if path == "/api/state":
            if not project:
                self._send_json({"error": "No project found. Run `defintra init <name>` first."}, 404)
                return

            reqs = db.get_requirements(project.id)
            decs = db.get_decisions(project.id)
            asms = db.get_assumptions(project.id)
            unks = db.get_unknowns(project.id)
            comps = db.get_components(project.id)
            contracts = db.get_contracts(project.id)
            conflicts = db.get_conflicts(project.id)
            audit = db.get_audit_entries(project.id)
            health = EntropyCalculator.compute(reqs, decs, asms, unks, conflicts)

            state = {
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "objective": project.objective,
                    "domain": project.domain,
                    "source_type": project.source_type,
                },
                "health": health.to_dict(),
                "requirements": [r.model_dump() for r in reqs],
                "decisions": [d.model_dump() for d in decs],
                "assumptions": [a.model_dump() for a in asms],
                "unknowns": [u.model_dump() for u in unks],
                "components": [c.model_dump() for c in comps],
                "contracts": [ct.model_dump() for ct in contracts],
                "conflicts": [cf.model_dump() for cf in conflicts],
                "audit_entries": [au.model_dump() for au in audit],
            }
            self._send_json(state)

        elif path == "/api/graph":
            if not project:
                self._send_json({"nodes": [], "edges": []})
                return
            p_graph = ProjectGraph(db, project.id)
            nodes = []
            for n_id, data in p_graph.graph.nodes(data=True):
                etype = data.get("entity_type", "")
                etype_str = etype.value if hasattr(etype, "value") else str(etype)
                nodes.append({
                    "id": n_id,
                    "title": data.get("title", n_id),
                    "type": etype_str,
                    "status": data.get("status", "PROPOSED"),
                    "confidence": data.get("confidence", 1.0),
                })
            edges = []
            for u, v, data in p_graph.graph.edges(data=True):
                edges.append({"source": u, "target": v, "kind": data.get("kind", "relates")})

            self._send_json({"nodes": nodes, "edges": edges, "mermaid": p_graph.to_mermaid()})

        elif path == "/api/stability":
            if not project:
                self._send_json({"error": "No project"}, 404)
                return
            stab_engine = StabilityBudgetEngine(db)
            rep = stab_engine.evaluate_stability(project.id)
            self._send_json(rep.to_dict())

        elif path.startswith("/api/runbook"):
            if not project:
                self._send_json({"error": "No project"}, 404)
                return
            query = urllib.parse.parse_qs(parsed.query)
            rb_type = query.get("type", ["backup"])[0]
            gen = RunbookGenerator(db)
            content = gen.generate_runbook(project.id, rb_type)
            self._send_json({"type": rb_type, "content": content})

        elif path.startswith("/api/test-pack"):
            if not project:
                self._send_json({"error": "No project"}, 404)
                return
            query = urllib.parse.parse_qs(parsed.query)
            tp_type = query.get("type", ["human"])[0]
            from defintra.core.testing.test_packs import TestPackGenerator
            tp_gen = TestPackGenerator(db)
            if tp_type == "automated":
                content = tp_gen.generate_automated_test_scaffold(project.id)
            elif tp_type == "security":
                content = tp_gen.generate_security_regression_suite(project.id)
            else:
                content = tp_gen.generate_human_testing_pack(project.id)
            self._send_json({"type": tp_type, "content": content})

        elif path == "/api/staleness":
            if not project:
                self._send_json({"error": "No project"}, 404)
                return
            from defintra.core.governance.staleness import StalenessEngine
            st_engine = StalenessEngine(db)
            rep = st_engine.evaluate_staleness(project.id)
            self._send_json(rep.to_dict())

        elif path == "/api/improvements":
            if not project:
                self._send_json({"error": "No project"}, 404)
                return
            from defintra.core.operations.improvements import PostDeploymentAdvisor
            advisor = PostDeploymentAdvisor(db)
            suggestions = advisor.generate_recommendations(project.id)
            self._send_json({"project_id": project.id, "suggestions": [s.to_dict() for s in suggestions]})

        elif path == "/api/recovery":
            if not project:
                self._send_json({"error": "No project"}, 404)
                return
            from defintra.core.governance.recovery import FailureRecoveryEngine
            rec_engine = FailureRecoveryEngine(db)
            rep = rec_engine.diagnose_project(project.id)
            self._send_json(rep.to_dict())

        elif path == "/api/policies":
            if not project:
                self._send_json({"policies": []})
                return
            from defintra.core.policy.engine import PolicyEngine
            pe = PolicyEngine(db)
            policies = pe.list_policies(project.id)
            self._send_json({"project_id": project.id, "policies": [p.to_dict() for p in policies]})

        elif path == "/api/events":
            if not project:
                self._send_json({"events": []})
                return
            coord = TeamCoordinator(db)
            evts = coord.get_events(project.id)
            self._send_json({"project_id": project.id, "events": evts})

        elif path == "/api/benchmarks":
            from defintra.core.benchmark.runner import BenchmarkRunner
            runner = BenchmarkRunner(db)
            history = runner.get_history(project_id=project.id if project else None, limit=20)
            self._send_json({"benchmarks": [h.to_dict() for h in history]})

        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b"{}"
        payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}

        # 1. Dedicated session exchange endpoint for bootstrap token
        if path == "/api/session":
            req_token = payload.get("token", "")
            now = time.time()
            if (
                self.auth_token
                and req_token
                and secrets.compare_digest(req_token, self.auth_token)
                and (self.token_created_at == 0 or now - self.token_created_at <= self.token_ttl_seconds)
            ):
                session_id = secrets.token_urlsafe(32)
                self.active_sessions[session_id] = now
                body = json.dumps({"status": "authenticated", "session_id": session_id}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Set-Cookie",
                    f"defintra_session={session_id}; HttpOnly; SameSite=Strict; Path=/",
                )
                self.end_headers()
                self.wfile.write(body)
                return
            else:
                self._send_json({"error": "Unauthorized: Invalid or expired bootstrap token"}, 401)
                return

        elif path == "/api/token/rotate":
            if not self._check_auth():
                self._send_json({"error": "Unauthorized: Valid session or token required"}, 401)
                return
            new_token = secrets.token_urlsafe(24)
            DefintraAPIHandler.auth_token = new_token
            DefintraAPIHandler.token_created_at = time.time()
            DefintraAPIHandler.active_sessions.clear()

            new_session_id = secrets.token_urlsafe(32)
            DefintraAPIHandler.active_sessions[new_session_id] = time.time()

            body = json.dumps({
                "status": "rotated",
                "new_token": new_token,
                "session_id": new_session_id,
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Set-Cookie",
                f"defintra_session={new_session_id}; HttpOnly; SameSite=Strict; Path=/",
            )
            self.end_headers()
            self.wfile.write(body)
            return

        elif path == "/api/token/revoke":
            if not self._check_auth():
                self._send_json({"error": "Unauthorized: Valid session or token required"}, 401)
                return
            DefintraAPIHandler.auth_token = None
            DefintraAPIHandler.active_sessions.clear()
            body = json.dumps({"status": "revoked"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Set-Cookie",
                "defintra_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0",
            )
            self.end_headers()
            self.wfile.write(body)
            return

        if not self._check_auth():
            self._send_json({"error": "Unauthorized: Valid session token required"}, 401)
            return

        db = self._get_db()
        project = db.get_first_project()
        if not project:
            self._send_json({"error": "No active project"}, 400)
            return

        if path == "/api/answer":
            unk_id = payload.get("unknown_id")
            answer = SecretRedactor.sanitize_all(payload.get("answer", ""))
            engine = DiscoveryEngine(db)
            report = engine.answer_unknown(project.id, unk_id, answer)
            self._send_json({"status": "OK", "health": report.to_dict()})

        elif path == "/api/compile":
            raw_task = payload.get("task", "Implement core features")
            task = SecretRedactor.sanitize_all(raw_task)
            role_str = payload.get("role", "GENERAL")
            target_str = payload.get("target", "markdown")
            try:
                role = AgentRole[role_str.upper()]
            except KeyError:
                role = AgentRole.GENERAL
            try:
                target = TargetFormat[target_str.upper()]
            except KeyError:
                target = TargetFormat.MARKDOWN

            compiler = ContextCompiler(db)
            compiled = compiler.compile(task_description=task, project_id=project.id, role=role)
            self._send_json({
                "compiled_data": compiled.to_dict(),
                "rendered_text": compiled.render(target),
            })

        elif path == "/api/conflicts/resolve":
            cid = payload.get("conflict_id")
            winner_id = payload.get("winner_id")
            raw_notes = payload.get("notes", "Resolved in Web Dashboard")
            notes = SecretRedactor.sanitize_all(raw_notes)
            conf_engine = ConflictEngine(db)
            resolved = conf_engine.resolve_conflict(project.id, cid, notes, winner_id)
            self._send_json(resolved.model_dump())

        elif path == "/api/incident":
            raw_error = payload.get("error_text", "")
            error_text = SecretRedactor.sanitize_all(raw_error)
            tracer = IncidentTracer(db)
            report = tracer.trace_incident(error_text, project.id)
            self._send_json(report.to_dict())

        elif path == "/api/team/dispatch":
            raw_task = payload.get("task", "")
            task = SecretRedactor.sanitize_all(raw_task)
            role_str = payload.get("role", "SOFTWARE_ARCHITECT")
            try:
                role = AgentRole[role_str.upper()]
            except KeyError:
                role = AgentRole.SOFTWARE_ARCHITECT
            coordinator = TeamCoordinator(db)
            res = coordinator.dispatch_task(project.id, task, role)
            self._send_json(res)

        elif path == "/api/blast-radius":
            node_id = payload.get("node_id", "")
            p_graph = ProjectGraph(db, project.id)
            report = p_graph.calculate_blast_radius(node_id)
            self._send_json(report.to_dict())

        elif path == "/api/scan":
            scan_path = payload.get("path", ".")
            proj_name = payload.get("name", "Scanned Project")

            target_path = Path(scan_path).resolve()
            workspace_root = Path(".").resolve()
            try:
                target_path.relative_to(workspace_root)
            except ValueError:
                self._send_json({"error": "Path traversal rejected: target path must be within workspace root"}, 400)
                return

            if not target_path.exists() or not target_path.is_dir():
                self._send_json({"error": f"Target path '{scan_path}' is not an existing directory"}, 400)
                return

            from defintra.core.brownfield.scanner import BrownfieldScanner
            scanner = BrownfieldScanner(db)
            report = scanner.scan_repository(str(target_path), project_name=proj_name)
            self._send_json(report.to_dict())

        elif path == "/api/sandbox/create":
            task_id = payload.get("task", "task_execution")
            from defintra.core.sandbox.manager import SandboxManager
            sbx_mgr = SandboxManager(db)
            sandbox = sbx_mgr.create_sandbox(project.id, task_id=task_id)
            self._send_json(sandbox.to_dict())

        elif path == "/api/staleness/revalidate":
            node_id = payload.get("node_id", "")
            from defintra.core.governance.staleness import StalenessEngine
            st_engine = StalenessEngine(db)
            success = st_engine.revalidate_node(project.id, node_id)
            self._send_json({"status": "OK" if success else "FAILED", "node_id": node_id})

        else:
            self.send_error(404, "Not Found")

    def log_message(self, format, *args):
        pass  # Suppress noisy HTTP stdout logs


def start_ui_server(
    port: int = 8765,
    db_path: str = ".defintra/project.db",
    open_browser: bool = True,
    auth_token: Optional[str] = None,
):
    token = auth_token or secrets.token_urlsafe(24)
    DefintraAPIHandler.db_path = db_path
    DefintraAPIHandler.auth_token = token
    DefintraAPIHandler.token_created_at = time.time()
    server = ThreadingHTTPServer(("127.0.0.1", port), DefintraAPIHandler)
    url = f"http://127.0.0.1:{port}/?token={token}"
    print(f"Defintra Control Center running at: {url}")
    print(f"Session Token: {token}")
    if open_browser:
        try:
            webbrowser.open(url)
        except (webbrowser.Error, OSError):
            pass  # Suppress browser launch failure in headless environments
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
