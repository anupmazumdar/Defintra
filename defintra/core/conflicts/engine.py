"""
Conflict Detection & Resolution Engine (§18, §48).
Identifies contradictions between requirements, architectural decisions,
and constraints, and provides deterministic resolution workflows.
"""

from typing import List, Optional

from defintra.core.db.database import Database
from defintra.core.entropy.calculator import EntropyCalculator
from defintra.core.models.entities import (
    ArtifactState,
    Conflict,
)
from defintra.core.security.redactor import SecretRedactor


class ConflictEngine:
    def __init__(self, db: Database):
        self.db = db

    def detect_conflicts(self, project_id: str) -> List[Conflict]:
        """
        Scans project knowledge graph for structural and semantic contradictions (§18).
        """
        reqs = self.db.get_requirements(project_id)
        decs = self.db.get_decisions(project_id)
        asms = self.db.get_assumptions(project_id)
        existing_conflicts = {c.id: c for c in self.db.get_conflicts(project_id)}

        discovered: List[Conflict] = []

        # 1. Check for Contradictions between Decisions and Requirements
        for d in decs:
            d_text = (d.title + " " + d.decision + " " + d.reason).lower()
            for r in reqs:
                r_text = (r.title + " " + r.description + " " + " ".join(r.constraints)).lower()

                # Offline vs No-Local-Storage Conflict
                if ("offline" in r_text or "local cache" in r_text) and ("stateless only" in d_text or "no local storage" in d_text):
                    cid = f"CONF-OFFLINE_{d.id}_{r.id}"
                    if cid not in existing_conflicts:
                        c = Conflict(
                            id=cid,
                            project_id=project_id,
                            title="Offline Requirement Clashes with Stateless Decision",
                            description=f"Requirement '{r.title}' demands offline capabilities, but Decision '{d.title}' enforces stateless/no-local-storage architecture.",
                            entity_a_ref=r.id,
                            entity_b_ref=d.id,
                            severity="HIGH",
                            status="OPEN",
                        )
                        self.db.save_conflict(c)
                        discovered.append(c)

                # Database Choice vs Query Requirement Conflict
                if "sqlite" in d_text and any("distributed transactions" in c.lower() for c in r.constraints):
                    cid = f"CONF-DB-SCALE_{d.id}_{r.id}"
                    if cid not in existing_conflicts:
                        c = Conflict(
                            id=cid,
                            project_id=project_id,
                            title="Database Engine Scalability Incompatibility",
                            description=f"Requirement constraint on distributed transactions conflicts with SQLite Decision '{d.id}'.",
                            entity_a_ref=d.id,
                            entity_b_ref=r.id,
                            severity="CRITICAL",
                            status="OPEN",
                        )
                        self.db.save_conflict(c)
                        discovered.append(c)

        # 2. Check for Conflicting Decisions (Duplicate titles or opposite choices)
        for i, d1 in enumerate(decs):
            for d2 in decs[i + 1 :]:
                if d1.id != d2.id and d1.title.lower() == d2.title.lower() and d1.status != ArtifactState.SUPERSEDED and d2.status != ArtifactState.SUPERSEDED:
                    cid = f"CONF-DEC_{d1.id}_{d2.id}"
                    if cid not in existing_conflicts:
                        c = Conflict(
                            id=cid,
                            project_id=project_id,
                            title=f"Multiple Active Decisions for '{d1.title}'",
                            description=f"Decisions '{d1.id}' ({d1.decision}) and '{d2.id}' ({d2.decision}) both claim active status for the same topic.",
                            entity_a_ref=d1.id,
                            entity_b_ref=d2.id,
                            severity="HIGH",
                            status="OPEN",
                        )
                        self.db.save_conflict(c)
                        discovered.append(c)

        # 3. Check for Assumptions Refuted by Approved Decisions
        for a in asms:
            if a.status == "ACTIVE":
                a_text = a.statement.lower()
                for d in decs:
                    if d.status == ArtifactState.APPROVED:
                        d_text = (d.decision + " " + d.reason).lower()
                        if "nosql" in a_text and "relational" in d_text:
                            cid = f"CONF-ASM_{a.id}_{d.id}"
                            if cid not in existing_conflicts:
                                c = Conflict(
                                    id=cid,
                                    project_id=project_id,
                                    title="Active Assumption Refuted by Approved Decision",
                                    description=f"Assumption '{a.statement}' assumes NoSQL, but Decision '{d.title}' approved Relational DB.",
                                    entity_a_ref=a.id,
                                    entity_b_ref=d.id,
                                    severity="MEDIUM",
                                    status="OPEN",
                                )
                                self.db.save_conflict(c)
                                discovered.append(c)

        # Recalculate health
        self._recalculate_health(project_id)
        return self.db.get_conflicts(project_id)

    def resolve_conflict(
        self,
        project_id: str,
        conflict_id: str,
        resolution_notes: str,
        winning_entity_id: Optional[str] = None,
    ) -> Conflict:
        """
        Resolves a conflict, updates affected entities, and reduces project entropy (§18, §48).
        """
        conflicts = self.db.get_conflicts(project_id)
        target = next((c for c in conflicts if c.id == conflict_id), None)
        if not target:
            raise ValueError(f"Conflict with ID '{conflict_id}' not found in project '{project_id}'.")

        target.status = "RESOLVED"
        target.resolution = SecretRedactor.sanitize_all(resolution_notes)
        self.db.save_conflict(target)

        # If a winning entity was chosen, update the loser
        if winning_entity_id:
            loser_id = target.entity_b_ref if winning_entity_id == target.entity_a_ref else target.entity_a_ref

            # Check if loser is an assumption -> mark REFUTED
            asms = self.db.get_assumptions(project_id)
            loser_asm = next((a for a in asms if a.id == loser_id), None)
            if loser_asm:
                loser_asm.status = "REFUTED"
                self.db.save_assumption(loser_asm)

            # Check if loser is a decision -> mark SUPERSEDED / CONFLICTED
            decs = self.db.get_decisions(project_id)
            loser_dec = next((d for d in decs if d.id == loser_id), None)
            if loser_dec:
                loser_dec.status = ArtifactState.SUPERSEDED
                loser_dec.superseded_by = winning_entity_id
                self.db.save_decision(loser_dec)

        self._recalculate_health(project_id)
        return target

    def _recalculate_health(self, project_id: str):
        reqs = self.db.get_requirements(project_id)
        decs = self.db.get_decisions(project_id)
        asms = self.db.get_assumptions(project_id)
        unks = self.db.get_unknowns(project_id)
        conflicts = self.db.get_conflicts(project_id)

        report = EntropyCalculator.compute(reqs, decs, asms, unks, conflicts)
        project = self.db.get_project(project_id)
        if project:
            project.spec_entropy = report.entropy
            project.spec_health_score = report.health_score
            self.db.save_project(project)
