"""
AI Team Roles & Multi-Agent Collaboration Coordinator (§16, §17, §19).
Manages multi-agent task dispatching, structured coordination event logs,
role handoffs, and task-to-model routing.
"""

from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Dict, List, Optional
import uuid

from defintra.context.compiler import AgentRole, ContextCompiler
from defintra.core.db.database import Database
from defintra.core.models.entities import current_utc_time


class StructuredEventType(str, Enum):
    REQUIREMENT_ADDED = "REQUIREMENT_ADDED"
    REQUIREMENT_CHANGED = "REQUIREMENT_CHANGED"
    CONTRACT_UPDATE = "CONTRACT_UPDATE"
    CHANGE_REQUEST = "CHANGE_REQUEST"
    SECURITY_FINDING = "SECURITY_FINDING"
    TEST_RESULT = "TEST_RESULT"
    CONFLICT = "CONFLICT"
    DECISION_REQUEST = "DECISION_REQUEST"
    TASK_COMPLETED = "TASK_COMPLETED"
    DEPENDENCY_UPDATE = "DEPENDENCY_UPDATE"


class TeamEvent:
    def __init__(
        self,
        event_id: str,
        project_id: str,
        event_type: StructuredEventType,
        actor_role: AgentRole,
        summary: str,
        payload: Dict[str, Any],
        created_at: str,
    ):
        self.event_id = event_id
        self.project_id = project_id
        self.event_type = event_type
        self.actor_role = actor_role
        self.summary = summary
        self.payload = payload
        self.created_at = created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "project_id": self.project_id,
            "event_type": self.event_type.value,
            "actor_role": self.actor_role.value,
            "summary": self.summary,
            "payload": self.payload,
            "created_at": self.created_at,
        }


class ModelRoutingRecommendation:
    def __init__(
        self,
        recommended_model: str,
        reason: str,
        context_window_tier: str,
        estimated_cost_tier: str,
    ):
        self.recommended_model = recommended_model
        self.reason = reason
        self.context_window_tier = context_window_tier
        self.estimated_cost_tier = estimated_cost_tier

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommended_model": self.recommended_model,
            "reason": self.reason,
            "context_window_tier": self.context_window_tier,
            "estimated_cost_tier": self.estimated_cost_tier,
        }


class TeamCoordinator:
    def __init__(self, db: Database):
        self.db = db
        self.compiler = ContextCompiler(db)

    def route_model(self, role: AgentRole, task_complexity: str = "MEDIUM") -> ModelRoutingRecommendation:
        """
        AI Model Routing Engine (§19).
        Routes tasks to appropriate AI models based on capabilities, cost, and context size.
        """
        if role in [AgentRole.SOFTWARE_ARCHITECT, AgentRole.BACKEND_ENGINEER]:
            return ModelRoutingRecommendation(
                recommended_model="Claude 3.5 Sonnet / Claude Code",
                reason="High technical reasoning and complex multi-file architectural consistency",
                context_window_tier="200k tokens",
                estimated_cost_tier="Standard High Performance",
            )
        elif role in [AgentRole.PRODUCT_ANALYST, AgentRole.QA_ENGINEER]:
            return ModelRoutingRecommendation(
                recommended_model="Gemini 1.5 Pro",
                reason="Massive context window for comprehensive requirement analysis and test suite generation",
                context_window_tier="1M+ tokens",
                estimated_cost_tier="Cost Efficient",
            )
        elif role == AgentRole.SECURITY_ENGINEER:
            return ModelRoutingRecommendation(
                recommended_model="GPT-4o / Claude 3.5 Sonnet",
                reason="Deterministic vulnerability analysis and strict constraint verification",
                context_window_tier="128k tokens",
                estimated_cost_tier="Standard High Performance",
            )
        else:
            return ModelRoutingRecommendation(
                recommended_model="Claude 3.5 Sonnet / Local Fast Model",
                reason="General coding and component authoring",
                context_window_tier="128k tokens",
                estimated_cost_tier="Standard",
            )

    def dispatch_task(
        self,
        project_id: str,
        task_title: str,
        role: AgentRole,
        task_complexity: str = "MEDIUM",
    ) -> Dict[str, Any]:
        """
        Dispatches task to specialized AI role with compiled minimum sufficient context (§16, §17).
        """
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        # 1. Compile context for this specific role
        compiled = self.compiler.compile(
            task_description=task_title,
            project_id=project_id,
            role=role,
        )

        # 2. Get Model Routing recommendation
        routing = self.route_model(role, task_complexity)

        # 3. Record event in SQLite audit_events
        event = self.record_event(
            project_id=project_id,
            event_type=StructuredEventType.CHANGE_REQUEST,
            actor_role=role,
            summary=f"Dispatched task '{task_title}' to role {role.value}",
            payload={"task": task_title, "role": role.value, "routing": routing.to_dict()},
        )

        return {
            "dispatch_id": f"disp_{uuid.uuid4().hex[:8]}",
            "project_id": project_id,
            "task": task_title,
            "assigned_role": role.value,
            "routing": routing.to_dict(),
            "compiled_context_summary": {
                "requirements_count": len(compiled.requirements),
                "decisions_count": len(compiled.decisions),
                "token_count": compiled.token_count,
            },
            "initial_event": event.to_dict(),
        }

    def record_event(
        self,
        project_id: str,
        event_type: StructuredEventType,
        actor_role: AgentRole,
        summary: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> TeamEvent:
        """
        Records an immutable structured coordination event (§17, §34).
        """
        event_id = f"evt_{uuid.uuid4().hex[:8]}"
        created_at = current_utc_time()
        p = payload or {}

        # Save to database audit_events table
        with self.db._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (id, project_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    project_id,
                    event_type.value,
                    json.dumps({"actor_role": actor_role.value, "summary": summary, "data": p}),
                    created_at,
                ),
            )

        return TeamEvent(
            event_id=event_id,
            project_id=project_id,
            event_type=event_type,
            actor_role=actor_role,
            summary=summary,
            payload=p,
            created_at=created_at,
        )

    def get_events(self, project_id: str) -> List[Dict[str, Any]]:
        with self.db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, project_id, event_type, payload_json, created_at FROM audit_events WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            )
            rows = cursor.fetchall()

        events = []
        for r in rows:
            p_data = json.loads(r["payload_json"])
            events.append({
                "id": r["id"],
                "project_id": r["project_id"],
                "event_type": r["event_type"],
                "actor_role": p_data.get("actor_role", "GENERAL"),
                "summary": p_data.get("summary", ""),
                "data": p_data.get("data", {}),
                "created_at": r["created_at"],
            })
        return events
