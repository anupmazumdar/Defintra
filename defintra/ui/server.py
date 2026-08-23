"""
Defintra Embedded Web Dashboard Server (§5, §7, §21, §22).
Serves the rich dark-mode Defintra Control Center and provides JSON REST API.
"""

import json
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from defintra.context.compiler import AgentRole, ContextCompiler, TargetFormat
from defintra.core.conflicts.engine import ConflictEngine
from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.entropy.calculator import EntropyCalculator
from defintra.core.governance.stability import StabilityBudgetEngine
from defintra.core.graph.engine import ProjectGraph
from defintra.core.operations.feedback import IncidentTracer
from defintra.core.operations.runbooks import RunbookGenerator
from defintra.core.team.coordinator import TeamCoordinator


class DefintraAPIHandler(BaseHTTPRequestHandler):
    db_path: str = ".defintra/project.db"

    def _get_db(self) -> Database:
        return Database(self.db_path)

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content: str):
        body = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            html_file = Path(__file__).parent / "dashboard.html"
            if html_file.exists():
                self._send_html(html_file.read_text(encoding="utf-8"))
            else:
                self._send_html("<h1>Defintra Dashboard Loading...</h1>")
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

        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b"{}"
        payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}

        db = self._get_db()
        project = db.get_first_project()
        if not project:
            self._send_json({"error": "No active project"}, 400)
            return

        if path == "/api/answer":
            unk_id = payload.get("unknown_id")
            answer = payload.get("answer", "")
            engine = DiscoveryEngine(db)
            report = engine.answer_unknown(project.id, unk_id, answer)
            self._send_json({"status": "OK", "health": report.to_dict()})

        elif path == "/api/compile":
            task = payload.get("task", "Implement core features")
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
            notes = payload.get("notes", "Resolved in Web Dashboard")
            conf_engine = ConflictEngine(db)
            resolved = conf_engine.resolve_conflict(project.id, cid, notes, winner_id)
            self._send_json(resolved.model_dump())

        elif path == "/api/incident":
            error_text = payload.get("error_text", "")
            tracer = IncidentTracer(db)
            report = tracer.trace_incident(error_text, project.id)
            self._send_json(report.to_dict())

        elif path == "/api/team/dispatch":
            task = payload.get("task", "")
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
            from defintra.core.brownfield.scanner import BrownfieldScanner
            scanner = BrownfieldScanner(db)
            report = scanner.scan_repository(scan_path, project_name=proj_name)
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


def start_ui_server(port: int = 8765, db_path: str = ".defintra/project.db", open_browser: bool = True):
    DefintraAPIHandler.db_path = db_path
    server = ThreadingHTTPServer(("127.0.0.1", port), DefintraAPIHandler)
    url = f"http://127.0.0.1:{port}"
    print(f"Defintra Control Center running at: {url}")
    if open_browser:
        try:
            webbrowser.open(url)
        except (webbrowser.Error, OSError):
            pass  # Suppress browser launch failure in headless environments
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
