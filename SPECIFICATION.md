# Defintra Specification
> **Define. Validate. Compile. Build.**

Defintra is a project intelligence and control layer for AI software engineering. It maintains a traceable model of requirements, decisions, dependencies, contracts, code, tests, and changes, then compiles the minimum sufficient context an AI agent needs to build, change, test, and deploy safely.

Defintra is not a prompt generator. Its purpose is to make AI systems understand what needs to be built, why, what constraints apply, what decisions have been approved, what context is relevant, and how work should be validated.

> **Revision note:** this replaces an earlier "requirement engineering and context compilation platform" framing. The project-knowledge-graph is the product; requirement intelligence, context compilation, and controlled execution are subsystems that plug into it (see §45).

---

## 1. Core Problem
People often know what they want but not how to express complete technical requirements to an AI.
AI coding systems then:
- make assumptions
- miss requirements
- repeat context
- waste tokens
- make incompatible architectural decisions
- modify unrelated parts of a project
- introduce security or integration problems
- lose the reasoning behind earlier decisions

Defintra creates a controlled layer between human intent and AI execution.

---

## 2. Core Principle
> **Understand first. Decompose deeply. Validate continuously. Change minimally. Compile only approved context.**

Optimize for minimum sufficient context, not simply minimum tokens.
Goals:
- complete requirement coverage
- preservation of critical context and approved decisions
- minimal semantic loss
- fewer conflicts and unnecessary changes
- lower token/cost usage
- better execution quality

Zero hallucinations cannot be guaranteed. Defintra reduces hallucination and misleading-information risk through validation, evidence, explicit unknowns, controlled changes, and testing.

---

## 3. Complete Lifecycle
```
Human Idea → Intent Understanding → Requirement Discovery →
Dynamic Questioning/Forms → Recursive Decomposition →
Requirement & Dependency Graph → Validation/Conflict Detection →
Architecture & Technology Decisions → Security/Policy/Budget/Scope Review →
Canonical Project Specification → Human Final Review → User Approval →
Context Compilation → Token Optimization → Model-Specific Execution →
Sandbox/Staging → Testing/Security/Review → Human Approval → Deployment →
Monitoring → Maintenance/Controlled Improvement
```

---

## 4. Requirement Intelligence
Defintra begins with natural language (e.g. "I want to build an attendance system for colleges") and does not immediately generate code or a final prompt. It first determines what is known, unknown, ambiguous, conflicting, or high-risk.

It can discover: project purpose, target users, organizational context (school/college/startup/research/personal), platform (web/mobile/desktop), language/localization, accessibility, user roles, registration/onboarding, authentication, pages/navigation, features/workflows, UI/UX, frontend, backend, database, APIs, integrations, automation, AI assistants, security, privacy, applicable policies/standards, budget, timeline, scalability, performance, deployment, monitoring, maintenance, testing, edge cases, constraints, and acceptance criteria.

Questions are conditional — Defintra must not force every project through the same questionnaire.

---

## 5. Dynamic Questioning
```
Question → Answer → Update Project State → Find Important Unknown → Next Question
```
- Prefer high-impact questions first (e.g. "Is this a college project, internal system, startup MVP, or production product?" — the answer reshapes everything that follows).
- Structured forms may be generated when many details are needed, but the system should avoid overwhelming the user with unnecessary questions.
- **Live Spec Health UI**: while questioning is happening, show the user a running "spec health" meter (tied to §18's entropy score) and a "what we still don't know" panel listing open Unknowns.
- **Fast Path / Deep Path**:
  - *Deep path*: full recursive questioning flow.
  - *Fast path*: user pastes a rough prompt or existing PRD; Defintra extracts what it can, tags everything else as Unknown, and asks only the highest-impact gaps before producing a spec.
- **Domain Templates (optional, overridable)**: a light library of pre-seeded questioning flows for common domains (SaaS, internal tool, student project, e-commerce) to accelerate the first 30–40% of discovery.

---

## 6. Recursive Decomposition
Requirements are broken down until meaningful detail is covered, e.g.:
```
Authentication
├── Signup (fields, validation, verification, duplicate handling, errors)
├── Login (credentials, rate limiting, sessions, failure states, recovery)
└── Password Reset (request, verification, expiration, completion)
```
Rule: Decompose → solve → validate → merge. If a problem appears in one branch, only that branch is decomposed further; validated branches stay protected.

---

## 7. Requirement Graph
Structured requirements replace one giant text prompt. A requirement holds:
`ID, Type, Description, Priority, Status, Source, Dependencies, Affected Components, Constraints, Acceptance Criteria, Related Decisions, Validation`.

- **EARS Notation**: express requirements using EARS (Easy Approach to Requirements Syntax) — a small set of constrained-English templates (Ubiquitous, Event-driven, State-driven, Optional feature, Unwanted behavior).
- **Visual Rendering**: Plain text tree or Mermaid/ASCII diagram to render dependency and impact relationships visually.

---

## 8. Canonical Project State
One authoritative representation, not a conversation transcript:
```
Project State
├── Objective, Users, Requirements, Constraints, Decisions
├── Assumptions, Unknowns, Architecture, Contracts, Components
├── Tasks, Dependencies, Test Results, Security Findings
├── Suggestions, Changes, History
```

---

## 9. Facts, Decisions, Assumptions, Unknowns, Suggestions
Never silently mixed:
- `FACT`: explicitly provided or verified information.
- `DECISION`: an approved project choice.
- `ASSUMPTION`: an unverified interpretation used temporarily.
- `UNKNOWN`: information not yet established.
- `SUGGESTION`: an AI-generated improvement or alternative.

### Evidence Layer
A Fact and the evidence behind it are distinct:
```
FACT: PostgreSQL is required.
EVIDENCE: Architecture decision document AD-17, approved by: Human
CONFIDENCE: 0.99
```
Every Fact, Decision, and Assumption attaches an `EVIDENCE` record.

### Confidence Scoring + Provenance
Every node carries: `source, source_type, author, timestamp, confidence, evidence, derived_from, approved_by, last_validated`.
Low confidence propagates downstream.

### Confidence Decay / Staleness Detection
Track `last_validated` against downstream change activity. Proactively surface stale high-confidence items when dependencies change.

---

## 10. Decision Ledger
```
D-001 | Decision: PostgreSQL | Reason: Strong transactional consistency
Alternatives: MongoDB, MySQL | Approved: User | Status: LOCKED
```
- **Preserved Disagreement**: permanently record rejected alternatives, trade-offs, and losing rationale in the ledger.

---

## 11. Architecture & Technology Selection
Compares alternatives on requirements, constraints, cost, scale, security, maintainability, and complexity, explaining why. Technology selection must not become arbitrary model preference.

---

## 12. Contracts
Shared contracts prevent agents from inventing incompatible interfaces:
- **API Contract**: request/response shapes, headers, status codes.
- **Database Contract**: tables, relationships, fields, constraints, migrations.
- **UI Contract**: relevant UI behavior, states, API interactions.
- **Security Contract**: approved authentication, authorization, validation, secrets, and security requirements.
Contracts are versioned and dependency-aware.

---

## 13. Task & Dependency Graph
Dependencies are explicit: `Database Schema → Backend API → Frontend Integration → Integration Testing`.

---

## 14. Minimal Change Principle
> **Never change a validated component merely because another solution exists.**
```
Proposed Change → Impact Analysis → Affected Components →
  Can it be isolated? → Yes: change only that area → No: escalate/approval
```
Supports cheap, isolated delta changes without re-triggering the whole pipeline.

---

## 15. Component Stability & Governance
Separates artifact state from governance requirements:
1. **Artifact State**: `PROPOSED`, `VALIDATED`, `APPROVED`, `IMPLEMENTED`, `VERIFIED`, `DEPRECATED`, `CONFLICTED`, `SUPERSEDED`.
2. **Governance**: `approval_required` (none / user / admin / two-person), `approval_level`, `change_risk` (low / medium / high / critical), `blast_radius`.
LOCKED means "cannot be changed silently," not "cannot be changed."

---

## 16. AI Team Roles
Product Analyst, Requirements Engineer, Software Architect, Frontend/Backend/Database/Security/QA/Performance/DevOps Engineer, Code Reviewer, Integration Engineer.

---

## 17. AI Collaboration
- Agents receive: Global Context + Role Context + Task Context + Dependencies + Relevant Contracts + Locked Decisions + Recent Changes.
- Structured Events: `REQUIREMENT_ADDED`, `REQUIREMENT_CHANGED`, `CONTRACT_UPDATE`, `CHANGE_REQUEST`, `SECURITY_FINDING`, `TEST_RESULT`, `CONFLICT`, `DECISION_REQUEST`, `TASK_COMPLETED`, `DEPENDENCY_UPDATE`.
- State over prose: Agents consume the canonical project state directly.
- **Discovery Audit Log**: Logs silent assumptions made without asking the user.

---

## 18. Conflict Resolution & Spec Health Score
- Evaluate solutions against requirements, security, performance, cost, maintainability, compatibility, evidence, and constraints.
- **Spec Health / Entropy Score**: A continuously-updated metric tracking unresolved ambiguity, open unknowns, and active conflicts.

---

## 19. AI Model Routing
Considers task requirements, model capabilities, tool compatibility, context requirements, historical performance, cost, latency, reliability, and security needs.

---

## 20. Adaptive Execution
Assign model as a hypothesis, observe validation results, perform targeted retry, or switch models upon failure with evidence.

---

## 21. Context Compiler
Compiles the minimum sufficient context: Global Project Context + Relevant Requirements + Relevant Contracts + Locked Decisions + Dependencies + Relevant Files + Recent Changes + Current Task.
- **Explainable Inclusion/Exclusion**: Justifies every included and excluded node.
- **Reverse Traceability**: Tracks origin requirements and decisions for every generated artifact.

---

## 22. Defintra Intermediate Representation (DIR)
Canonical versioned JSON representation of intent, requirements, constraints, decisions, architecture, contracts, dependencies, tasks, acceptance criteria, security, testing, and deployment.
- **Dual-Track Output**: Produces both structured machine-actionable DIR and a human-readable narrative Project Brief.

---

## 23. Token Optimization
Removes redundant context, deduplicates requirements, safely compresses semantics, and formats model-specifically without losing critical correctness.

---

## 24. AI Execution Integrations
Model-agnostic adapters (OpenAI, Claude Code, Gemini, Antigravity, local models). Single-action compilation for execution targets.

---

## 25. Isolated Staging Worktree & Subprocess Sandbox
Isolates autonomous execution with dedicated Git branches and worktrees (`sandbox.worktree_path`), path traversal confinement, scrubbed environment variables (stripping host API keys and tokens), policy-gated action checks, and hard execution timeouts.

---

## 26. Self-Testing & Independent Validation
Combines agent self-tests, automated test suites, independent reviewer models, and human review for high-risk items.

---

## 27. Human Testing Packs
Generates structured manual testing checklists and verification steps.

---

## 28. Security & Vulnerability Lifecycle
Converts every discovered vulnerability into a persistent regression test.

---

## 29. Deployment Governance
Pre-production gates: snapshot, rollback plan, health checks, test suite, security sign-off, approval logs.

---

## 30. Monitoring & Production Feedback Loop
Tracks operational metrics and maps production incidents back to the originating requirement or assumption in the knowledge graph.

---

## 31. Maintenance & Operations Runbooks
Maintains runbooks for lifecycle operations, backups, failover, recovery, and updates.

---

## 32. Post-Deployment Improvement
Targeted post-deployment suggestions with expected benefit, risk, cost, and blast radius.

---

## 33. Architecture Stability Budget
Tracks architectural churn and alerts on high-churn modifications.

---

## 34. Audit & History Log
Traceable immutable ledger of all project events.

---

## 35–37. System Architecture, Data Model, and Repository Structure
Modular monolith architecture with clean subsystem layering:
- `defintra/core/`: Requirements, decisions, graph, contracts, conflicts, entropy, impact.
- `defintra/schemas/`: DIR JSON schema definitions.
- `defintra/context/`: Context compiler and token optimizer.
- `defintra/cli/`: CLI entrypoints.
- `defintra/mcp/`: MCP server.

---

## 38–46. Roadmap & Phased Execution
- **V0 (Proof)**: CLI only. Input idea → DIR JSON, EARS requirements, decisions, assumptions, unknowns, conflicts, spec.md.
- **V1 (Requirement Intelligence)**: Adaptive questioning, EARS engine, confidence/provenance, evidence, discovery audit log, spec health score, decision ledger v2.
- **V1.5 (Brownfield Ingestion)**: Repository component/API graph extraction.
- **V2 (Context Compiler)**: Explainable inclusion/exclusion, token optimizer.
- **V3 (Change Engine)**: Blast radius calculation, delta changes.
- **V4 (Coding Integration)**: Execution adapters.
- **V5 (Validation & Security)**: Policy engine, sandboxing.
- **V6 (AI Team Collaboration)**: Coordinated role execution.
- **V7 (Production Control)**: Incident-to-requirement feedback loop.

---

## 47. Non-Goals
- Not a generic project management tool.
- Does not replace human engineering judgment.
- Does not guarantee zero hallucinations (mitigates via evidence & validation).
- Not a chat room or unstructured bot.

---

## 48. Failure Modes & Recovery Patterns
Explicit recovery paths for contradictions, deadlocks, superseded decisions, compiler exclusions, entropy spikes, and rollback requirements.

---

## 49. Spec Evolution & Versioning
Semantic versioning at the contract level, deprecation tracking, and machine-actionable diffs.

---

## 50. Open-Source & GTM
Open-source core data layer, EARS engine, and context compiler.
