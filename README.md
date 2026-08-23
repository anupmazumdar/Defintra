# Defintra — Project Intelligence & Control Layer

**Define. Validate. Compile. Build.**
*The definitive project intelligence and governance layer for AI-native software engineering.*

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-active-emerald.svg)
![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)
![Tests Passing](https://img.shields.io/badge/tests-58%20passing-brightgreen.svg)

---

## 📖 Overview

Modern AI coding agents fail not because they cannot write code, but because they lack **grounded context, architectural boundaries, and traceable requirements**. When context windows are flooded with irrelevant files, agents hallucinate, contradict earlier decisions, and introduce silent regressions.

**Defintra** is a project intelligence and control layer that bridges the gap between human architectural intent and autonomous AI agents. It maintains a living, persistent knowledge graph of your project (requirements, decisions, assumptions, unknowns, contracts, components, and dependencies), detects conflicts, and compiles the **Minimum Sufficient Context** tailored specifically for each agent role and target model.

```text
       +-----------------------------------------------------------------------+
       |                           HUMAN / TEAM                                |
       |   PRDs / Raw Ideas | Brownfield Repos | Incidents | Architectural Decs|
       +-----------------------------------+-----------------------------------+
                                           |
                                           v
       +-----------------------------------------------------------------------+
       |                     DEFINITRA INTELLIGENCE ENGINE                     |
       |  - EARS Requirement Parser          - Conflict & Contradiction Engine |
       |  - Typed Knowledge Graph (SQLite)   - Adaptive Questioning (Entropy)  |
       |  - Policy & Action Gate Engine      - Incident Feedback Loop          |
       |  - Stability & Churn Budget         - Operations & Runbooks           |
       |  - Test Pack Scaffolder (Pytest/QA) - Post-Deployment Advisor         |
       +-----------------------------------+-----------------------------------+
                                           |
                                           v
       +-----------------------------------------------------------------------+
       |               MINIMUM SUFFICIENT CONTEXT COMPILER                     |
       |  Role Adaptors (Backend / Frontend / Architect / Security / QA)       |
       |  Target Adaptors (Claude XML / OpenAI Markdown / Gemini / Antigravity)|
       |  Graph Pruning, Dependency Tree-Shaking & Token Ceiling Packing       |
       +-----------------------------------+-----------------------------------+
                                           |
                 +-------------------------+-------------------------+
                 |                         |                         |
                 v                         v                         v
       +--------------------+    +--------------------+    +--------------------+
       |   AUTONOMOUS AI    |    |     MCP SERVER     |    |    INTERACTIVE     |
       |   CODING AGENTS    |    |  Cursor / Claude / |    |    WEB CONTROL     |
       |  (Target Prompts)  |    |    Antigravity     |    |   CENTER / UI      |
       +--------------------+    +--------------------+    +--------------------+
```

---

## 🌟 Key Capabilities

1. **EARS-Driven Requirement Engineering** — Automatically transforms raw PRD or feature text into structured, unambiguous requirements adhering to Easy Approach to Requirements Syntax (Ubiquitous, Event-Driven, State-Driven, Unwanted Behavior, and Optional Features).
2. **Entropy & Spec Health Calculation** — Quantifies project ambiguity, unverified assumptions, and open unknowns into a dynamic 0.0–1.0 entropy metric.
3. **Autonomous Agent Policy Engine (§45)** — Enforces fine-grained permission tiers, risk checks (LOW, MEDIUM, HIGH, CRITICAL), and approval requirements (ALLOW, DENY, REQUIRES_APPROVAL) before agents perform actions.
4. **Minimum Sufficient Context Compiler** — Token-budgeted compiler that extracts only the exact sub-graph needed for a specific coding agent task, formatting it natively for Claude (XML-tagged), OpenAI (Markdown), Gemini, or Antigravity.
5. **Multi-Agent Team Orchestration & AI Execution (§16, §17, §19, §24)** — Coordinates tasks across software architects, backend, frontend, security, and QA engineers with intelligent LLM model routing and direct provider execution.
6. **Conflict & Contradiction Detection** — Graph-traversal algorithms that flag mutually exclusive architectural decisions, contradictory requirements, and circular dependencies.
7. **Semantic Spec Diffing** — Track structural specification drift between versions, diffing entities, confidence levels, and acceptance criteria.
8. **Interactive Web Control Center & Dashboard** — Real-time browser-based dashboard with visual interactive knowledge graph, health gauges, conflict resolution, and runbook triggers.
9. **Full MCP Server Support** — Seamless Model Context Protocol integration with 15+ native tools for Cursor, Claude Code, and Antigravity.

---

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/anupmazumdar/Defintra.git
cd Defintra

# Install Defintra in editable mode
pip install -e .
```

### 1. Initialize & Analyze a Project

```bash
# Initialize a new project
defintra init "Autonomous Billing Microservice"

# Decompose raw intent into formal EARS requirements & discover unknowns
defintra analyze "Build a multi-tenant subscription service using Stripe, PostgreSQL, and FastAPI with idempotency." --deep
```

### 2. Compile Context for a Coding Agent

```bash
# Compile minimum sufficient context for an agent implementing webhooks
defintra compile "Implement Stripe subscription renewal webhook with idempotency" \
  --role BACKEND_ENGINEER \
  --target claude \
  --tokens 3500
```

### 3. Launch the Web Control Center

```bash
defintra ui
```

Opens the interactive dashboard at `http://127.0.0.1:8765` featuring:

- **Spec Health Gauge** (0–100% health score with active penalty breakdown)
- **Interactive SVG Graph Visualizer** (Color-coded node topologies with physics layout)
- **Live Decision Ledger** (Accepted vs. rejected alternatives with rationale)
- **Active Questioning Loop** (Resolve unknowns and watch entropy drop in real time)
- **Minimum Sufficient Context Studio** (Preview compiled prompts per agent role and LLM)
- **Operations & Runbooks Studio** (One-click failover, backup, and rollback runbooks)

---

## 💻 Complete CLI Command Reference

### Project Lifecycle & Decomposition

```bash
# Initialize a new project in the current workspace
defintra init "E-Commerce Checkout & Inventory"

# Analyze a raw idea, feature request, or PRD text (use --deep for recursive decomposition)
defintra analyze "Build a multi-vendor marketplace with stripe checkout, order processing, and redis caching." --deep

# Inspect project health, confidence scores, and graph statistics
defintra status
```

### Brownfield Codebase Ingestion

```bash
# Ingest an existing codebase into the knowledge graph
defintra scan ./my-existing-app --name "Legacy API"
```

### Context Compilation (The Core Engine)

```bash
# Compile minimum sufficient context for a specific coding agent task
defintra compile "Implement Stripe webhook handler" \
  --role BACKEND_ENGINEER \
  --target claude \
  --tokens 4000

# Other supported roles:
# FRONTEND_ENGINEER | SOFTWARE_ARCHITECT | SECURITY_ENGINEER | QA_ENGINEER | PRODUCT_ANALYST

# Other supported targets:
# claude (XML tagged) | openai (Markdown) | gemini | antigravity
```

### Multi-Agent Team Dispatch & Model Routing

```bash
# Dispatch tasks across specialized AI team roles with structured handoffs (§16, §17)
defintra team "Design Auth & Tenant Isolation" --role SOFTWARE_ARCHITECT
defintra team "Implement JWT Refresh Rotation" --role BACKEND_ENGINEER

# Inspect the chronological stream of multi-agent structured coordination events (§17, §34)
defintra events

# Query optimal AI model routing recommendations and cost/context tiers (§19)
defintra route BACKEND_ENGINEER --complexity HIGH
```

### Autonomous Agent Policy Engine (§45)

```bash
# Evaluate an action request against the governance policy engine
defintra policy check read_repository
defintra policy check deploy
defintra policy check delete_production_data

# List all configured governance policies and action permissions
defintra policy list
```

### Conflict Detection & Resolution

```bash
# View active architectural and requirement conflicts
defintra conflicts

# Resolve a specific conflict by selecting the winning node
defintra conflicts --resolve CONF-001 --winner D-001 --notes "Selected PostgreSQL for ACID consistency"
```

### Adaptive Questioning & Entropy Reduction

```bash
# Run interactive questioning loop to resolve highest-entropy unknowns
defintra question
```

### Incident Root-Cause Feedback Loop

```bash
# Map a production error or stack trace back to requirements and assumptions
defintra incident "NullPointerException in payment_service.py at line 142 during refund callback"
```

### Operations & Maintenance Runbooks

```bash
# Generate operational runbooks for production resilience
defintra runbook --type backup
defintra runbook --type failover
defintra runbook --type disaster_recovery
defintra runbook --type rollback
```

### Architecture Stability Budget

```bash
# Check modification velocity, churn index, and stability health
defintra stability
```

### Semantic Spec Diffing

```bash
# Compare two versions of DIR specifications
defintra diff ./specs/v1_dir.json ./specs/v2_dir.json
```

### Test Pack & Pytest Generation

```bash
# Generate human QA verification walkthrough checklist
defintra test-pack --type human

# Generate executable Pytest test suite mapped directly to EARS requirements
defintra test-pack --type automated --out tests/test_generated_suite.py
```

### Execution Sandboxing & Governance Gates

```bash
# Create an isolated staging sandbox for a risky agent implementation
defintra sandbox create --task "auth_refactor"

# Evaluate pre-production release readiness & deployment gates
defintra gate
```

### Impact & Blast Radius Simulation

```bash
# Simulate the downstream impact of changing or removing a node
defintra blast-radius "D-001"
```

### Export & Agent Rules

```bash
# Export knowledge graph to JSON DIR schema and human-readable Markdown
defintra export --out .defintra/export

# Directly export targeted agent rules for AI IDEs
defintra export --rules cursor   # Generates .cursorrules
defintra export --rules claude   # Generates CLAUDE.md
defintra export --rules agents   # Generates AGENTS.md
```

### Governance, Architecture & Multi-Agent Scheduling

```bash
# Check confidence decay and stale knowledge graph nodes (§9)
defintra staleness
defintra staleness --revalidate REQ-001

# Generate formal Architecture Decision Records (ADRs) with trade-off matrices (§10, §11)
defintra adr

# Generate multi-phase implementation roadmap & parallel execution tracks (§13, §16)
defintra schedule

# Validate semantic contract versions & breaking changes (§12, §49)
defintra contracts

# Generate post-deployment continuous improvement advisory (§32)
defintra advise

# Diagnose systemic failure modes & execute self-healing remediation (§48)
defintra recover
```

---

## 🔌 Model Context Protocol (MCP) Server

Defintra provides a full-featured Model Context Protocol (MCP) server that connects seamlessly with IDEs and AI tools like **Cursor**, **Claude Code / Claude Desktop**, and **Antigravity**.

### Launching the MCP Server

```bash
# Via defintra CLI
defintra mcp

# Or via Python module
python -m defintra.mcp.server
```

### Available MCP Tools

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `compile_context` | `task_description`, `role`, `target_format`, `max_tokens` | Compiles the optimal minimum sufficient context for an agent task. |
| `get_project_state` | `project_id` | Retrieves current knowledge graph state, entities, and health score. |
| `calculate_blast_radius` | `node_id` | Calculates downstream blast radius, risk level, and required approvals. |
| `propose_decision` | `decision_id`, `title`, `decision`, `reason`, `rejected_alternatives` | Records an architectural decision with preserved disagreement. |
| `detect_conflicts` | `project_id` | Automatically detects contradictory requirements and incompatible decisions. |
| `resolve_conflict` | `conflict_id`, `resolution_notes`, `winning_entity_id` | Resolves a conflict, archiving the losing variant and updating the graph. |
| `generate_test_pack` | `pack_type` (`human`, `automated`, `security`) | Generates structured human testing checklists or pytest scaffolds. |
| `dispatch_team_task` | `task`, `role` | Orchestrates role-specific subagent execution with isolated context. |
| `trace_incident` | `error_text` | Traces runtime stack traces back to root-cause requirements or assumptions. |
| `generate_runbook` | `runbook_type` (`backup`, `deployment`, `failover`, `restore`) | Generates executable step-by-step operations runbooks. |
| `check_stability_budget` | `project_id` | Evaluates architectural churn velocity against stability thresholds. |
| `check_staleness` | `project_id` | Tracks confidence decay and surfaces outdated items when dependents mutate. |
| `get_improvements` | `project_id` | Generates prioritized post-deployment performance and reliability recommendations. |
| `diagnose_recovery` | `project_id` | Diagnoses systemic contradictions, entropy spikes, or churn breaches. |

---

## 🧪 Testing

Defintra includes a comprehensive test suite covering all engines, CLI workflows, APIs, and the UI server:

```bash
# Run all tests with pytest
python -m pytest

# Run tests with coverage report
python -m pytest -v --cov=defintra tests/
```

All **58 unit and integration tests** pass consistently across:

- `test_adr_and_scheduling.py` — Architecture Decision Records (ADR) & task execution scheduling
- `test_brownfield.py` — AST & framework route ingestion
- `test_cli.py` — Complete 33-command CLI suite & governance verification
- `test_compiler.py` — Context compilation and token pruning
- `test_conflicts.py` — Contradiction and incompatible decision engine
- `test_database.py` — SQLite schema, project ownership, and graph persistence
- `test_decisions.py` — Decision ledger & disagreement tracking
- `test_discovery.py` — Fast path and deep LLM decomposition
- `test_discovery_llm_providers.py` — OpenAI & Gemini mock HTTP decomposition
- `test_ears.py` — EARS syntax validation and parsing
- `test_entropy.py` — Spec health and ambiguity scoring
- `test_export_and_schema.py` — DIR JSON export & markdown serialization
- `test_governance_and_recovery.py` — Confidence decay, staleness, post-deployment advisor, and failure recovery
- `test_graph.py` — NetworkX graph algorithms & blast radius
- `test_mcp.py` — Model Context Protocol tools & server handlers
- `test_operations.py` — Incident feedback loop & runbook generation
- `test_policy.py` — Autonomous agent action governance & permission engine
- `test_stability_and_diff.py` — Stability budgets & semantic spec diffs
- `test_team_coordinator.py` — Multi-agent role handoff & AI task execution
- `test_testing_and_sandbox.py` — Test pack generation & workspace sandboxes
- `test_ui.py` — Web Control Center HTTP server, REST APIs, and dashboard

---

## 📂 Project Structure

```text
Defintra/
├── defintra/
│   ├── cli/             # Typer CLI commands & command groups
│   ├── context/         # Minimum Sufficient Context compiler & token optimizer
│   ├── core/
│   │   ├── audit/       # Cryptographic provenance & audit trails
│   │   ├── brownfield/  # Codebase AST scanner & route/model parser
│   │   ├── conflicts/   # Contradiction detection & resolution engine
│   │   ├── contracts/   # Semantic contract versioning & breaking change detector
│   │   ├── db/          # SQLite database schema & migrations
│   │   ├── decisions/   # Decision ledger & preserved disagreement engine
│   │   ├── diff/        # Semantic DIR spec diffing engine
│   │   ├── discovery/   # Fast-path parser & LLM decomposition
│   │   ├── entropy/     # Spec health, entropy & ambiguity scoring
│   │   ├── governance/  # Architecture stability budget & churn index
│   │   ├── graph/       # Knowledge graph traversals & blast radius calculation
│   │   ├── models/      # Pydantic entity models (EARS, Nodes, Edges, Enums)
│   │   ├── operations/  # Incident feedback loop & automated runbooks
│   │   ├── policy/      # Autonomous agent governance & action policy engine
│   │   ├── requirements/# EARS syntax parser & requirement criteria
│   │   ├── sandbox/     # Isolated worktrees & pre-commit governance gates
│   │   ├── tasks/       # Multi-agent dependency scheduling & roadmap engine
│   │   ├── team/        # Multi-agent role coordinator & model routing
│   │   └── testing/     # Human QA test packs & Pytest suite generation
│   ├── export/          # JSON DIR schema & Markdown export serializers
│   ├── mcp/             # Model Context Protocol (MCP) server & tool registry
│   ├── schemas/         # JSON schemas for DIR compliance
│   └── ui/              # Interactive Web Control Center & dashboard (HTML/CSS/JS)
├── tests/               # Full test suite (58 unit & integration tests)
├── pyproject.toml       # Build configuration, ruff & pytest dependencies
├── SPECIFICATION.md     # 50-section formal technical specification
└── README.md            # Project documentation & reference
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
