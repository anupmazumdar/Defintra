"""
Defintra MCP Server (§44).
Exposes Defintra project knowledge graph, blast-radius analysis, and context compilation
as Model Context Protocol (MCP) tools for AI assistants (Claude Code, Cursor, Antigravity).
"""

import json
import sys
from typing import Any, Dict, List, Optional
from defintra.core.db.database import Database
from defintra.core.entropy.calculator import EntropyCalculator
from defintra.core.graph.engine import ProjectGraph
from defintra.core.decisions.ledger import DecisionLedger
from defintra.core.models.entities import ApprovalLevel, ChangeRisk, RejectedAlternative, SourceType


class DefintraMCPServer:
    def __init__(self, db_path: str = ".defintra/project.db"):
        self.db = Database(db_path)
        self.decision_ledger = DecisionLedger(self.db)

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

        alts = [
            RejectedAlternative(
                alternative=a.get("alternative", ""),
                reason_rejected=a.get("reason_rejected", ""),
                proposed_by=a.get("proposed_by", "AI Assistant"),
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

    def compile_context(self, task_description: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Minimum Sufficient Context Compiler (§21).
        Provides explainable inclusion/exclusion for the specified task.
        """
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            return {"error": "No project found"}

        reqs = self.db.get_requirements(project.id)
        decs = self.db.get_decisions(project.id)
        comps = self.db.get_components(project.id)

        task_words = set(task_description.lower().split())

        included_reqs = []
        excluded_reqs = []
        for r in reqs:
            r_words = set(r.title.lower().split() + r.description.lower().split())
            if r.priority.value == "CRITICAL" or task_words.intersection(r_words):
                included_reqs.append({"id": r.id, "statement": r.description, "reason": "Direct relevance or critical constraint"})
            else:
                excluded_reqs.append({"id": r.id, "reason": "Unrelated to immediate task keywords"})

        included_decs = [
            {"id": d.id, "decision": f"{d.title}: {d.decision}", "reason": "Approved architecture decision"}
            for d in decs
            if d.status.value == "APPROVED"
        ]

        return {
            "task": task_description,
            "global_objective": project.objective,
            "included_requirements": included_reqs,
            "included_decisions": included_decs,
            "explainable_exclusions": excluded_reqs,
            "token_optimization_ratio": f"{len(included_reqs)}/{len(reqs)} requirements included",
        }


def handle_stdio_rpc():
    """
    Lightweight JSON-RPC stdio dispatcher for MCP integrations.
    """
    server = DefintraMCPServer()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            method = req.get("method")
            params = req.get("params", {})
            req_id = req.get("id")

            if method == "get_project_state":
                res = server.get_project_state(params.get("project_id"))
            elif method == "calculate_blast_radius":
                res = server.calculate_blast_radius(params.get("node_id"), params.get("project_id"))
            elif method == "propose_decision":
                res = server.propose_decision(
                    decision_id=params.get("decision_id"),
                    title=params.get("title"),
                    decision=params.get("decision"),
                    reason=params.get("reason"),
                    rejected_alternatives=params.get("rejected_alternatives", []),
                    project_id=params.get("project_id"),
                )
            elif method == "compile_context":
                res = server.compile_context(params.get("task_description"), params.get("project_id"))
            else:
                res = {"error": f"Unknown method '{method}'"}

            response = {"jsonrpc": "2.0", "id": req_id, "result": res}
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err_response = {"jsonrpc": "2.0", "id": None, "error": str(e)}
            sys.stdout.write(json.dumps(err_response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    handle_stdio_rpc()
