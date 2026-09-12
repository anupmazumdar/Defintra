"""
Incident-to-Requirement Feedback Loop (§30, §32).
Maps production incidents, stack traces, and outage logs back to
originating requirements, contracts, and assumptions in the knowledge graph.
"""

import re
from typing import Any, Dict, List

from defintra.core.db.database import Database
from defintra.core.graph.engine import ProjectGraph
from defintra.core.security.redactor import SecretRedactor


class IncidentTraceReport:
    def __init__(
        self,
        incident_text: str,
        mapped_nodes: List[Dict[str, Any]],
        refuted_assumptions: List[Dict[str, Any]],
        blast_radius_risk: str,
        recommended_regression_tests: List[str],
        recommended_improvements: List[str],
    ):
        self.incident_text = incident_text
        self.mapped_nodes = mapped_nodes
        self.refuted_assumptions = refuted_assumptions
        self.blast_radius_risk = blast_radius_risk
        self.recommended_regression_tests = recommended_regression_tests
        self.recommended_improvements = recommended_improvements

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident": self.incident_text,
            "mapped_nodes": self.mapped_nodes,
            "refuted_assumptions": self.refuted_assumptions,
            "blast_radius_risk": self.blast_radius_risk,
            "recommended_regression_tests": self.recommended_regression_tests,
            "recommended_improvements": self.recommended_improvements,
        }


class IncidentTracer:
    def __init__(self, db: Database):
        self.db = db

    def trace_incident(self, incident_text: str, project_id: str) -> IncidentTraceReport:
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        # Sanitize sensitive credentials and prompt delimiters from stack trace
        incident_text = SecretRedactor.sanitize_all(incident_text)

        reqs = self.db.get_requirements(project_id)
        asms = self.db.get_assumptions(project_id)
        comps = self.db.get_components(project_id)
        contracts = self.db.get_contracts(project_id)

        inc_words = set(re.findall(r"\w+", incident_text.lower()))

        mapped_nodes: List[Dict[str, Any]] = []
        refuted_asms: List[Dict[str, Any]] = []

        # 1. Match Requirements
        for r in reqs:
            r_words = set(re.findall(r"\w+", (r.title + " " + r.description).lower()))
            overlap = inc_words.intersection(r_words)
            if len(overlap) >= 2 or any(w in incident_text.lower() for w in [r.id.lower(), r.title.lower()]):
                mapped_nodes.append({
                    "id": r.id,
                    "type": "REQUIREMENT",
                    "title": r.title,
                    "relevance": f"Matched terms: {', '.join(overlap)}",
                })

        # 2. Match Contracts & Components
        for ct in contracts:
            if ct.name.lower() in incident_text.lower() or ct.contract_type.lower() in incident_text.lower():
                mapped_nodes.append({
                    "id": ct.id,
                    "type": "CONTRACT",
                    "title": ct.name,
                    "relevance": "Contract interface impacted by incident",
                })

        for c in comps:
            if c.name.lower() in incident_text.lower() or c.component_type.lower() in incident_text.lower():
                mapped_nodes.append({
                    "id": c.id,
                    "type": "COMPONENT",
                    "title": c.name,
                    "relevance": "Component boundary where fault occurred",
                })

        # 3. Check for refuted assumptions
        for a in asms:
            a_words = set(re.findall(r"\w+", a.statement.lower()))
            overlap = inc_words.intersection(a_words)
            if len(overlap) >= 2:
                refuted_asms.append({
                    "id": a.id,
                    "statement": a.statement,
                    "confidence": a.confidence,
                    "reason": f"Incident indicates assumption may be invalid: '{incident_text[:60]}...'",
                })

        # 4. Calculate Blast Radius of the Fix
        graph = ProjectGraph(self.db, project_id)
        risk_level = "LOW"
        if mapped_nodes:
            top_node = mapped_nodes[0]["id"]
            blast = graph.calculate_blast_radius(top_node)
            risk_level = blast.risk_level.value

        # 5. Formulate recommendations
        reg_tests = [
            f"Add fault injection test for: {incident_text[:50]}",
            "Verify timeout and circuit-breaker behavior under network degradation",
            "Ensure idempotent retry logic prevents duplicate transactions",
        ]

        improvements = [
            "Update acceptance criteria in the originating requirement node",
            "Review and tighten contract boundary validation rules",
        ]
        if refuted_asms:
            improvements.append(f"Formally refute and supersede {len(refuted_asms)} weak assumption(s)")

        return IncidentTraceReport(
            incident_text=incident_text,
            mapped_nodes=mapped_nodes,
            refuted_assumptions=refuted_asms,
            blast_radius_risk=risk_level,
            recommended_regression_tests=reg_tests,
            recommended_improvements=improvements,
        )
