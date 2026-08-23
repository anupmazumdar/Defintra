import pytest

from defintra.context.compiler import AgentRole
from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.team.coordinator import StructuredEventType, TeamCoordinator


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_team.db"
    return Database(str(db_file))


def test_team_coordinator_dispatch_and_routing(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Team Orchestration App", "Build SaaS billing engine with Stripe")

    coordinator = TeamCoordinator(test_db)

    # 1. Model routing check
    routing_arch = coordinator.route_model(AgentRole.SOFTWARE_ARCHITECT)
    assert "Claude" in routing_arch.recommended_model

    routing_qa = coordinator.route_model(AgentRole.QA_ENGINEER)
    assert "Gemini" in routing_qa.recommended_model

    # 2. Task dispatch
    dispatch = coordinator.dispatch_task(
        project_id=project.id,
        task_title="Design database schema and isolation model",
        role=AgentRole.DATABASE_ENGINEER,
    )
    assert dispatch["assigned_role"] == "DATABASE_ENGINEER"
    assert "routing" in dispatch
    assert dispatch["compiled_context_summary"]["requirements_count"] > 0

    # 3. Events log check
    events = coordinator.get_events(project.id)
    assert len(events) >= 1
    assert events[0]["event_type"] == StructuredEventType.CHANGE_REQUEST.value
