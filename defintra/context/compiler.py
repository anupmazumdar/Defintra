"""
Context Compiler Engine (§21, §23, §24).
Compiles the minimum sufficient context an AI agent needs for a specific task:
Global Context + Role Guidance + Relevant Requirements + Applicable Contracts +
Locked Decisions + Dependencies + Explainable Inclusions/Exclusions.
"""

from enum import Enum
import json
import re
from typing import Any, Dict, List, Optional

from defintra.context.optimizer import TokenEstimator
from defintra.core.db.database import Database
from defintra.core.models.entities import (
    ArtifactState,
    Component,
    Contract,
    Decision,
    Requirement,
    RequirementPriority,
)


class TargetFormat(str, Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTIGRAVITY = "antigravity"
    MARKDOWN = "markdown"
    JSON = "json"


class AgentRole(str, Enum):
    GENERAL = "GENERAL"
    PRODUCT_ANALYST = "PRODUCT_ANALYST"
    SOFTWARE_ARCHITECT = "SOFTWARE_ARCHITECT"
    BACKEND_ENGINEER = "BACKEND_ENGINEER"
    FRONTEND_ENGINEER = "FRONTEND_ENGINEER"
    DATABASE_ENGINEER = "DATABASE_ENGINEER"
    SECURITY_ENGINEER = "SECURITY_ENGINEER"
    QA_ENGINEER = "QA_ENGINEER"
    DEVOPS_ENGINEER = "DEVOPS_ENGINEER"


ROLE_GUIDANCE: Dict[AgentRole, str] = {
    AgentRole.GENERAL: "Focus on delivering a complete, robust, and clean implementation strictly adhering to the locked architectural decisions and EARS requirements.",
    AgentRole.SOFTWARE_ARCHITECT: "Preserve component boundaries, interface contracts, and existing locked decisions. Minimize cross-boundary coupling.",
    AgentRole.BACKEND_ENGINEER: "Implement server endpoints, validation logic, database queries, and business logic according to API and Database contracts.",
    AgentRole.FRONTEND_ENGINEER: "Implement responsive UI components, user interaction flows, client-side state, and error handling conforming to API contracts.",
    AgentRole.DATABASE_ENGINEER: "Ensure relational integrity, schema migrations, indexing strategies, and ACID transactional consistency as specified in contracts.",
    AgentRole.SECURITY_ENGINEER: "Enforce authentication, authorization, input sanitization, least privilege, and cryptographic standards.",
    AgentRole.QA_ENGINEER: "Design comprehensive test suites, verify all EARS acceptance criteria, and create regression tests for edge cases.",
    AgentRole.DEVOPS_ENGINEER: "Manage infrastructure, containerization, environment variables, CI/CD pipelines, and zero-downtime deployment strategies.",
}


class ExplainableItem:
    def __init__(
        self,
        item_id: str,
        item_type: str,
        title: str,
        is_included: bool,
        reason: str,
        priority_score: float = 0.5,
    ):
        self.item_id = item_id
        self.item_type = item_type
        self.title = title
        self.is_included = is_included
        self.reason = reason
        self.priority_score = priority_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.item_id,
            "type": self.item_type,
            "title": self.title,
            "included": self.is_included,
            "reason": self.reason,
            "priority_score": self.priority_score,
        }


class CompiledContext:
    def __init__(
        self,
        project_id: str,
        project_name: str,
        task_description: str,
        role: AgentRole,
        global_objective: str,
        requirements: List[Requirement],
        decisions: List[Decision],
        contracts: List[Contract],
        components: List[Component],
        explainable_items: List[ExplainableItem],
        token_count: int,
        compression_ratio: float,
    ):
        self.project_id = project_id
        self.project_name = project_name
        self.task_description = task_description
        self.role = role
        self.global_objective = global_objective
        self.requirements = requirements
        self.decisions = decisions
        self.contracts = contracts
        self.components = components
        self.explainable_items = explainable_items
        self.token_count = token_count
        self.compression_ratio = compression_ratio

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "task": self.task_description,
            "role": self.role.value,
            "role_guidance": ROLE_GUIDANCE.get(self.role, ""),
            "global_objective": self.global_objective,
            "requirements": [
                {
                    "id": r.id,
                    "title": r.title,
                    "ears_pattern": r.ears_pattern.value,
                    "statement": r.description,
                    "priority": r.priority.value,
                    "acceptance_criteria": r.acceptance_criteria,
                    "constraints": r.constraints,
                }
                for r in self.requirements
            ],
            "decisions": [
                {
                    "id": d.id,
                    "title": d.title,
                    "decision": d.decision,
                    "reason": d.reason,
                    "status": d.status.value,
                }
                for d in self.decisions
            ],
            "contracts": [
                {
                    "id": ct.id,
                    "name": ct.name,
                    "type": ct.contract_type,
                    "version": ct.version,
                    "specification": ct.specification,
                }
                for ct in self.contracts
            ],
            "components": [
                {"id": c.id, "name": c.name, "type": c.component_type}
                for c in self.components
            ],
            "explainable_inclusions": [
                item.to_dict() for item in self.explainable_items if item.is_included
            ],
            "explainable_exclusions": [
                item.to_dict() for item in self.explainable_items if not item.is_included
            ],
            "token_metrics": {
                "estimated_tokens": self.token_count,
                "compression_ratio": f"{self.compression_ratio:.1f}%",
            },
        }

    def render(self, target_format: TargetFormat = TargetFormat.MARKDOWN) -> str:
        """
        Renders the compiled context in model-specific formats (§24).
        """
        if target_format == TargetFormat.JSON:
            return json.dumps(self.to_dict(), indent=2)

        elif target_format == TargetFormat.CLAUDE:
            # Claude Code XML formatting
            lines = [
                "<defintra_context>",
                f"  <project id=\"{self.project_id}\" name=\"{self.project_name}\">",
                f"    <global_objective>{self.global_objective}</global_objective>",
                f"    <assigned_role>{self.role.value}: {ROLE_GUIDANCE.get(self.role, '')}</assigned_role>",
                f"    <task>{self.task_description}</task>",
                "  </project>",
                "",
                "  <locked_decisions>",
            ]
            for d in self.decisions:
                lines.append(f"    <decision id=\"{d.id}\" title=\"{d.title}\">")
                lines.append(f"      <choice>{d.decision}</choice>")
                lines.append(f"      <reason>{d.reason}</reason>")
                lines.append("    </decision>")
            lines.append("  </locked_decisions>")
            lines.append("")
            lines.append("  <requirements>")
            for r in self.requirements:
                lines.append(f"    <requirement id=\"{r.id}\" priority=\"{r.priority.value}\" pattern=\"{r.ears_pattern.value}\">")
                lines.append(f"      <statement>{r.description}</statement>")
                for ac in r.acceptance_criteria:
                    lines.append(f"      <acceptance_criterion>{ac}</acceptance_criterion>")
                lines.append("    </requirement>")
            lines.append("  </requirements>")
            lines.append("")
            if self.contracts:
                lines.append("  <contracts>")
                for ct in self.contracts:
                    lines.append(f"    <contract id=\"{ct.id}\" type=\"{ct.contract_type}\" version=\"{ct.version}\">")
                    lines.append(f"      <spec>{json.dumps(ct.specification)}</spec>")
                    lines.append("    </contract>")
                lines.append("  </contracts>")
                lines.append("")
            lines.append("</defintra_context>")
            return "\n".join(lines)

        elif target_format == TargetFormat.OPENAI or target_format == TargetFormat.GEMINI or target_format == TargetFormat.ANTIGRAVITY:
            # High-impact markdown instruction set
            lines = [
                f"# Defintra Task Context: {self.task_description}",
                f"> **Project:** {self.project_name} | **Role:** {self.role.value}",
                f"> **Role Guidance:** {ROLE_GUIDANCE.get(self.role, '')}",
                "",
                "## 1. Global Project Objective",
                self.global_objective,
                "",
                "## 2. Mandatory Architectural Decisions (LOCKED)",
            ]
            for d in self.decisions:
                lines.append(f"- **`{d.id}` ({d.title})**: {d.decision} — *{d.reason}*")

            lines.extend(["", "## 3. Relevant Requirements (EARS Syntax)"])
            for r in self.requirements:
                lines.append(f"### `{r.id}`: {r.title} ({r.priority.value})")
                lines.append(f"- **EARS Rule:** `{r.description}`")
                if r.acceptance_criteria:
                    lines.append("- **Acceptance Criteria:**")
                    for ac in r.acceptance_criteria:
                        lines.append(f"  - [ ] {ac}")
                if r.constraints:
                    lines.append(f"- **Constraints:** {', '.join(r.constraints)}")
                lines.append("")

            if self.contracts:
                lines.append("## 4. Interfaces & Contracts")
                for ct in self.contracts:
                    lines.append(f"- **`{ct.id}` ({ct.name})**: {ct.contract_type} v{ct.version}")
                lines.append("")

            lines.extend([
                "## 5. Immediate Execution Goal",
                f"Please implement the assigned task: **{self.task_description}** adhering strictly to all requirements and decisions above.",
            ])
            return "\n".join(lines)

        # Default Markdown format
        lines = [
            f"# Compiled Context — {self.project_name}",
            f"**Task:** {self.task_description}",
            f"**Role:** {self.role.value}",
            "",
            "## Global Objective",
            self.global_objective,
            "",
            "## Included Locked Decisions",
        ]
        for d in self.decisions:
            lines.append(f"- `[{d.id}]` **{d.title}**: {d.decision}")

        lines.extend(["", "## Included Requirements"])
        for r in self.requirements:
            lines.append(f"- `[{r.id}]` ({r.ears_pattern.value}): {r.description}")

        lines.extend(["", "## Explainable Inclusion/Exclusion Audit"])
        for item in self.explainable_items:
            tag = "[INCLUDED]" if item.is_included else "[EXCLUDED]"
            lines.append(f"- {tag} `{item.item_id}` ({item.item_type}): *{item.reason}*")

        return "\n".join(lines)


class ContextCompiler:
    def __init__(self, db: Database):
        self.db = db

    def compile(
        self,
        task_description: str,
        project_id: Optional[str] = None,
        role: AgentRole = AgentRole.GENERAL,
        max_tokens: int = 4000,
    ) -> CompiledContext:
        """
        Compiles the minimum sufficient context for the given task and role.
        """
        project = self.db.get_project(project_id) if project_id else self.db.get_first_project()
        if not project:
            raise ValueError("No active project found in database.")

        reqs = self.db.get_requirements(project.id)
        decs = self.db.get_decisions(project.id)
        contracts = self.db.get_contracts(project.id)
        comps = self.db.get_components(project.id)

        task_words = set(re.findall(r"\w+", task_description.lower()))
        explainable_items: List[ExplainableItem] = []

        # 1. Evaluate Requirements
        candidate_reqs: List[Dict[str, Any]] = []
        for r in reqs:
            r_words = set(re.findall(r"\w+", (r.title + " " + r.description).lower()))
            overlap = task_words.intersection(r_words)

            priority_score = 0.3
            if r.priority == RequirementPriority.CRITICAL:
                priority_score += 0.5
            elif r.priority == RequirementPriority.HIGH:
                priority_score += 0.3

            if overlap:
                priority_score += 0.4

            # Role matching
            if role == AgentRole.BACKEND_ENGINEER and any("backend" in c.lower() or "api" in c.lower() for c in r.affected_components):
                priority_score += 0.3
            elif role == AgentRole.FRONTEND_ENGINEER and any("frontend" in c.lower() or "ui" in c.lower() for c in r.affected_components):
                priority_score += 0.3
            elif role == AgentRole.DATABASE_ENGINEER and any("db" in c.lower() or "database" in c.lower() for c in r.affected_components):
                priority_score += 0.3
            elif role == AgentRole.SECURITY_ENGINEER and "auth" in r.category.lower():
                priority_score += 0.4

            candidate_reqs.append({
                "obj": r,
                "priority_score": priority_score,
                "has_overlap": bool(overlap),
                "is_critical": r.priority == RequirementPriority.CRITICAL,
            })

        # Sort candidate requirements and include relevant
        included_reqs: List[Requirement] = []
        for c in sorted(candidate_reqs, key=lambda x: x["priority_score"], reverse=True):
            r: Requirement = c["obj"]
            if c["is_critical"] or c["has_overlap"] or c["priority_score"] >= 0.6 or len(included_reqs) < 2:
                included_reqs.append(r)
                explainable_items.append(
                    ExplainableItem(
                        item_id=r.id,
                        item_type="REQUIREMENT",
                        title=r.title,
                        is_included=True,
                        reason="Direct task keyword match or critical priority requirement",
                        priority_score=c["priority_score"],
                    )
                )
            else:
                explainable_items.append(
                    ExplainableItem(
                        item_id=r.id,
                        item_type="REQUIREMENT",
                        title=r.title,
                        is_included=False,
                        reason="Lower priority or unrelated to immediate task domain",
                        priority_score=c["priority_score"],
                    )
                )

        # 2. Evaluate Decisions (Include all APPROVED and relevant PROPOSED)
        included_decs: List[Decision] = []
        for d in decs:
            if d.status == ArtifactState.APPROVED or d.status == ArtifactState.PROPOSED:
                included_decs.append(d)
                explainable_items.append(
                    ExplainableItem(
                        item_id=d.id,
                        item_type="DECISION",
                        title=d.title,
                        is_included=True,
                        reason=f"Authoritative architectural choice ({d.status.value})",
                        priority_score=0.9,
                    )
                )
            else:
                explainable_items.append(
                    ExplainableItem(
                        item_id=d.id,
                        item_type="DECISION",
                        title=d.title,
                        is_included=False,
                        reason=f"Inactive or superseded decision state ({d.status.value})",
                        priority_score=0.1,
                    )
                )

        # 3. Evaluate Contracts & Components
        included_contracts: List[Contract] = []
        for ct in contracts:
            included_contracts.append(ct)
            explainable_items.append(
                ExplainableItem(
                    item_id=ct.id,
                    item_type="CONTRACT",
                    title=ct.name,
                    is_included=True,
                    reason="Active interface contract binding the system",
                    priority_score=0.8,
                )
            )

        # 4. Token metrics and compression ratio
        raw_full_content = (
            project.objective
            + " ".join(r.description for r in reqs)
            + " ".join(d.decision for d in decs)
        )
        compiled_content = (
            project.objective
            + " ".join(r.description for r in included_reqs)
            + " ".join(d.decision for d in included_decs)
        )

        full_tokens = max(1, TokenEstimator.estimate_tokens(raw_full_content))
        compiled_tokens = TokenEstimator.estimate_tokens(compiled_content)
        compression_ratio = max(0.0, (1.0 - (compiled_tokens / full_tokens)) * 100.0)

        return CompiledContext(
            project_id=project.id,
            project_name=project.name,
            task_description=task_description,
            role=role,
            global_objective=project.objective,
            requirements=included_reqs,
            decisions=included_decs,
            contracts=included_contracts,
            components=comps,
            explainable_items=explainable_items,
            token_count=compiled_tokens,
            compression_ratio=compression_ratio,
        )
