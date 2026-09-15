"""
Defintra MCP Server (§44).
Exposes Defintra project knowledge graph, blast-radius analysis,
context compilation, brownfield ingestion, conflict detection, test packs,
AI team orchestration, incident traceback, runbooks, and stability budget
as Model Context Protocol (MCP) tools for AI assistants.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from defintra.context.compiler import AgentRole, ContextCompiler, TargetFormat
from defintra.core.brownfield.scanner import BrownfieldScanner
from defintra.core.conflicts.engine import ConflictEngine
from defintra.core.db.database import Database
from defintra.core.decisions.ledger import DecisionLedger
from defintra.core.entropy.calculator import EntropyCalculator
from defintra.core.governance.stability import StabilityBudgetEngine
from defintra.core.graph.engine import ProjectGraph
from defintra.core.models.entities import (
    ApprovalLevel,
    ChangeRisk,
    RejectedAlternative,
    SourceType,
)
from defintra.core.operations.feedback import IncidentTracer
from defintra.core.operations.runbooks import RunbookGenerator
from defintra.core.security.redactor import SecretRedactor
from defintra.core.team.coordinator import TeamCoordinator
from defintra.core.testing.test_packs import TestPackGenerator


class DefintraMCPServer:
    def __init__(self, db_path: str = ".defintra/project.db"):
        self.db = Database(db_path)
        self.decision_ledger = DecisionLedger(self.db)
        self.compiler = ContextCompiler(self.db)
        self.conflict_engine = ConflictEngine(self.db)
        self.scanner = BrownfieldScanner(self.db)
        self.test_pack_gen = TestPackGenerator(self.db)
        self.team_coordinator = TeamCoordinator(self.db)
        self.incident_tracer = IncidentTracer(self.db)
        self.runbook_gen = RunbookGenerator(self.db)
        self.stability_engine = StabilityBudgetEngine(self.db)

    def get_project_state(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found in Defintra database"}

        reqs = self.db.get_requirements(project.id)
        decs = self.db.get_decisions(project.id)
        asms = self.db.get_assumptions(project.id)
        unks = self.db.get_unknowns(project.id)
        comps = self.db.get_components(project.id)
        conflicts = self.db.get_conflicts(project.id)

        health_report = EntropyCalculator.compute(reqs, decs, asms, unks, conflicts)

        return {
            "project_id": project.id,
            "name": project.name,
            "objective": project.objective,
            "domain": project.domain,
            "source_type": project.source_type,
            "health": health_report.to_dict(),
            "summary": {
                "requirements_count": len(reqs),
                "decisions_count": len(decs),
                "components_count": len(comps),
                "open_unknowns_count": len([u for u in unks if u.status == "OPEN"]),
                "active_conflicts_count": len([c for c in conflicts if c.status == "OPEN"]),
            },
        }

    def calculate_blast_radius(self, node_id: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}

        p_graph = ProjectGraph(self.db, project.id)
        report = p_graph.calculate_blast_radius(node_id)
        return report.to_dict()

    def propose_decision(
        self,
        decision_id: str,
        title: str,
        decision: str,
        reason: str,
        rejected_alternatives: List[Dict[str, str]],
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}

        title = SecretRedactor.sanitize_all(title)
        decision = SecretRedactor.sanitize_all(decision)
        reason = SecretRedactor.sanitize_all(reason)

        alts = [
            RejectedAlternative(
                alternative=SecretRedactor.sanitize_all(a.get("alternative", "")),
                reason_rejected=SecretRedactor.sanitize_all(a.get("reason_rejected", "")),
                proposed_by=SecretRedactor.sanitize_all(a.get("proposed_by", "AI Assistant")),
            )
            for a in rejected_alternatives
        ]

        dec = self.decision_ledger.record_decision(
            project_id=project.id,
            decision_id=decision_id,
            title=title,
            decision=decision,
            reason=reason,
            rejected_alternatives=alts,
            approval_level=ApprovalLevel.USER,
            change_risk=ChangeRisk.MEDIUM,
            source="MCP Tool Invocation",
            source_type=SourceType.AI_INFERRED,
        )

        return {
            "status": "PROPOSED",
            "decision_id": dec.id,
            "title": dec.title,
            "requires_user_approval": True,
            "message": f"Decision '{dec.title}' recorded in ledger as PROPOSED. Preserved {len(alts)} rejected alternative(s).",
        }

    def compile_context(
        self,
        task_description: str,
        project_id: Optional[str] = None,
        role: str = "GENERAL",
        target_format: str = "markdown",
        max_tokens: int = 4000,
    ) -> Dict[str, Any]:
        """
        Minimum Sufficient Context Compiler (§21, §23).
        """
        task_description = SecretRedactor.sanitize_all(task_description)
        try:
            agent_role = AgentRole[role.upper()]
        except KeyError:
            agent_role = AgentRole.GENERAL

        try:
            tgt_fmt = TargetFormat[target_format.upper()]
        except KeyError:
            tgt_fmt = TargetFormat.MARKDOWN

        compiled = self.compiler.compile(
            task_description=task_description,
            project_id=project_id,
            role=agent_role,
            max_tokens=max_tokens,
        )
        return {
            "compiled_data": compiled.to_dict(),
            "rendered_context": compiled.render(tgt_fmt),
        }

    def scan_repository(self, repo_path: str, name: Optional[str] = None) -> Dict[str, Any]:
        target = Path(repo_path).resolve()
        cwd = Path.cwd().resolve()
        try:
            target.relative_to(cwd)
        except ValueError:
            return {"error": f"Path traversal rejected: target repository path '{repo_path}' must be within current workspace"}
        if not target.exists():
            return {"error": f"Target repository path '{repo_path}' does not exist."}
        report = self.scanner.scan_repository(str(target), project_name=name)
        return report.to_dict()

    def detect_conflicts(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return [{"error": "No project found"}]
        confs = self.conflict_engine.detect_conflicts(project.id)
        return [c.model_dump() for c in confs]

    def resolve_conflict(
        self,
        conflict_id: str,
        resolution_notes: str,
        winning_entity_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}
        resolved = self.conflict_engine.resolve_conflict(
            project_id=project.id,
            conflict_id=conflict_id,
            resolution_notes=SecretRedactor.sanitize_all(resolution_notes),
            winning_entity_id=winning_entity_id,
        )
        return resolved.model_dump()

    def generate_test_pack(self, pack_type: str = "human", project_id: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}

        if pack_type.lower() == "automated":
            content = self.test_pack_gen.generate_automated_test_scaffold(project.id)
        elif pack_type.lower() == "security":
            content = self.test_pack_gen.generate_security_regression_suite(project.id)
        else:
            content = self.test_pack_gen.generate_human_testing_pack(project.id)

        return {"project_id": project.id, "pack_type": pack_type, "content": content}

    def dispatch_team_task(self, task: str, role: str = "SOFTWARE_ARCHITECT", project_id: Optional[str] = None, action_type: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}
        try:
            agent_role = AgentRole[role.upper()]
        except KeyError:
            agent_role = AgentRole.SOFTWARE_ARCHITECT

        return self.team_coordinator.dispatch_task(project.id, SecretRedactor.sanitize_all(task), agent_role, action_type=action_type)

    def trace_incident(self, error_text: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}
        rep = self.incident_tracer.trace_incident(SecretRedactor.sanitize_all(error_text), project.id)
        return rep.to_dict()

    def generate_runbook(self, runbook_type: str = "backup", project_id: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}
        content = self.runbook_gen.generate_runbook(project.id, runbook_type)
        return {"project_id": project.id, "runbook_type": runbook_type, "content": content}

    def check_stability_budget(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}
        rep = self.stability_engine.evaluate_stability(project.id)
        return rep.to_dict()

    def check_staleness(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}
        from defintra.core.governance.staleness import StalenessEngine
        engine = StalenessEngine(self.db)
        rep = engine.evaluate_staleness(project.id)
        return rep.to_dict()

    def get_improvements(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}
        from defintra.core.operations.improvements import PostDeploymentAdvisor
        advisor = PostDeploymentAdvisor(self.db)
        suggestions = advisor.generate_recommendations(project.id)
        return {"project_id": project.id, "suggestions": [s.to_dict() for s in suggestions]}

    def diagnose_recovery(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}
        from defintra.core.governance.recovery import FailureRecoveryEngine
        engine = FailureRecoveryEngine(self.db)
        rep = engine.diagnose_project(project.id)
        return rep.to_dict()

    def generate_adrs(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}
        from defintra.core.decisions.adr import ADRGenerator
        gen = ADRGenerator(self.db)
        decs = self.db.get_decisions(project.id)
        adrs = {d.id: gen.generate_adr(project.id, d.id) for d in decs}
        return {"project_id": project.id, "adrs": adrs}

    def schedule_phases(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}
        from defintra.core.tasks.scheduler import TaskScheduler
        scheduler = TaskScheduler(self.db)
        sched = scheduler.schedule_project(project.id)
        return sched.to_dict()

    def validate_contracts(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}
        from defintra.core.contracts.versioning import ContractVersioningEngine
        engine = ContractVersioningEngine(self.db)
        res = engine.validate_project_contracts(project.id)
        return {"project_id": project.id, "contracts": res}


def handle_stdio_rpc(db_path: str = ".defintra/project.db"):
    """
    MCP-compliant JSON-RPC stdio dispatcher.
    """
    server = DefintraMCPServer(db_path)

    TOOLS = [
        {"name": "get_project_state", "description": "Get current project health, requirements, decisions summary.", "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": []}},
        {"name": "compile_context", "description": "Compile minimum sufficient context for an AI coding task.", "inputSchema": {"type": "object", "properties": {"task_description": {"type": "string"}, "role": {"type": "string"}, "target_format": {"type": "string"}, "max_tokens": {"type": "integer"}, "project_id": {"type": "string"}}, "required": ["task_description"]}},
        {"name": "calculate_blast_radius", "description": "Simulate blast radius of changing a node.", "inputSchema": {"type": "object", "properties": {"node_id": {"type": "string"}, "project_id": {"type": "string"}}, "required": ["node_id"]}},
        {"name": "detect_conflicts", "description": "Detect requirement and architectural conflicts.", "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": []}},
        {"name": "generate_test_pack", "description": "Generate test packs (human/automated/security).", "inputSchema": {"type": "object", "properties": {"pack_type": {"type": "string"}, "project_id": {"type": "string"}}, "required": []}},
        {"name": "check_stability_budget", "description": "Check architecture stability and churn index.", "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": []}},
        {"name": "trace_incident", "description": "Map production error back to requirements.", "inputSchema": {"type": "object", "properties": {"error_text": {"type": "string"}, "project_id": {"type": "string"}}, "required": ["error_text"]}},
        {"name": "generate_runbook", "description": "Generate operational runbooks.", "inputSchema": {"type": "object", "properties": {"runbook_type": {"type": "string"}, "project_id": {"type": "string"}}, "required": []}},
        {"name": "propose_decision", "description": "Record an architectural decision.", "inputSchema": {"type": "object", "properties": {"decision_id": {"type": "string"}, "title": {"type": "string"}, "decision": {"type": "string"}, "reason": {"type": "string"}, "rejected_alternatives": {"type": "array"}, "project_id": {"type": "string"}}, "required": ["decision_id", "title", "decision", "reason"]}},
        {"name": "dispatch_team_task", "description": "Dispatch task to a specialized AI team role.", "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}, "role": {"type": "string"}, "project_id": {"type": "string"}}, "required": ["task"]}},
        {"name": "check_staleness", "description": "Check stale requirements and decisions.", "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": []}},
    ]

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            method = req.get("method")
            params = req.get("params", {})
            req_id = req.get("id")

            # MCP Protocol Handshake
            if method == "initialize":
                res = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "defintra", "version": "0.1.0"},
                }
            elif method == "notifications/initialized":
                continue
            elif method == "ping":
                res = {}
            elif method == "tools/list":
                res = {"tools": TOOLS}
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})

                if tool_name == "get_project_state":
                    result = server.get_project_state(tool_args.get("project_id"))
                elif tool_name == "compile_context":
                    result = server.compile_context(
                        task_description=tool_args.get("task_description", ""),
                        project_id=tool_args.get("project_id"),
                        role=tool_args.get("role", "GENERAL"),
                        target_format=tool_args.get("target_format", "markdown"),
                        max_tokens=tool_args.get("max_tokens", 4000),
                    )
                elif tool_name == "calculate_blast_radius":
                    result = server.calculate_blast_radius(tool_args.get("node_id"), tool_args.get("project_id"))
                elif tool_name == "detect_conflicts":
                    result = server.detect_conflicts(tool_args.get("project_id"))
                elif tool_name == "generate_test_pack":
                    result = server.generate_test_pack(tool_args.get("pack_type", "human"), tool_args.get("project_id"))
                elif tool_name == "check_stability_budget":
                    result = server.check_stability_budget(tool_args.get("project_id"))
                elif tool_name == "trace_incident":
                    result = server.trace_incident(tool_args.get("error_text", ""), tool_args.get("project_id"))
                elif tool_name == "generate_runbook":
                    result = server.generate_runbook(tool_args.get("runbook_type", "backup"), tool_args.get("project_id"))
                elif tool_name == "propose_decision":
                    result = server.propose_decision(
                        decision_id=tool_args.get("decision_id"),
                        title=tool_args.get("title"),
                        decision=tool_args.get("decision"),
                        reason=tool_args.get("reason"),
                        rejected_alternatives=tool_args.get("rejected_alternatives", []),
                        project_id=tool_args.get("project_id"),
                    )
                elif tool_name == "dispatch_team_task":
                    result = server.dispatch_team_task(tool_args.get("task", ""), tool_args.get("role", "SOFTWARE_ARCHITECT"), tool_args.get("project_id"))
                elif tool_name == "check_staleness":
                    result = server.check_staleness(tool_args.get("project_id"))
                else:
                    result = {"error": f"Unknown tool '{tool_name}'"}

                res = {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

            else:
                res = {"error": f"Unknown method '{method}'"}

            response = {"jsonrpc": "2.0", "id": req_id, "result": res}
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except Exception as e:
            err_response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
            sys.stdout.write(json.dumps(err_response) + "\n")
            sys.stdout.flush()



if __name__ == "__main__":
    handle_stdio_rpc()
