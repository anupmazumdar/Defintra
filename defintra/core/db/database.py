"""
Defintra Database & Persistence Engine.
Manages local SQLite database, transactions, entity CRUD, and dependency graph persistence.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, List, Optional

from defintra.core.models.entities import (
    ApprovalLevel,
    Approver,
    ArtifactState,
    Assumption,
    ChangeRisk,
    Component,
    Conflict,
    Contract,
    Decision,
    DependencyEdge,
    DependencyKind,
    DiscoveryAuditEntry,
    EARSPattern,
    EntityType,
    Evidence,
    Project,
    Provenance,
    RejectedAlternative,
    Requirement,
    RequirementPriority,
    Unknown,
)
from defintra.core.security.redactor import SecretRedactor


class Database:
    def __init__(self, db_path: str = ".defintra/project.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self):
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            schema_sql = schema_path.read_text(encoding="utf-8")
            with self._get_connection() as conn:
                conn.executescript(schema_sql)
                try:
                    conn.execute("ALTER TABLE projects ADD COLUMN owner_id TEXT;")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                conn.commit()

    # ==========================================
    # Project Operations
    # ==========================================
    def save_project(self, project: Project):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, objective, owner_id, domain, source_type, spec_entropy, spec_health_score, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    objective=excluded.objective,
                    owner_id=excluded.owner_id,
                    domain=excluded.domain,
                    source_type=excluded.source_type,
                    spec_entropy=excluded.spec_entropy,
                    spec_health_score=excluded.spec_health_score,
                    updated_at=excluded.updated_at
                """,
                (
                    project.id,
                    project.name,
                    SecretRedactor.sanitize_all(project.objective),
                    project.owner_id,
                    project.domain,
                    project.source_type,
                    project.spec_entropy,
                    project.spec_health_score,
                    project.created_at,
                    project.updated_at,
                ),
            )
            conn.commit()
        self.seed_default_approvers(project.id)

    def get_project(self, project_id: str) -> Optional[Project]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not row:
                return None
            return Project(
                id=row["id"],
                name=row["name"],
                objective=row["objective"],
                owner_id=row["owner_id"] if "owner_id" in row.keys() else None,
                domain=row["domain"],
                source_type=row["source_type"],
                spec_entropy=row["spec_entropy"],
                spec_health_score=row["spec_health_score"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def get_first_project(self) -> Optional[Project]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM projects ORDER BY created_at ASC LIMIT 1").fetchone()
            if not row:
                return None
            return Project(
                id=row["id"],
                name=row["name"],
                objective=row["objective"],
                owner_id=row["owner_id"] if "owner_id" in row.keys() else None,
                domain=row["domain"],
                source_type=row["source_type"],
                spec_entropy=row["spec_entropy"],
                spec_health_score=row["spec_health_score"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_projects(self) -> List[Project]:
        """
        Lists all projects currently registered in the database.
        """
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
            projects = []
            for row in rows:
                projects.append(
                    Project(
                        id=row["id"],
                        name=row["name"],
                        objective=row["objective"],
                        owner_id=row["owner_id"] if "owner_id" in row.keys() else None,
                        domain=row["domain"],
                        source_type=row["source_type"],
                        spec_entropy=row["spec_entropy"],
                        spec_health_score=row["spec_health_score"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                )
            return projects

    def delete_project(self, project_id: str) -> bool:
        """
        Deletes a project and cascades across all requirements, decisions,
        assumptions, unknowns, components, contracts, and edges.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()
            return cursor.rowcount > 0

    def purge_all(self) -> int:
        """
        Purges all project data and cascaded entities from the SQLite database.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM projects")
            conn.commit()
            return cursor.rowcount

    # ==========================================
    # Requirement Operations
    # ==========================================
    def save_requirement(self, req: Requirement):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO requirements (
                    id, project_id, title, description, ears_pattern, priority, status,
                    category, affected_components_json, constraints_json, acceptance_criteria_json,
                    provenance_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    ears_pattern=excluded.ears_pattern,
                    priority=excluded.priority,
                    status=excluded.status,
                    category=excluded.category,
                    affected_components_json=excluded.affected_components_json,
                    constraints_json=excluded.constraints_json,
                    acceptance_criteria_json=excluded.acceptance_criteria_json,
                    provenance_json=excluded.provenance_json
                """,
                (
                    req.id,
                    req.project_id,
                    SecretRedactor.sanitize_all(req.title),
                    SecretRedactor.sanitize_all(req.description),
                    req.ears_pattern.value,
                    req.priority.value,
                    req.status.value,
                    req.category,
                    json.dumps(req.affected_components),
                    json.dumps([SecretRedactor.sanitize_all(c) for c in req.constraints]),
                    json.dumps([SecretRedactor.sanitize_all(a) for a in req.acceptance_criteria]),
                    req.provenance.model_dump_json(),
                    req.created_at,
                ),
            )
            # Save any attached evidence
            for ev in req.evidence:
                self.save_evidence(ev, conn)
            conn.commit()

    def get_requirements(self, project_id: str) -> List[Requirement]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM requirements WHERE project_id = ? ORDER BY id ASC", (project_id,)).fetchall()
            requirements = []
            for row in rows:
                evs = self.get_evidence(EntityType.REQUIREMENT, row["id"], conn)
                req = Requirement(
                    id=row["id"],
                    project_id=row["project_id"],
                    title=row["title"],
                    description=row["description"],
                    ears_pattern=EARSPattern(row["ears_pattern"]),
                    priority=RequirementPriority(row["priority"]),
                    status=ArtifactState(row["status"]),
                    category=row["category"],
                    affected_components=json.loads(row["affected_components_json"] or "[]"),
                    constraints=json.loads(row["constraints_json"] or "[]"),
                    acceptance_criteria=json.loads(row["acceptance_criteria_json"] or "[]"),
                    provenance=Provenance.model_validate_json(row["provenance_json"]),
                    evidence=evs,
                    created_at=row["created_at"],
                )
                requirements.append(req)
            return requirements

    # ==========================================
    # Decision Ledger Operations
    # ==========================================
    def save_decision(self, dec: Decision):
        with self._get_connection() as conn:
            rejected_alts = [
                {
                    "alternative": SecretRedactor.sanitize_all(alt.alternative),
                    "reason_rejected": SecretRedactor.sanitize_all(alt.reason_rejected),
                    "proposed_by": alt.proposed_by,
                }
                for alt in dec.rejected_alternatives
            ]
            conn.execute(
                """
                INSERT INTO decisions (
                    id, project_id, title, decision, reason, rejected_alternatives_json,
                    status, approval_level, change_risk, superseded_by,
                    affected_components_json, provenance_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    decision=excluded.decision,
                    reason=excluded.reason,
                    rejected_alternatives_json=excluded.rejected_alternatives_json,
                    status=excluded.status,
                    approval_level=excluded.approval_level,
                    change_risk=excluded.change_risk,
                    superseded_by=excluded.superseded_by,
                    affected_components_json=excluded.affected_components_json,
                    provenance_json=excluded.provenance_json
                """,
                (
                    dec.id,
                    dec.project_id,
                    SecretRedactor.sanitize_all(dec.title),
                    SecretRedactor.sanitize_all(dec.decision),
                    SecretRedactor.sanitize_all(dec.reason),
                    json.dumps(rejected_alts),
                    dec.status.value,
                    dec.approval_level.value,
                    dec.change_risk.value,
                    dec.superseded_by,
                    json.dumps(dec.affected_components),
                    dec.provenance.model_dump_json(),
                    dec.created_at,
                ),
            )
            for ev in dec.evidence:
                self.save_evidence(ev, conn)
            conn.commit()

    def get_decisions(self, project_id: str) -> List[Decision]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM decisions WHERE project_id = ? ORDER BY id ASC", (project_id,)).fetchall()
            decisions = []
            for row in rows:
                evs = self.get_evidence(EntityType.DECISION, row["id"], conn)
                rejected_data = json.loads(row["rejected_alternatives_json"] or "[]")
                rejected_alts = [RejectedAlternative(**alt) for alt in rejected_data]
                dec = Decision(
                    id=row["id"],
                    project_id=row["project_id"],
                    title=row["title"],
                    decision=row["decision"],
                    reason=row["reason"],
                    rejected_alternatives=rejected_alts,
                    status=ArtifactState(row["status"]),
                    approval_level=ApprovalLevel(row["approval_level"]),
                    change_risk=ChangeRisk(row["change_risk"]),
                    superseded_by=row["superseded_by"],
                    affected_components=json.loads(row["affected_components_json"] or "[]"),
                    provenance=Provenance.model_validate_json(row["provenance_json"]),
                    evidence=evs,
                    created_at=row["created_at"],
                )
                decisions.append(dec)
            return decisions

    # ==========================================
    # Assumptions & Unknowns
    # ==========================================
    def save_assumption(self, asm: Assumption):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO assumptions (id, project_id, statement, category, confidence, status, provenance_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    statement=excluded.statement,
                    category=excluded.category,
                    confidence=excluded.confidence,
                    status=excluded.status,
                    provenance_json=excluded.provenance_json
                """,
                (
                    asm.id,
                    asm.project_id,
                    SecretRedactor.sanitize_all(asm.statement),
                    asm.category,
                    asm.confidence,
                    asm.status,
                    asm.provenance.model_dump_json(),
                    asm.created_at,
                ),
            )
            for ev in asm.evidence:
                self.save_evidence(ev, conn)
            conn.commit()

    def get_assumptions(self, project_id: str) -> List[Assumption]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM assumptions WHERE project_id = ? ORDER BY id ASC", (project_id,)).fetchall()
            assumptions = []
            for row in rows:
                evs = self.get_evidence(EntityType.ASSUMPTION, row["id"], conn)
                asm = Assumption(
                    id=row["id"],
                    project_id=row["project_id"],
                    statement=row["statement"],
                    category=row["category"],
                    confidence=row["confidence"],
                    status=row["status"],
                    provenance=Provenance.model_validate_json(row["provenance_json"]),
                    evidence=evs,
                    created_at=row["created_at"],
                )
                assumptions.append(asm)
            return assumptions

    def save_unknown(self, unk: Unknown):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO unknowns (id, project_id, question, impact, category, status, resolution, priority_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    question=excluded.question,
                    impact=excluded.impact,
                    category=excluded.category,
                    status=excluded.status,
                    resolution=excluded.resolution,
                    priority_order=excluded.priority_order
                """,
                (
                    unk.id,
                    unk.project_id,
                    SecretRedactor.sanitize_all(unk.question),
                    unk.impact,
                    unk.category,
                    unk.status,
                    SecretRedactor.sanitize_all(unk.resolution) if unk.resolution else None,
                    unk.priority_order,
                    unk.created_at,
                ),
            )
            conn.commit()

    def get_unknowns(self, project_id: str, status_filter: Optional[str] = None) -> List[Unknown]:
        with self._get_connection() as conn:
            if status_filter:
                rows = conn.execute(
                    "SELECT * FROM unknowns WHERE project_id = ? AND status = ? ORDER BY priority_order ASC, id ASC",
                    (project_id, status_filter),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM unknowns WHERE project_id = ? ORDER BY priority_order ASC, id ASC",
                    (project_id,),
                ).fetchall()
            return [
                Unknown(
                    id=row["id"],
                    project_id=row["project_id"],
                    question=row["question"],
                    impact=row["impact"],
                    category=row["category"],
                    status=row["status"],
                    resolution=row["resolution"],
                    priority_order=row["priority_order"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    # ==========================================
    # Evidence Layer
    # ==========================================
    def save_evidence(self, ev: Evidence, conn: Optional[sqlite3.Connection] = None):
        def _exec(c):
            c.execute(
                """
                INSERT INTO evidence (id, target_entity_type, target_entity_id, evidence_type, description, confidence, source, approved_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    description=excluded.description,
                    confidence=excluded.confidence,
                    source=excluded.source,
                    approved_by=excluded.approved_by
                """,
                (
                    ev.id,
                    ev.target_entity_type.value,
                    ev.target_entity_id,
                    ev.evidence_type,
                    SecretRedactor.sanitize_all(ev.description),
                    ev.confidence,
                    SecretRedactor.sanitize_all(ev.source),
                    ev.approved_by,
                    ev.created_at,
                ),
            )

        if conn:
            _exec(conn)
        else:
            with self._get_connection() as c:
                _exec(c)
                c.commit()

    def get_evidence(self, entity_type: EntityType, entity_id: str, conn: Optional[sqlite3.Connection] = None) -> List[Evidence]:
        query = "SELECT * FROM evidence WHERE target_entity_type = ? AND target_entity_id = ?"
        params = (entity_type.value, entity_id)

        if conn:
            rows = conn.execute(query, params).fetchall()
        else:
            with self._get_connection() as c:
                rows = c.execute(query, params).fetchall()

        return [
            Evidence(
                id=row["id"],
                target_entity_type=EntityType(row["target_entity_type"]),
                target_entity_id=row["target_entity_id"],
                evidence_type=row["evidence_type"],
                description=row["description"],
                confidence=row["confidence"],
                source=row["source"],
                approved_by=row["approved_by"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # ==========================================
    # Discovery Audit Log
    # ==========================================
    def save_audit_entry(self, entry: DiscoveryAuditEntry):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO discovery_audit_log (id, project_id, silent_assumption, reason_skipped, risk_level, category, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    silent_assumption=excluded.silent_assumption,
                    reason_skipped=excluded.reason_skipped,
                    risk_level=excluded.risk_level,
                    category=excluded.category
                """,
                (
                    entry.id,
                    entry.project_id,
                    SecretRedactor.sanitize_all(entry.silent_assumption),
                    SecretRedactor.sanitize_all(entry.reason_skipped),
                    entry.risk_level.value,
                    entry.category,
                    entry.created_at,
                ),
            )
            conn.commit()

    def get_audit_entries(self, project_id: str) -> List[DiscoveryAuditEntry]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM discovery_audit_log WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
            return [
                DiscoveryAuditEntry(
                    id=row["id"],
                    project_id=row["project_id"],
                    silent_assumption=row["silent_assumption"],
                    reason_skipped=row["reason_skipped"],
                    risk_level=ChangeRisk(row["risk_level"]),
                    category=row["category"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    # ==========================================
    # Components, Contracts, Conflicts
    # ==========================================
    def save_component(self, comp: Component):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO components (id, project_id, name, component_type, description, stability_state, blast_radius_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    component_type=excluded.component_type,
                    description=excluded.description,
                    stability_state=excluded.stability_state,
                    blast_radius_json=excluded.blast_radius_json
                """,
                (
                    comp.id,
                    comp.project_id,
                    SecretRedactor.sanitize_all(comp.name),
                    comp.component_type,
                    SecretRedactor.sanitize_all(comp.description),
                    comp.stability_state.value,
                    json.dumps(comp.blast_radius),
                    comp.created_at,
                ),
            )
            conn.commit()

    def get_components(self, project_id: str) -> List[Component]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM components WHERE project_id = ? ORDER BY id ASC", (project_id,)).fetchall()
            return [
                Component(
                    id=row["id"],
                    project_id=row["project_id"],
                    name=row["name"],
                    component_type=row["component_type"],
                    description=row["description"],
                    stability_state=ArtifactState(row["stability_state"]),
                    blast_radius=json.loads(row["blast_radius_json"] or "[]"),
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    def save_contract(self, contract: Contract):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO contracts (id, project_id, name, contract_type, version, specification_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    contract_type=excluded.contract_type,
                    version=excluded.version,
                    specification_json=excluded.specification_json,
                    status=excluded.status
                """,
                (
                    contract.id,
                    contract.project_id,
                    contract.name,
                    contract.contract_type,
                    contract.version,
                    json.dumps(contract.specification),
                    contract.status.value,
                    contract.created_at,
                ),
            )
            conn.commit()

    def get_contracts(self, project_id: str) -> List[Contract]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM contracts WHERE project_id = ? ORDER BY id ASC", (project_id,)).fetchall()
            return [
                Contract(
                    id=row["id"],
                    project_id=row["project_id"],
                    name=row["name"],
                    contract_type=row["contract_type"],
                    version=row["version"],
                    specification=json.loads(row["specification_json"] or "{}"),
                    status=ArtifactState(row["status"]),
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    def save_conflict(self, conflict: Conflict):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conflicts (id, project_id, title, description, entity_a_ref, entity_b_ref, severity, status, resolution, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    entity_a_ref=excluded.entity_a_ref,
                    entity_b_ref=excluded.entity_b_ref,
                    severity=excluded.severity,
                    status=excluded.status,
                    resolution=excluded.resolution
                """,
                (
                    conflict.id,
                    conflict.project_id,
                    SecretRedactor.sanitize_all(conflict.title),
                    SecretRedactor.sanitize_all(conflict.description),
                    conflict.entity_a_ref,
                    conflict.entity_b_ref,
                    conflict.severity,
                    conflict.status,
                    SecretRedactor.sanitize_all(conflict.resolution) if conflict.resolution else None,
                    conflict.created_at,
                ),
            )
            conn.commit()

    def get_conflicts(self, project_id: str) -> List[Conflict]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM conflicts WHERE project_id = ? ORDER BY id ASC", (project_id,)).fetchall()
            return [
                Conflict(
                    id=row["id"],
                    project_id=row["project_id"],
                    title=row["title"],
                    description=row["description"],
                    entity_a_ref=row["entity_a_ref"],
                    entity_b_ref=row["entity_b_ref"],
                    severity=row["severity"],
                    status=row["status"],
                    resolution=row["resolution"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    # ==========================================
    # Dependency Graph Edges
    # ==========================================
    def save_dependency(self, dep: DependencyEdge):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dependencies (id, project_id, source_type, source_id, target_type, target_id, dependency_kind, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    dependency_kind=excluded.dependency_kind,
                    description=excluded.description
                """,
                (
                    dep.id,
                    dep.project_id,
                    dep.source_type.value,
                    dep.source_id,
                    dep.target_type.value,
                    dep.target_id,
                    dep.dependency_kind.value,
                    dep.description,
                    dep.created_at,
                ),
            )
            conn.commit()

    def get_dependencies(self, project_id: str) -> List[DependencyEdge]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM dependencies WHERE project_id = ? ORDER BY id ASC", (project_id,)).fetchall()
            return [
                DependencyEdge(
                    id=row["id"],
                    project_id=row["project_id"],
                    source_type=EntityType(row["source_type"]),
                    source_id=row["source_id"],
                    target_type=EntityType(row["target_type"]),
                    target_id=row["target_id"],
                    dependency_kind=DependencyKind(row["dependency_kind"]),
                    description=row["description"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    # ==========================================
    # Benchmark Operations (§40, §46)
    # ==========================================
    def save_benchmark(self, bm_data: dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO benchmarks (
                    id, project_id, input_summary, defintra_req_count, defintra_health_score,
                    defintra_entropy, defintra_token_count, defintra_duration_ms, naive_req_count,
                    naive_token_count, naive_duration_ms, comparison_summary, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    defintra_req_count=excluded.defintra_req_count,
                    defintra_health_score=excluded.defintra_health_score,
                    defintra_entropy=excluded.defintra_entropy,
                    defintra_token_count=excluded.defintra_token_count,
                    defintra_duration_ms=excluded.defintra_duration_ms,
                    naive_req_count=excluded.naive_req_count,
                    naive_token_count=excluded.naive_token_count,
                    naive_duration_ms=excluded.naive_duration_ms,
                    comparison_summary=excluded.comparison_summary
                """,
                (
                    bm_data["id"],
                    bm_data["project_id"],
                    bm_data["input_summary"],
                    bm_data.get("defintra_req_count", 0),
                    bm_data.get("defintra_health_score", 0.0),
                    bm_data.get("defintra_entropy", 1.0),
                    bm_data.get("defintra_token_count", 0),
                    bm_data.get("defintra_duration_ms", 0.0),
                    bm_data.get("naive_req_count", 0),
                    bm_data.get("naive_token_count", 0),
                    bm_data.get("naive_duration_ms", 0.0),
                    bm_data.get("comparison_summary", ""),
                    bm_data["created_at"],
                ),
            )
            conn.commit()

    def get_benchmarks(self, project_id: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM benchmarks WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM benchmarks ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    # ==========================================
    # Approver Operations (§45)
    # ==========================================
    def save_approver(self, approver: Approver):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO approvers (id, project_id, name, role, is_admin, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, name) DO UPDATE SET
                    id=excluded.id,
                    role=excluded.role,
                    is_admin=excluded.is_admin
                """,
                (
                    approver.id,
                    approver.project_id,
                    approver.name,
                    approver.role,
                    1 if approver.is_admin else 0,
                    approver.created_at,
                ),
            )
            conn.commit()

    def get_approvers(self, project_id: str) -> List[Approver]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, project_id, name, role, is_admin, created_at FROM approvers WHERE project_id = ? ORDER BY name ASC",
                (project_id,),
            ).fetchall()
            return [
                Approver(
                    id=r["id"],
                    project_id=r["project_id"],
                    name=r["name"],
                    role=r["role"],
                    is_admin=bool(r["is_admin"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def get_approver(self, project_id: str, identifier: str) -> Optional[Approver]:
        clean_id = identifier.strip().lower()
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, project_id, name, role, is_admin, created_at FROM approvers WHERE project_id = ? AND (LOWER(id) = ? OR LOWER(name) = ?)",
                (project_id, clean_id, clean_id),
            ).fetchone()
            if not row:
                return None
            return Approver(
                id=row["id"],
                project_id=row["project_id"],
                name=row["name"],
                role=row["role"],
                is_admin=bool(row["is_admin"]),
                created_at=row["created_at"],
            )

    def delete_approver(self, project_id: str, approver_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM approvers WHERE project_id = ? AND (id = ? OR name = ?)",
                (project_id, approver_id, approver_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def seed_default_approvers(self, project_id: str):
        default_approvers = [
            Approver(id=f"appr_{project_id}_devlead", project_id=project_id, name="DevLead", role="ADMIN", is_admin=True),
            Approver(id=f"appr_{project_id}_seclead", project_id=project_id, name="SecurityLead", role="ADMIN", is_admin=True),
            Approver(id=f"appr_{project_id}_engineer", project_id=project_id, name="Engineer", role="USER", is_admin=False),
        ]
        for a in default_approvers:
            try:
                self.save_approver(a)
            except Exception:
                pass

