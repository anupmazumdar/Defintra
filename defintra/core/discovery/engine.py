"""
Requirement Intelligence & Discovery Engine (§4, §5, §6).
Provides intent extraction, Fast Path / Deep Path discovery, domain templates,
EARS requirement decomposition, and adaptive questioning queue.
"""

import re
from typing import Any, Dict

from defintra.core.audit.logger import DiscoveryAuditLogger
from defintra.core.db.database import Database
from defintra.core.decisions.ledger import DecisionLedger
from defintra.core.entropy.calculator import EntropyCalculator, SpecHealthReport
from defintra.core.models.entities import (
    ApprovalLevel,
    ArtifactState,
    ChangeRisk,
    Component,
    DependencyEdge,
    DependencyKind,
    EARSPattern,
    EntityType,
    Project,
    RejectedAlternative,
    RequirementPriority,
    SourceType,
    Unknown,
    current_utc_time,
)
from defintra.core.requirements.ears import EARSEngine
from defintra.core.security.redactor import SecretRedactor

# Pre-seeded Domain Templates (§5)
DOMAIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "COLLEGE_STUDENT": {
        "domain": "COLLEGE_STUDENT",
        "default_components": [
            {"id": "COMP-UI", "name": "Frontend Web & Mobile App", "type": "FRONTEND"},
            {"id": "COMP-API", "name": "REST API Backend", "type": "BACKEND"},
            {"id": "COMP-DB", "name": "Relational Database", "type": "DATABASE"},
            {"id": "COMP-AUTH", "name": "Role-Based Authentication Service", "type": "AUTH"},
        ],
        "default_decisions": [
            {
                "id": "D-001",
                "title": "Database Engine",
                "decision": "SQLite / PostgreSQL",
                "reason": "ACID transactional safety for attendance and grade records",
                "rejected": [{"alternative": "MongoDB", "reason_rejected": "Lack of relational integrity for enrollment"}],
            }
        ],
        "high_impact_questions": [
            "What is the deployment environment? (Local demo, university intranet, or public cloud)?",
            "What authentication method should be used? (Email/password, College SSO/SAML, or Roll Number/PIN)?",
            "Does attendance verification require QR codes, Geofencing, or Manual faculty entry?",
        ],
        "silent_assumptions": [
            ("Multi-tenancy across different universities is not required in MVP", "Standard college project scope is single institution", ChangeRisk.LOW),
            ("English is the primary interface language", "Default for college management software unless specified", ChangeRisk.LOW),
        ],
    },
    "SAAS": {
        "domain": "SAAS",
        "default_components": [
            {"id": "COMP-WEB", "name": "Next.js/React Web Application", "type": "FRONTEND"},
            {"id": "COMP-SVC", "name": "FastAPI/Node API Gateway", "type": "BACKEND"},
            {"id": "COMP-DB", "name": "PostgreSQL Database", "type": "DATABASE"},
            {"id": "COMP-BILLING", "name": "Stripe Billing & Subscription Service", "type": "PAYMENT"},
            {"id": "COMP-AUTH", "name": "OAuth2 & JWT Auth", "type": "AUTH"},
        ],
        "default_decisions": [
            {
                "id": "D-001",
                "title": "Multi-Tenant Architecture",
                "decision": "Row-Level Security (RLS) on PostgreSQL",
                "reason": "Cost-effective isolation with high data safety",
                "rejected": [{"alternative": "Database-per-tenant", "reason_rejected": "Excessive operational overhead for MVP"}],
            }
        ],
        "high_impact_questions": [
            "What is the monetization model? (Freemium, Tiered Subscriptions, Usage-based, or Free Trial)?",
            "What compliance or security standards apply? (SOC2, GDPR, HIPAA, or Standard Web Security)?",
            "What third-party integrations are mandatory for V1?",
        ],
        "silent_assumptions": [
            ("Standard HTTPS encryption in transit and AES-256 at rest are sufficient", "Industry standard baseline", ChangeRisk.LOW),
            ("User self-service password reset is mandatory", "Standard SaaS requirement", ChangeRisk.LOW),
        ],
    },
    "INTERNAL_TOOL": {
        "domain": "INTERNAL_TOOL",
        "default_components": [
            {"id": "COMP-ADMIN-UI", "name": "Admin Dashboard", "type": "FRONTEND"},
            {"id": "COMP-BACKEND", "name": "Internal Service Backend", "type": "BACKEND"},
            {"id": "COMP-DB", "name": "Internal DB / Data Warehouse", "type": "DATABASE"},
        ],
        "default_decisions": [
            {
                "id": "D-001",
                "title": "Authentication",
                "decision": "Corporate SSO / Google Workspace",
                "reason": "Seamless integration with internal employee identity",
                "rejected": [{"alternative": "Custom username/password", "reason_rejected": "Violates corporate credential policy"}],
            }
        ],
        "high_impact_questions": [
            "Which internal database or data source does this tool interface with?",
            "What are the distinct employee role tiers (e.g. Viewer, Operator, Admin)?",
            "Is real-time sync or batch data processing required?",
        ],
        "silent_assumptions": [
            ("Public internet indexing (SEO) must be disabled", "Internal tools must remain private", ChangeRisk.LOW),
        ],
    },
    "ECOMMERCE": {
        "domain": "ECOMMERCE",
        "default_components": [
            {"id": "COMP-STOREFRONT", "name": "Storefront Web & Mobile Catalog", "type": "FRONTEND"},
            {"id": "COMP-CART-ORDER", "name": "Cart & Order Checkout Service", "type": "BACKEND"},
            {"id": "COMP-INVENTORY", "name": "Real-Time Inventory Manager", "type": "BACKEND"},
            {"id": "COMP-PAYMENTS", "name": "Payment Gateway Integration", "type": "PAYMENT"},
            {"id": "COMP-DB", "name": "Transactional Order & Product DB", "type": "DATABASE"},
        ],
        "default_decisions": [
            {
                "id": "D-001",
                "title": "Inventory Concurrency Control",
                "decision": "Pessimistic Locking / Redis Distributed Lock",
                "reason": "Prevents double-booking and overselling during high-traffic checkout spikes",
                "rejected": [{"alternative": "Optimistic Concurrency", "reason_rejected": "High checkout conflict rates during sales"}],
            }
        ],
        "high_impact_questions": [
            "What payment gateways must be supported? (Stripe, PayPal, Razorpay, Apple Pay)?",
            "Is this a single-vendor store or a multi-vendor marketplace with vendor payouts?",
            "What shipping and tax rate calculation providers are needed?",
        ],
        "silent_assumptions": [
            ("Inventory reservation expires after 15 minutes of inactivity in cart", "E-commerce standard pattern", ChangeRisk.LOW),
            ("PCI-DSS compliance requires zero raw card data storage on local servers", "Mandatory security policy", ChangeRisk.HIGH),
        ],
    },
    "HEALTHCARE": {
        "domain": "HEALTHCARE",
        "default_components": [
            {"id": "COMP-PATIENT-PORTAL", "name": "Patient & Provider Portal", "type": "FRONTEND"},
            {"id": "COMP-EHR-SERVICE", "name": "FHIR / EHR Clinical Records API", "type": "BACKEND"},
            {"id": "COMP-APPOINTMENTS", "name": "Appointment Scheduling & Telehealth Engine", "type": "BACKEND"},
            {"id": "COMP-ENCRYPTED-DB", "name": "Encrypted Patient Database (CMEK)", "type": "DATABASE"},
        ],
        "default_decisions": [
            {
                "id": "D-001",
                "title": "HIPAA & Field-Level Encryption",
                "decision": "AES-256-GCM Envelope Encryption with Audit Logging",
                "reason": "Strict compliance with medical privacy laws (HIPAA/GDPR)",
                "rejected": [{"alternative": "Standard unencrypted relational columns", "reason_rejected": "Severe regulatory non-compliance risk"}],
            }
        ],
        "high_impact_questions": [
            "What regulatory frameworks apply? (HIPAA, HITECH, GDPR Health Data)?",
            "Does the system interface with existing EHR/EMR systems via HL7 or FHIR standards?",
            "Are telehealth video consultations integrated directly or through third-party links?",
        ],
        "silent_assumptions": [
            ("Audit logs of PHI access must be immutable and retained for 7 years", "Mandatory HIPAA requirement", ChangeRisk.HIGH),
        ],
    },
    "FINTECH": {
        "domain": "FINTECH",
        "default_components": [
            {"id": "COMP-APP", "name": "Fintech Mobile & Web App", "type": "FRONTEND"},
            {"id": "COMP-LEDGER", "name": "Double-Entry Accounting Ledger", "type": "BACKEND"},
            {"id": "COMP-FRAUD-SEC", "name": "Fraud Detection & KYC Engine", "type": "SECURITY"},
            {"id": "COMP-LEDGER-DB", "name": "Immutable Ledger Database", "type": "DATABASE"},
        ],
        "default_decisions": [
            {
                "id": "D-001",
                "title": "Financial Ledger Architecture",
                "decision": "Immutable Double-Entry Bookkeeping Ledger",
                "reason": "Guarantees zero mathematical discrepancies in balance calculation",
                "rejected": [{"alternative": "Single-table mutable balance row", "reason_rejected": "Unacceptable risk of phantom balance corruption"}],
            }
        ],
        "high_impact_questions": [
            "What financial regulations and KYC/AML tiers must be enforced?",
            "What fiat/crypto currencies and settlement networks are supported?",
            "What is the maximum allowable transaction verification latency?",
        ],
        "silent_assumptions": [
            ("Idempotency keys must be required on all payment mutation endpoints", "Prevents duplicate charges", ChangeRisk.HIGH),
        ],
    },
}


class DiscoveryEngine:
    def __init__(self, db: Database):
        self.db = db
        self.decision_ledger = DecisionLedger(db)
        self.audit_logger = DiscoveryAuditLogger(db)

    def detect_domain(self, text: str) -> str:
        lower = text.lower()
        if any(w in lower for w in ["college", "school", "university", "student", "attendance", "faculty", "professor"]):
            return "COLLEGE_STUDENT"
        elif any(w in lower for w in ["health", "medical", "patient", "doctor", "clinic", "hospital", "ehr", "hipaa"]):
            return "HEALTHCARE"
        elif any(w in lower for w in ["bank", "fintech", "payment", "ledger", "crypto", "wallet", "kyc", "fraud"]):
            return "FINTECH"
        elif any(w in lower for w in ["shop", "store", "ecommerce", "cart", "checkout", "product", "marketplace"]):
            return "ECOMMERCE"
        elif any(w in lower for w in ["subscription", "saas", "b2b", "billing", "stripe", "customer"]):
            return "SAAS"
        elif any(w in lower for w in ["internal", "admin tool", "operations", "dashboard", "employee"]):
            return "INTERNAL_TOOL"
        return "COLLEGE_STUDENT"

    def run_fast_path(self, project_name: str, raw_input: str) -> Project:
        """
        Fast Path (§5):
        Parses raw prompt/PRD into canonical graph entities, EARS requirements,
        identifies unknowns and assumptions, and logs silent assumptions.
        """
        project_id = re.sub(r"[^a-zA-Z0-9_-]", "_", project_name.lower().strip())
        raw_input = SecretRedactor.sanitize_all(raw_input)
        domain_key = self.detect_domain(raw_input)
        template = DOMAIN_TEMPLATES.get(domain_key, DOMAIN_TEMPLATES["COLLEGE_STUDENT"])

        # 1. Create or Update Project
        project = Project(
            id=project_id,
            name=project_name,
            objective=raw_input.strip(),
            domain=domain_key,
            source_type="idea",
            spec_entropy=0.75,
            spec_health_score=35.0,
            created_at=current_utc_time(),
            updated_at=current_utc_time(),
        )
        self.db.save_project(project)

        # 2. Add Components from Template
        for comp_data in template["default_components"]:
            comp = Component(
                id=f"{comp_data['id']}_{project_id}",
                project_id=project_id,
                name=comp_data["name"],
                component_type=comp_data["type"],
                stability_state=ArtifactState.PROPOSED,
            )
            self.db.save_component(comp)

        # 3. Add Pre-seeded Decisions
        for dec_data in template["default_decisions"]:
            alts = [
                RejectedAlternative(alternative=alt["alternative"], reason_rejected=alt["reason_rejected"])
                for alt in dec_data.get("rejected", [])
            ]
            self.decision_ledger.record_decision(
                project_id=project_id,
                decision_id=f"{dec_data['id']}_{project_id}",
                title=dec_data["title"],
                decision=dec_data["decision"],
                reason=dec_data["reason"],
                rejected_alternatives=alts,
                approval_level=ApprovalLevel.USER,
                change_risk=ChangeRisk.MEDIUM,
                confidence=0.9,
                source="Domain Knowledge Template",
                source_type=SourceType.DOMAIN_EXPERT,
            )

        # 4. Generate Core EARS Requirements based on input
        self._generate_ears_requirements(project_id, raw_input, domain_key)

        # 5. Extract Unknowns from domain and text
        for i, q in enumerate(template["high_impact_questions"]):
            unk = Unknown(
                id=f"UNK-{i+1:03d}_{project_id}",
                project_id=project_id,
                question=q,
                impact="HIGH" if i == 0 else "MEDIUM",
                category="ARCHITECTURE" if "database" in q.lower() or "deployment" in q.lower() else "SECURITY",
                status="OPEN",
                priority_order=i + 1,
            )
            self.db.save_unknown(unk)

        # 6. Log Discovery Audit Entries (Silent Assumptions §17)
        for i, (assumption_stmt, reason, risk) in enumerate(template["silent_assumptions"]):
            self.audit_logger.record_silent_assumption(
                project_id=project_id,
                entry_id=f"AUD-{i+1:03d}_{project_id}",
                silent_assumption=assumption_stmt,
                reason_skipped=reason,
                risk_level=risk,
                category="DOMAIN_DEFAULT",
            )

        # 7. Compute Initial Health & Spec Entropy
        reqs = self.db.get_requirements(project_id)
        decs = self.db.get_decisions(project_id)
        asms = self.db.get_assumptions(project_id)
        unks = self.db.get_unknowns(project_id)
        conflicts = self.db.get_conflicts(project_id)

        health_report = EntropyCalculator.compute(reqs, decs, asms, unks, conflicts)
        project.spec_entropy = health_report.entropy
        project.spec_health_score = health_report.health_score
        self.db.save_project(project)

        return project

    def _generate_ears_requirements(self, project_id: str, raw_input: str, domain: str):
        # 1. Ubiquitous requirement
        req1 = EARSEngine.create_requirement(
            req_id=f"R-101_{project_id}",
            project_id=project_id,
            title="User Authentication",
            system_name="System",
            response="authenticate registered users using secure credentials before granting access to workflows",
            pattern=EARSPattern.UBIQUITOUS,
            priority=RequirementPriority.CRITICAL,
            affected_components=["Frontend Web & Mobile App", "REST API Backend", "Role-Based Authentication Service"],
            constraints=["Passwords must be hashed using bcrypt or Argon2", "Tokens must expire after 24 hours"],
            acceptance_criteria=[
                "Valid credentials successfully generate access tokens",
                "Invalid credentials reject with HTTP 401 Unauthorized",
            ],
            confidence=0.95,
        )
        self.db.save_requirement(req1)

        # 2. Event-driven requirement
        req2 = EARSEngine.create_requirement(
            req_id=f"R-102_{project_id}",
            project_id=project_id,
            title="Core Domain Action Execution",
            system_name="System",
            response="record and store the operational log with UTC timestamp and actor identity",
            pattern=EARSPattern.EVENT_DRIVEN,
            trigger="an authorized user submits a record or action request",
            priority=RequirementPriority.HIGH,
            affected_components=["REST API Backend", "Relational Database"],
            acceptance_criteria=[
                "Submitted actions are committed with immutable audit timestamp",
                "Unauthorized submissions return HTTP 403 Forbidden",
            ],
            confidence=0.9,
        )
        self.db.save_requirement(req2)

        # 3. Unwanted behavior requirement
        req3 = EARSEngine.create_requirement(
            req_id=f"R-103_{project_id}",
            project_id=project_id,
            title="Network Disconnection / Fault Handling",
            system_name="System",
            response="queue pending local transactions and display a non-blocking offline alert",
            pattern=EARSPattern.UNWANTED_BEHAVIOR,
            fault="the network connection is lost during data submission",
            priority=RequirementPriority.MEDIUM,
            affected_components=["Frontend Web & Mobile App"],
            acceptance_criteria=[
                "Network interruption triggers offline queueing",
                "Reconnection synchronizes queued records to the backend",
            ],
            confidence=0.85,
        )
        self.db.save_requirement(req3)

        # Connect dependencies
        dep1 = DependencyEdge(
            id=f"DEP-01_{project_id}",
            project_id=project_id,
            source_type=EntityType.REQUIREMENT,
            source_id=req1.id,
            target_type=EntityType.REQUIREMENT,
            target_id=req2.id,
            dependency_kind=DependencyKind.REQUIRES,
            description="Core action execution requires prior authentication",
        )
        self.db.save_dependency(dep1)

    def answer_unknown(self, project_id: str, unknown_id: str, user_answer: str) -> SpecHealthReport:
        """
        Processes user answer during questioning loop (§5):
        - Marks unknown as RESOLVED
        - Converts answer into an approved Fact / Decision or Assumption
        - Recalculates Spec Health & Entropy
        """
        unknowns = self.db.get_unknowns(project_id)
        target = next((u for u in unknowns if u.id == unknown_id), None)
        if target:
            target.status = "RESOLVED"
            target.resolution = user_answer
            self.db.save_unknown(target)

            # Record as Decision or Assumption
            dec_id = f"D-ANS-{unknown_id}"
            self.decision_ledger.record_decision(
                project_id=project_id,
                decision_id=dec_id,
                title=f"Clarification for: {target.question[:40]}",
                decision=user_answer,
                reason=f"User clarified via Questioning Loop on question '{target.question}'",
                approval_level=ApprovalLevel.USER,
                change_risk=ChangeRisk.LOW,
                confidence=0.99,
                source="User Question Answer",
                source_type=SourceType.USER_CONFIRMED,
            )

        # Recalculate health
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

        return report
