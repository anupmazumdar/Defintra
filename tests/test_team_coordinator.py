from unittest.mock import MagicMock, patch

import pytest

from defintra.context.compiler import AgentRole
from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.discovery.llm import LLMResponse
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
    assert "GPT-4o" in routing_arch.fallback_model

    routing_qa = coordinator.route_model(AgentRole.QA_ENGINEER)
    assert "Gemini" in routing_qa.recommended_model
    assert "Claude" in routing_qa.fallback_model

    # 2. Task dispatch & Execution (offline heuristic mode)
    dispatch = coordinator.dispatch_task(
        project_id=project.id,
        task_title="Design database schema and isolation model",
        role=AgentRole.DATABASE_ENGINEER,
        execute=True,
        action_type="read_repository",
    )
    assert dispatch["assigned_role"] == "DATABASE_ENGINEER"
    assert "routing" in dispatch
    assert dispatch["compiled_context_summary"]["requirements_count"] > 0
    assert "execution_output" in dispatch
    assert len(dispatch["execution_output"]) > 0
    assert dispatch["provider"] == "MockHeuristicLLMProvider"
    assert dispatch["is_mock"] is True

    # 3. Events log check
    events = coordinator.get_events(project.id)
    assert len(events) >= 2
    event_types = [e["event_type"] for e in events]
    assert StructuredEventType.POLICY_CHECK.value in event_types
    assert StructuredEventType.TASK_COMPLETED.value in event_types


def test_team_coordinator_routing_only_mode(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Routing Only App", "Simple prototype")
    coordinator = TeamCoordinator(test_db)

    dispatch = coordinator.dispatch_task(
        project_id=project.id,
        task_title="Review security posture",
        role=AgentRole.SECURITY_ENGINEER,
        execute=False,
    )
    assert dispatch["status"] == "ROUTED"
    assert dispatch["provider"] == "None (Routing Only)"
    assert dispatch["is_mock"] is False


def test_team_coordinator_adaptive_retry_and_fallback(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Adaptive App", "High reliability system")
    coordinator = TeamCoordinator(test_db)

    # Simulate primary model failing validation (empty response), then retry succeeding
    mock_provider = MagicMock()
    mock_provider.generate.side_effect = [
        LLMResponse(content=""),  # Attempt 1: fails validation (< 20 chars)
        LLMResponse(content="Valid detailed architecture and schema specifications for the service."),  # Attempt 2: succeeds
    ]

    with patch("defintra.core.discovery.llm.get_llm_provider", return_value=mock_provider):
        dispatch = coordinator.dispatch_task(
            project_id=project.id,
            task_title="Design rate limiting subsystem",
            role=AgentRole.BACKEND_ENGINEER,
            execute=True,
            action_type="read_repository",
        )

        assert dispatch["status"] == "COMPLETED"
        assert len(dispatch["attempts_log"]) == 2
        assert dispatch["attempts_log"][0]["valid"] is False
        assert dispatch["attempts_log"][1]["valid"] is True

        events = coordinator.get_events(project.id)
        event_types = [e["event_type"] for e in events]
        assert StructuredEventType.TASK_ATTEMPTED.value in event_types
        assert StructuredEventType.TASK_RETRIED.value in event_types
        assert StructuredEventType.TASK_COMPLETED.value in event_types


def test_team_coordinator_fallback_model_trigger(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Fallback App", "High reliability system")
    coordinator = TeamCoordinator(test_db)

    # Primary model fails attempt 1 and attempt 2, fallback model succeeds on attempt 3
    mock_primary = MagicMock()
    mock_primary.generate.side_effect = [
        LLMResponse(content=""),
        LLMResponse(content="too short"),
    ]

    mock_fallback = MagicMock()
    mock_fallback.generate.return_value = LLMResponse(
        content="Fallback model successfully generated full comprehensive component design.",
    )

    def mock_get_provider(model_name=""):
        if "GPT-4o" in model_name or "Fallback" in model_name:
            return mock_fallback
        return mock_primary

    with patch("defintra.core.discovery.llm.get_llm_provider", side_effect=mock_get_provider):
        dispatch = coordinator.dispatch_task(
            project_id=project.id,
            task_title="Design high concurrency caching subsystem",
            role=AgentRole.SOFTWARE_ARCHITECT,
            execute=True,
            action_type="read_repository",
        )

        assert dispatch["status"] == "COMPLETED"
        assert len(dispatch["attempts_log"]) == 3
        assert dispatch["attempts_log"][0]["valid"] is False
        assert dispatch["attempts_log"][1]["valid"] is False
        assert dispatch["attempts_log"][2]["valid"] is True

