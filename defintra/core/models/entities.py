"""
Defintra Core Domain Models.
Defines all typed entities for the persistent project knowledge graph,
provenance tracking, EARS requirements, decisions, governance states, and DIR.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    PROJECT = "PROJECT"
    REQUIREMENT = "REQUIREMENT"
    DECISION = "DECISION"
    ASSUMPTION = "ASSUMPTION"
    UNKNOWN = "UNKNOWN"
    EVIDENCE = "EVIDENCE"
    COMPONENT = "COMPONENT"
    CONTRACT = "CONTRACT"
    CONFLICT = "CONFLICT"
    AUDIT_ENTRY = "AUDIT_ENTRY"
    DEPENDENCY = "DEPENDENCY"
    TASK = "TASK"


class EARSPattern(str, Enum):
    UBIQUITOUS = "UBIQUITOUS"              # The <system> shall <response>
    EVENT_DRIVEN = "EVENT_DRIVEN"          # WHEN <trigger>, the <system> shall <response>
    STATE_DRIVEN = "STATE_DRIVEN"          # WHILE <state>, the <system> shall <response>
    OPTIONAL_FEATURE = "OPTIONAL_FEATURE"  # WHERE <feature>, the <system> shall <response>
    UNWANTED_BEHAVIOR = "UNWANTED_BEHAVIOR"# IF <fault>, THEN the <system> shall <response>
    COMPLEX = "COMPLEX"                    # Combined triggers/states


class RequirementPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ArtifactState(str, Enum):
    """
    v2 Artifact State Lifecycle (§15)
    """
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    IMPLEMENTED = "IMPLEMENTED"
    VERIFIED = "VERIFIED"
    DEPRECATED = "DEPRECATED"
    CONFLICTED = "CONFLICTED"
    SUPERSEDED = "SUPERSEDED"


class ApprovalLevel(str, Enum):
    NONE = "NONE"
    USER = "USER"
    ADMIN = "ADMIN"
    TWO_PERSON = "TWO_PERSON"


class ChangeRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SourceType(str, Enum):
    DOMAIN_EXPERT = "DOMAIN_EXPERT"
    USER_EXPLICIT = "USER_EXPLICIT"
    USER_CONFIRMED = "USER_CONFIRMED"
    AI_INFERRED = "AI_INFERRED"
    AI_GUESSED = "AI_GUESSED"


class DependencyKind(str, Enum):
    REQUIRES = "REQUIRES"
    IMPLEMENTS = "IMPLEMENTS"
    TESTS = "TESTS"
    CONSTRAINS = "CONSTRAINS"
    SUPERSEDES = "SUPERSEDES"
    AFFECTS = "AFFECTS"


def current_utc_time() -> str:
    return datetime.now(timezone.utc).isoformat()


class Evidence(BaseModel):
    id: str
    target_entity_type: EntityType
    target_entity_id: str
    evidence_type: str  # e.g., "USER_STATEMENT", "ADR_DOCUMENT", "AI_INFERENCE", "TEST_RESULT"
    description: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    source: str
    approved_by: Optional[str] = None
    created_at: str = Field(default_factory=current_utc_time)


class Provenance(BaseModel):
    source: str = "Defintra Engine"
    source_type: SourceType = SourceType.AI_INFERRED
    author: str = "Defintra Engine"
    timestamp: str = Field(default_factory=current_utc_time)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    derived_from: List[str] = Field(default_factory=list)
    approved_by: Optional[str] = None
    last_validated: Optional[str] = None


class Requirement(BaseModel):
    id: str
    project_id: str
    title: str
    description: str
    ears_pattern: EARSPattern = EARSPattern.UBIQUITOUS
    priority: RequirementPriority = RequirementPriority.MEDIUM
    status: ArtifactState = ArtifactState.PROPOSED
    category: str = "FUNCTIONAL"
    affected_components: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)
    evidence: List[Evidence] = Field(default_factory=list)
    created_at: str = Field(default_factory=current_utc_time)


class RejectedAlternative(BaseModel):
    alternative: str
    reason_rejected: str
    proposed_by: Optional[str] = None


class Decision(BaseModel):
    id: str
    project_id: str
    title: str
    decision: str
    reason: str
    rejected_alternatives: List[RejectedAlternative] = Field(default_factory=list)
    status: ArtifactState = ArtifactState.PROPOSED
    approval_level: ApprovalLevel = ApprovalLevel.USER
    change_risk: ChangeRisk = ChangeRisk.MEDIUM
    superseded_by: Optional[str] = None
    affected_components: List[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)
    evidence: List[Evidence] = Field(default_factory=list)
    created_at: str = Field(default_factory=current_utc_time)


class Assumption(BaseModel):
    id: str
    project_id: str
    statement: str
    category: str = "GENERAL"
    confidence: float = Field(ge=0.0, le=1.0, default=0.6)
    status: str = "ACTIVE"  # ACTIVE, VALIDATED, REFUTED
    provenance: Provenance = Field(default_factory=Provenance)
    evidence: List[Evidence] = Field(default_factory=list)
    created_at: str = Field(default_factory=current_utc_time)


class Unknown(BaseModel):
    id: str
    project_id: str
    question: str
    impact: str  # HIGH, MEDIUM, LOW
    category: str  # ARCHITECTURE, SECURITY, DATABASE, UI, DEPLOYMENT
    status: str = "OPEN"  # OPEN, RESOLVED, DISMISSED
    resolution: Optional[str] = None
    priority_order: int = 1
    created_at: str = Field(default_factory=current_utc_time)


class Contract(BaseModel):
    id: str
    project_id: str
    name: str
    contract_type: str  # API, DATABASE, UI, SECURITY
    version: str = "1.0.0"
    specification: Dict[str, Any] = Field(default_factory=dict)
    status: ArtifactState = ArtifactState.PROPOSED
    created_at: str = Field(default_factory=current_utc_time)


class Component(BaseModel):
    id: str
    project_id: str
    name: str
    component_type: str  # FRONTEND, BACKEND, DATABASE, AUTH, INFRA
    description: str = ""
    stability_state: ArtifactState = ArtifactState.PROPOSED
    blast_radius: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=current_utc_time)


class Conflict(BaseModel):
    id: str
    project_id: str
    title: str
    description: str
    entity_a_ref: str
    entity_b_ref: str
    severity: str = "HIGH"  # CRITICAL, HIGH, MEDIUM, LOW
    status: str = "OPEN"  # OPEN, RESOLVED, ESCALATED
    resolution: Optional[str] = None
    created_at: str = Field(default_factory=current_utc_time)


class DiscoveryAuditEntry(BaseModel):
    id: str
    project_id: str
    silent_assumption: str
    reason_skipped: str
    risk_level: ChangeRisk = ChangeRisk.LOW
    category: str = "GENERAL"
    created_at: str = Field(default_factory=current_utc_time)


class DependencyEdge(BaseModel):
    id: str
    project_id: str
    source_type: EntityType
    source_id: str
    target_type: EntityType
    target_id: str
    dependency_kind: DependencyKind = DependencyKind.REQUIRES
    description: str = ""
    created_at: str = Field(default_factory=current_utc_time)


class Project(BaseModel):
    id: str
    name: str
    objective: str
    owner_id: Optional[str] = None  # Multiplayer & Multi-author forward-compatible (§45)
    domain: str = "GENERAL"
    source_type: str = "idea"  # "idea" or "repo" (Brownfield ready §45)
    spec_entropy: float = 1.0  # 0.0 (perfect) to 1.0 (pure entropy)
    spec_health_score: float = 0.0  # 0.0% to 100.0%
    created_at: str = Field(default_factory=current_utc_time)
    updated_at: str = Field(default_factory=current_utc_time)


class Approver(BaseModel):
    id: str
    project_id: str
    name: str
    role: str = "USER"  # "USER" or "ADMIN"
    is_admin: bool = False
    created_at: str = Field(default_factory=current_utc_time)
