import tempfile
import os
import pytest
from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine


import gc

@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)
    yield db
    del db
    gc.collect()
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception:
        pass


def test_discovery_fast_path_and_audit_log(temp_db):
    engine = DiscoveryEngine(temp_db)
    prompt = "I want to build a mobile attendance system for college professors and students."

    project = engine.run_fast_path("Attendance App", prompt)
    assert project.id == "attendance_app"
    assert project.domain == "COLLEGE_STUDENT"

    reqs = temp_db.get_requirements(project.id)
    assert len(reqs) >= 3
    assert any("authenticate" in r.description for r in reqs)

    decs = temp_db.get_decisions(project.id)
    assert len(decs) >= 1
    assert any(len(d.rejected_alternatives) > 0 for d in decs)

    unks = temp_db.get_unknowns(project.id)
    assert len(unks) >= 2

    # Discovery Audit Log (Silent Assumptions §17)
    audit = temp_db.get_audit_entries(project.id)
    assert len(audit) >= 1
    assert any("Multi-tenancy" in a.silent_assumption or "English" in a.silent_assumption for a in audit)


def test_questioning_resolves_unknown_and_boosts_health(temp_db):
    engine = DiscoveryEngine(temp_db)
    project = engine.run_fast_path("SaaS Platform", "Build a subscription-based video transcription SaaS.")

    initial_health = project.spec_health_score
    unknowns = temp_db.get_unknowns(project.id, status_filter="OPEN")
    assert len(unknowns) > 0

    first_unk = unknowns[0]
    report = engine.answer_unknown(
        project.id,
        first_unk.id,
        "We will use Stripe for monthly and annual tiered subscriptions.",
    )

    assert report.health_score >= initial_health
    updated_unk = next(u for u in temp_db.get_unknowns(project.id) if u.id == first_unk.id)
    assert updated_unk.status == "RESOLVED"
    assert "Stripe" in updated_unk.resolution
