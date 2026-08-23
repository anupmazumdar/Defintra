import pytest
from defintra.core.entropy.calculator import EntropyCalculator
from defintra.core.models.entities import (
    ArtifactState,
    Assumption,
    Conflict,
    Decision,
    EARSPattern,
    Provenance,
    Requirement,
    RequirementPriority,
    Unknown,
)


def test_entropy_computation_unresolved_unknowns():
    reqs = [
        Requirement(
            id="R-1",
            project_id="p1",
            title="Auth",
            description="The System shall authenticate.",
            ears_pattern=EARSPattern.UBIQUITOUS,
            priority=RequirementPriority.HIGH,
            status=ArtifactState.APPROVED,
            provenance=Provenance(source="User", confidence=0.9),
        )
    ]
    decs = [
        Decision(
            id="D-1",
            project_id="p1",
            title="Database",
            decision="Postgres",
            reason="Relational safety",
            status=ArtifactState.APPROVED,
            provenance=Provenance(source="User", confidence=0.95),
        )
    ]
    asms = []
    unks = [
        Unknown(id="U-1", project_id="p1", question="What auth method?", impact="HIGH", category="SECURITY", status="OPEN"),
        Unknown(id="U-2", project_id="p1", question="What hosting provider?", impact="HIGH", category="DEPLOYMENT", status="OPEN"),
    ]
    conflicts = []

    report_with_unknowns = EntropyCalculator.compute(reqs, decs, asms, unks, conflicts)
    assert report_with_unknowns.entropy > 0.1
    assert any("Resolve" in rec for rec in report_with_unknowns.recommendations)

    # Now resolve unknowns
    resolved_unks = [
        Unknown(id="U-1", project_id="p1", question="What auth method?", impact="HIGH", category="SECURITY", status="RESOLVED"),
        Unknown(id="U-2", project_id="p1", question="What hosting provider?", impact="HIGH", category="DEPLOYMENT", status="RESOLVED"),
    ]
    report_resolved = EntropyCalculator.compute(reqs, decs, asms, resolved_unks, conflicts)

    # Health score must improve when unknowns are resolved
    assert report_resolved.health_score > report_with_unknowns.health_score
    assert report_resolved.entropy < report_with_unknowns.entropy


def test_entropy_with_conflicts():
    reqs = []
    decs = []
    asms = []
    unks = []
    conflicts = [
        Conflict(
            id="C-1",
            project_id="p1",
            title="Auth conflict",
            description="SSO vs Local password conflict",
            entity_a_ref="D-1",
            entity_b_ref="D-2",
            severity="CRITICAL",
            status="OPEN",
        )
    ]

    report = EntropyCalculator.compute(reqs, decs, asms, unks, conflicts)
    assert report.entropy > 0.2
    assert any("Conflict" in rec for rec in report.recommendations)
