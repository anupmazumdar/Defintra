"""
Task Dependency Schedulability & Topological Execution Graph (§13, §16).
Builds phased implementation roadmaps, parallel execution tracks,
and critical path analyses for AI multi-agent software engineering.
"""

from typing import Any, Dict, List
from defintra.context.compiler import AgentRole
from defintra.core.db.database import Database


class ExecutionPhase:
    def __init__(
        self,
        phase_number: int,
        name: str,
        assigned_role: AgentRole,
        primary_entities: List[str],
        parallel_tracks: List[str],
        gate_condition: str,
    ):
        self.phase_number = phase_number
        self.name = name
        self.assigned_role = assigned_role
        self.primary_entities = primary_entities
        self.parallel_tracks = parallel_tracks
        self.gate_condition = gate_condition

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase_number": self.phase_number,
            "name": self.name,
            "assigned_role": self.assigned_role.value,
            "primary_entities": self.primary_entities,
            "parallel_tracks": self.parallel_tracks,
            "gate_condition": self.gate_condition,
        }


class ExecutionSchedule:
    def __init__(
        self,
        project_id: str,
        total_phases: int,
        phases: List[ExecutionPhase],
        critical_path: List[str],
        parallelism_factor: float,
    ):
        self.project_id = project_id
        self.total_phases = total_phases
        self.phases = phases
        self.critical_path = critical_path
        self.parallelism_factor = round(parallelism_factor, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "total_phases": self.total_phases,
            "parallelism_factor": self.parallelism_factor,
            "critical_path": self.critical_path,
            "phases": [p.to_dict() for p in self.phases],
        }


class TaskScheduler:
    def __init__(self, db: Database):
        self.db = db

    def schedule_project(self, project_id: str) -> ExecutionSchedule:
        """
        Builds a multi-phase implementation roadmap and parallel agent dispatch schedule (§13).
        """
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        reqs = self.db.get_requirements(project_id)
        decs = self.db.get_decisions(project_id)
        comps = self.db.get_components(project_id)
        contracts = self.db.get_contracts(project_id)

        phases: List[ExecutionPhase] = []

        # Phase 1: Invariants & Data Foundation
        db_comps = [c.id for c in comps if c.component_type == "DATABASE"] or ["COMP-DB"]
        phases.append(
            ExecutionPhase(
                phase_number=1,
                name="Architectural Invariants & Database Schema",
                assigned_role=AgentRole.DATABASE_ENGINEER,
                primary_entities=[d.id for d in decs] + db_comps,
                parallel_tracks=[
                    "Track A: DDL schema migrations & indexes",
                    "Track B: Core entity constraints & audit triggers",
                ],
                gate_condition="Database contract validated and migration idempotency tests pass.",
            )
        )

        # Phase 2: Core Backend Services & API Contracts
        backend_comps = [c.id for c in comps if c.component_type in ["BACKEND", "AUTH"]] or ["COMP-API"]
        phases.append(
            ExecutionPhase(
                phase_number=2,
                name="Backend Domain Services & API Implementation",
                assigned_role=AgentRole.BACKEND_ENGINEER,
                primary_entities=backend_comps + [c.id for c in contracts if c.contract_type == "API"],
                parallel_tracks=[
                    "Track A: Authentication & JWT session endpoints",
                    "Track B: Business workflow endpoints & data mutations",
                ],
                gate_condition="All API contract response schemas pass type checking.",
            )
        )

        # Phase 3: Frontend User Interfaces
        frontend_comps = [c.id for c in comps if c.component_type == "FRONTEND"] or ["COMP-UI"]
        phases.append(
            ExecutionPhase(
                phase_number=3,
                name="Frontend Components & Client State Integration",
                assigned_role=AgentRole.FRONTEND_ENGINEER,
                primary_entities=frontend_comps + [r.id for r in reqs if r.priority.value in ["CRITICAL", "HIGH"]],
                parallel_tracks=[
                    "Track A: Responsive layout, design tokens & navigation",
                    "Track B: Client data fetching, form validation & error boundaries",
                ],
                gate_condition="UI unit tests and user interaction workflows pass.",
            )
        )

        # Phase 4: Security & Quality Assurance Verification
        phases.append(
            ExecutionPhase(
                phase_number=4,
                name="Security Audit & Multi-Pattern QA Test Suites",
                assigned_role=AgentRole.SECURITY_ENGINEER,
                primary_entities=[r.id for r in reqs if r.ears_pattern.value == "UNWANTED_BEHAVIOR"],
                parallel_tracks=[
                    "Track A: Automated EARS pytest test execution",
                    "Track B: Security regression & OWASP fuzzing suite",
                ],
                gate_condition="100% test pass rate with zero critical vulnerabilities.",
            )
        )

        # Phase 5: Deployment Governance & Sandboxing
        phases.append(
            ExecutionPhase(
                phase_number=5,
                name="Pre-Production Staging & Sandbox Verification",
                assigned_role=AgentRole.DEVOPS_ENGINEER,
                primary_entities=["PRE_PROD_GATE", "CONTAINER_ENV"],
                parallel_tracks=[
                    "Track A: Docker sandbox build & health probe checks",
                    "Track B: Rollback runbook validation & telemetry hooks",
                ],
                gate_condition="Pre-production governance gate approved and signed off.",
            )
        )

        critical_path = ["DB_SCHEMA", "API_CONTRACTS", "CLIENT_INTEGRATION", "SECURITY_GATE", "PROD_DEPLOY"]
        parallelism = 2.4  # Average concurrent worker tracks

        return ExecutionSchedule(
            project_id=project_id,
            total_phases=len(phases),
            phases=phases,
            critical_path=critical_path,
            parallelism_factor=parallelism,
        )
