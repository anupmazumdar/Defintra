"""
EARS (Easy Approach to Requirements Syntax) Engine (§7).
Provides parsing, classification, validation, formatting, and decomposition for EARS requirements.
"""

import re
from typing import List, Optional, Tuple

from defintra.core.models.entities import (
    ArtifactState,
    EARSPattern,
    Provenance,
    Requirement,
    RequirementPriority,
)


class EARSRequirement:
    """
    Structured representation of an EARS requirement statement.
    """

    def __init__(
        self,
        system_name: str,
        system_response: str,
        pattern: EARSPattern = EARSPattern.UBIQUITOUS,
        trigger: Optional[str] = None,
        state: Optional[str] = None,
        feature: Optional[str] = None,
        fault: Optional[str] = None,
    ):
        self.system_name = system_name.strip()
        self.system_response = system_response.strip()
        self.pattern = pattern
        self.trigger = trigger.strip() if trigger else None
        self.state = state.strip() if state else None
        self.feature = feature.strip() if feature else None
        self.fault = fault.strip() if fault else None

    def render(self) -> str:
        """
        Renders the requirement to canonical EARS English syntax.
        """
        sys = f"the {self.system_name}" if not self.system_name.lower().startswith("the ") else self.system_name

        if self.pattern == EARSPattern.UBIQUITOUS:
            return f"{sys} shall {self.system_response}."

        elif self.pattern == EARSPattern.EVENT_DRIVEN:
            return f"WHEN {self.trigger}, {sys} shall {self.system_response}."

        elif self.pattern == EARSPattern.STATE_DRIVEN:
            return f"WHILE {self.state}, {sys} shall {self.system_response}."

        elif self.pattern == EARSPattern.OPTIONAL_FEATURE:
            return f"WHERE {self.feature}, {sys} shall {self.system_response}."

        elif self.pattern == EARSPattern.UNWANTED_BEHAVIOR:
            return f"IF {self.fault}, THEN {sys} shall {self.system_response}."

        elif self.pattern == EARSPattern.COMPLEX:
            clauses = []
            if self.feature:
                clauses.append(f"WHERE {self.feature}")
            if self.state:
                clauses.append(f"WHILE {self.state}")
            if self.trigger:
                clauses.append(f"WHEN {self.trigger}")
            prefix = ", ".join(clauses)
            return f"{prefix}, {sys} shall {self.system_response}."

        return f"{sys} shall {self.system_response}."


class EARSEngine:
    """
    Parser, classifier, and validator for EARS syntax.
    """

    @classmethod
    def classify_and_parse(cls, text: str, default_system: str = "System") -> EARSRequirement:
        text = text.strip()
        if text.endswith("."):
            text = text[:-1]

        # Pattern: IF <fault>, THEN the <sys> shall <resp>
        m_unwanted = re.match(
            r"^IF\s+(.+?),\s*THEN\s+(?:the\s+)?(.+?)\s+shall\s+(.+)$", text, re.IGNORECASE
        )
        if m_unwanted:
            fault, sys_name, resp = m_unwanted.groups()
            return EARSRequirement(
                system_name=sys_name,
                system_response=resp,
                pattern=EARSPattern.UNWANTED_BEHAVIOR,
                fault=fault,
            )

        # Pattern: WHEN <trigger>, the <sys> shall <resp>
        m_event = re.match(
            r"^WHEN\s+(.+?),\s*(?:the\s+)?(.+?)\s+shall\s+(.+)$", text, re.IGNORECASE
        )
        if m_event:
            trigger, sys_name, resp = m_event.groups()
            return EARSRequirement(
                system_name=sys_name,
                system_response=resp,
                pattern=EARSPattern.EVENT_DRIVEN,
                trigger=trigger,
            )

        # Pattern: WHILE <state>, the <sys> shall <resp>
        m_state = re.match(
            r"^WHILE\s+(.+?),\s*(?:the\s+)?(.+?)\s+shall\s+(.+)$", text, re.IGNORECASE
        )
        if m_state:
            state, sys_name, resp = m_state.groups()
            return EARSRequirement(
                system_name=sys_name,
                system_response=resp,
                pattern=EARSPattern.STATE_DRIVEN,
                state=state,
            )

        # Pattern: WHERE <feature>, the <sys> shall <resp>
        m_opt = re.match(
            r"^WHERE\s+(.+?),\s*(?:the\s+)?(.+?)\s+shall\s+(.+)$", text, re.IGNORECASE
        )
        if m_opt:
            feature, sys_name, resp = m_opt.groups()
            return EARSRequirement(
                system_name=sys_name,
                system_response=resp,
                pattern=EARSPattern.OPTIONAL_FEATURE,
                feature=feature,
            )

        # Pattern: Ubiquitous: (the) <sys> shall <resp>
        m_ubi = re.match(r"^(?:The\s+)?(.+?)\s+shall\s+(.+)$", text, re.IGNORECASE)
        if m_ubi:
            sys_name, resp = m_ubi.groups()
            return EARSRequirement(
                system_name=sys_name,
                system_response=resp,
                pattern=EARSPattern.UBIQUITOUS,
            )

        # Fallback to Ubiquitous with default system name
        return EARSRequirement(
            system_name=default_system,
            system_response=text,
            pattern=EARSPattern.UBIQUITOUS,
        )

    @classmethod
    def validate_ears(cls, text: str) -> Tuple[bool, List[str]]:
        """
        Validates whether the statement complies with EARS best practices.
        """
        issues = []
        clean = text.strip()

        if "shall" not in clean.lower():
            issues.append("Requirement must contain mandatory modal keyword 'shall'.")

        if clean.lower().startswith("should") or "should" in clean.lower().split():
            issues.append("Avoid ambiguous keyword 'should'; use 'shall' for verifiable requirements.")

        if clean.lower().startswith("can") or "could" in clean.lower().split():
            issues.append("Avoid capability words ('can', 'could'); use 'shall' for deterministic behavior.")

        if not any(clean.lower().startswith(kw) for kw in ["the ", "when ", "while ", "where ", "if "]):
            issues.append("Statement should begin with standard EARS prefix (The, WHEN, WHILE, WHERE, IF).")

        return (len(issues) == 0, issues)

    @classmethod
    def create_requirement(
        cls,
        req_id: str,
        project_id: str,
        title: str,
        system_name: str,
        response: str,
        pattern: EARSPattern = EARSPattern.UBIQUITOUS,
        trigger: Optional[str] = None,
        state: Optional[str] = None,
        feature: Optional[str] = None,
        fault: Optional[str] = None,
        priority: RequirementPriority = RequirementPriority.MEDIUM,
        category: str = "FUNCTIONAL",
        affected_components: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        acceptance_criteria: Optional[List[str]] = None,
        confidence: float = 0.9,
    ) -> Requirement:
        ears_obj = EARSRequirement(
            system_name=system_name,
            system_response=response,
            pattern=pattern,
            trigger=trigger,
            state=state,
            feature=feature,
            fault=fault,
        )
        rendered_desc = ears_obj.render()

        return Requirement(
            id=req_id,
            project_id=project_id,
            title=title,
            description=rendered_desc,
            ears_pattern=pattern,
            priority=priority,
            status=ArtifactState.PROPOSED,
            category=category,
            affected_components=affected_components or [],
            constraints=constraints or [],
            acceptance_criteria=acceptance_criteria or [f"Verify that {rendered_desc}"],
            provenance=Provenance(
                source="EARS Requirement Generator",
                confidence=confidence,
            ),
        )
