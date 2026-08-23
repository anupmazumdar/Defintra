"""
Post-Deployment Improvement & Continuous Optimization Engine (§32).
Generates targeted post-deployment suggestions with expected benefit,
change risk, estimated cost, and blast radius.
"""

from typing import Any, Dict, List

from defintra.core.db.database import Database
from defintra.core.models.entities import ChangeRisk


class ImprovementSuggestion:
    def __init__(
        self,
        id: str,
        title: str,
        category: str,
        expected_benefit: str,
        change_risk: ChangeRisk,
        estimated_effort: str,
        affected_nodes: List[str],
        action_plan: List[str],
        roi_score: float,  # 1.0 to 10.0
    ):
        self.id = id
        self.title = title
        self.category = category
        self.expected_benefit = expected_benefit
        self.change_risk = change_risk
        self.estimated_effort = estimated_effort
        self.affected_nodes = affected_nodes
        self.action_plan = action_plan
        self.roi_score = roi_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "expected_benefit": self.expected_benefit,
            "change_risk": self.change_risk.value,
            "estimated_effort": self.estimated_effort,
            "affected_nodes": self.affected_nodes,
            "action_plan": self.action_plan,
            "roi_score": self.roi_score,
        }


class PostDeploymentAdvisor:
    def __init__(self, db: Database):
        self.db = db

    def generate_recommendations(self, project_id: str) -> List[ImprovementSuggestion]:
        """
        Analyzes the project knowledge graph, requirements, decisions, and contracts
        to produce actionable post-deployment optimization proposals (§32).
        """
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        reqs = self.db.get_requirements(project_id)
        decs = self.db.get_decisions(project_id)
        comps = self.db.get_components(project_id)

        suggestions: List[ImprovementSuggestion] = []

        # 1. Redis Caching Optimization
        has_caching = any("redis" in d.decision.lower() or "cache" in d.decision.lower() for d in decs)
        if not has_caching:
            suggestions.append(
                ImprovementSuggestion(
                    id="OPT-001",
                    title="Implement Distributed Redis Read Cache",
                    category="PERFORMANCE",
                    expected_benefit="Reduces database read latency by 60-80% on high-frequency query endpoints.",
                    change_risk=ChangeRisk.LOW,
                    estimated_effort="1-2 Days",
                    affected_nodes=[c.id for c in comps if c.component_type in ["BACKEND", "DATABASE"]],
                    action_plan=[
                        "Provision Redis cluster or local Valkey instance.",
                        "Add cache-aside wrapper on read-heavy service endpoints.",
                        "Set TTL of 300 seconds with event-driven invalidation on data mutations.",
                    ],
                    roi_score=8.5,
                )
            )

        # 2. Resilient Circuit Breakers & Dead-Letter Queue
        unwanted_reqs = [r for r in reqs if r.ears_pattern.value == "UNWANTED_BEHAVIOR"]
        suggestions.append(
            ImprovementSuggestion(
                id="OPT-002",
                title="Integrate Circuit Breaker & Asynchronous Dead-Letter Queue",
                category="RELIABILITY",
                expected_benefit="Prevents cascading failures when third-party or downstream APIs experience latency spikes.",
                change_risk=ChangeRisk.LOW,
                estimated_effort="2-3 Days",
                affected_nodes=[r.id for r in unwanted_reqs] or ["COMP-API"],
                action_plan=[
                    "Wrap external HTTP clients with Polly/Tenacity exponential backoff circuit breakers.",
                    "Route failed transactional tasks to an asynchronous dead-letter queue (DLQ) for inspection.",
                    "Expose health-check `/ready` and `/live` endpoints to load balancer.",
                ],
                roi_score=9.0,
            )
        )

        # 3. Automated Vulnerability Regression Pipeline
        suggestions.append(
            ImprovementSuggestion(
                id="OPT-003",
                title="Automated Continuous Security Regression Scanner",
                category="SECURITY",
                expected_benefit="Converts every discovered security audit finding into an automated pre-merge regression test.",
                change_risk=ChangeRisk.LOW,
                estimated_effort="1 Day",
                affected_nodes=["SECURITY_GATE"],
                action_plan=[
                    "Run `defintra test-pack --type security` in GitHub Actions CI workflow.",
                    "Enforce strict token signature validation and SQL injection fuzz tests on PRs.",
                ],
                roi_score=8.0,
            )
        )

        # 4. Database Indexing & Migration Verification
        suggestions.append(
            ImprovementSuggestion(
                id="OPT-004",
                title="Compound Indexing & Query Plan Optimization",
                category="DATABASE",
                expected_benefit="Eliminates table scans and guarantees sub-50ms execution on critical foreign-key lookups.",
                change_risk=ChangeRisk.MEDIUM,
                estimated_effort="1-2 Days",
                affected_nodes=[c.id for c in comps if c.component_type == "DATABASE"] or ["COMP-DB"],
                action_plan=[
                    "Analyze query EXPLAIN ANALYZE execution plans on high-traffic tables.",
                    "Apply compound B-Tree indexes on `(user_id, status, created_at)`.",
                    "Verify zero table locks during schema migrations with online DDL.",
                ],
                roi_score=7.8,
            )
        )

        return sorted(suggestions, key=lambda s: s.roi_score, reverse=True)
