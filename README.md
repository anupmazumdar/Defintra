# Defintra — Project Intelligence & Control Layer

<p align="center">
  <strong>Define. Validate. Compile. Build.</strong><br>
  <em>The definitive project intelligence and governance layer for AI-native software engineering.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/status-active-emerald.svg" alt="Status">
  <img src="https://img.shields.io/badge/MCP-compatible-purple.svg" alt="MCP Compatible">
  <img src="https://img.shields.io/badge/tests-passing-brightgreen.svg" alt="Tests Passing">
</p>

---

## 📖 Overview

Modern AI coding agents fail not because they cannot write code, but because they lack **grounded context, architectural boundaries, and traceable requirements**. When context windows are flooded with irrelevant files, agents hallucinate, contradict earlier decisions, and introduce silent regressions.

**Defintra** is a project intelligence and control layer that bridges the gap between human architectural intent and autonomous AI agents. It maintains a living, persistent knowledge graph of your project (requirements, decisions, assumptions, unknowns, contracts, components, and dependencies), detects conflicts, and compiles the **Minimum Sufficient Context** tailored specifically for each agent role and target model.

```
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
       |  - Stability & Churn Budget         - Incident Feedback Loop          |
       |  - Test Pack Scaffolder (Pytest/QA) - Operations & Runbooks           |
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
       |  AI CODING AGENTS  |    |  MCP INTEGRATIONS  |    |  WEB CONTROL CTR   |
       | (Cursor / Claude / |    | (Model Context     |    | (Real-time GUI     |
       |  Antigravity / etc)|    |  Protocol Tools)   |    |  `defintra ui`)    |
       +--------------------+    +--------------------+    +--------------------+
```

---

## ⚡ Key Features

| Capability | Description |
| :--- | :--- |
| **🌐 Interactive Web Dashboard (`defintra ui`)** | Real-time glassmorphic control center with live Spec Health gauge, interactive SVG knowledge graph, decision ledger, live questioning loop, context studio, and runbook viewer. |
| **🧠 Persistent Typed Knowledge Graph** | Local-first SQLite graph modeling Requirements, Decisions, Assumptions, Unknowns, Contracts, Components, and Dependencies. |
| **📐 EARS Requirement Engine** | Easy Approach to Requirements Syntax (Ubiquitous, Event-driven, State-driven, Optional, Unwanted behavior) with verification criteria. |
| **🎯 Minimum Sufficient Context Compiler** | Compiles role-tailored prompt payloads (`BACKEND_ENGINEER`, `FRONTEND_ENGINEER`, `SOFTWARE_ARCHITECT`, `SECURITY_ENGINEER`, `QA_ENGINEER`, `PRODUCT_ANALYST`) optimized for token ceilings. |
| **🔍 Brownfield Codebase Ingestion (`defintra scan`)** | AST and pattern scanners that inspect existing projects (FastAPI, Flask, Django, Express, React, etc.) and extract routes, models, and components into the graph. |
| **⚔️ Contradiction & Conflict Engine** | Automatically detects and helps resolve contradictions between requirements and architectural decisions. |
| **🤖 Multi-Agent Team Coordinator (`defintra team`)** | Manages structured multi-role agent handoffs across the lifecycle with targeted context bundles. |
| **🚨 Incident-to-Requirement Loop (`defintra incident`)** | Ingests production stack traces and maps failures back to originating requirements and assumptions. |
| **🛠️ Operations & Maintenance Runbooks (`defintra runbook`)** | Automated runbooks for Database Backup, Failover, Disaster Recovery, and Zero-Downtime Rollback. |
| **📊 Stability Budget & Churn Index (`defintra stability`)** | Monitors mutation velocity and architectural churn to prevent specification drift. |
| **🔄 Semantic Spec Diffing (`defintra diff`)** | Compares DIR specifications across versions, flagging breaking contract changes and superseded decisions. |
| **🧪 QA Test Packs & Pytest Generation (`defintra test-pack`)** | Generates human verification walkthroughs and runnable automated Pytest suites mapped 1:1 to EARS requirements. |
| **🛡️ Execution Sandboxing (`defintra sandbox`)** | Isolated staging worktrees with snapshot hashing and pre-commit governance gates. |
| **🔌 Model Context Protocol (MCP) Server** | Native MCP server providing rich tool access to Cursor, Claude Code, Antigravity, and VS Code. |

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/anupmazumdar/Defintra.git
cd Defintra

# Install in editable mode
pip install -e .

# Or install with dev dependencies (for testing)
pip install -e ".[dev]"
```

### 2. Initialize a Project

```bash
defintra init "Healthcare Patient Portal"
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

### Multi-Agent Team Dispatch
```bash
# Dispatch tasks across specialized AI team roles with structured handoffs
defintra team "Design Auth & Tenant Isolation" --role SOFTWARE_ARCHITECT
defintra team "Implement JWT Refresh Rotation" --role BACKEND_ENGINEER
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

### Execution Sandboxing
```bash
# Create an isolated staging sandbox for a risky agent implementation
defintra sandbox create --task "auth_refactor"
```

### Impact & Blast Radius Simulation
```bash
# Simulate the downstream impact of changing or removing a node
defintra blast-radius "D-001"
```

### Export & Portability
```bash
# Export knowledge graph to JSON DIR schema and human-readable Markdown
defintra export --out .defintra/export
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

### Adding to Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "defintra": {
      "command": "defintra",
      "args": ["mcp"],
      "env": {}
    }
  }
}
```

### Adding to Cursor (`~/.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "defintra": {
      "command": "python",
      "args": ["-m", "defintra.mcp.server"]
    }
  }
}
```

### Available MCP Tools

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `defintra_compile_context` | `task`, `role`, `target`, `max_tokens` | Compiles the optimal minimum sufficient context for an agent task. |
| `defintra_get_graph` | `node_type` (optional) | Retrieves current knowledge graph nodes and edge relations. |
| `defintra_get_health` | _none_ | Returns the current Spec Health score, entropy, and pending issues. |
| `defintra_add_decision` | `title`, `decision`, `rationale`, `alternatives` | Records an architectural decision with preserved disagreement. |
| `defintra_add_requirement`| `title`, `statement`, `ears_type`, `criteria` | Adds a formal EARS requirement to the project graph. |
| `defintra_answer_unknown` | `unknown_id`, `answer` | Resolves an open unknown, updating confidence and reducing entropy. |

---

## 🧩 Core Architecture & Concepts

### 1. The EARS Requirement Notation
Requirements are structured using the **Easy Approach to Requirements Syntax (EARS)** standard:
- **Ubiquitous**: *The system shall [response].*
- **Event-Driven**: *WHEN [event], the system shall [response].*
- **State-Driven**: *WHILE [state], the system shall [response].*
- **Optional**: *WHERE [feature is enabled], the system shall [response].*
- **Unwanted Behavior**: *IF [error/exception], THEN the system shall [response].*

### 2. The Decision Ledger
Decisions in Defintra preserve rejected alternatives and reasoning alongside the accepted choice:
- **Decision Record**: Unique ID, Title, Accepted Choice, Rationale, Author.
- **Preserved Disagreements**: List of considered alternatives, trade-offs, and why they were rejected.
- **Supersession**: Traceable lineage when decisions evolve over time.

### 3. Minimum Sufficient Context (MSC)
Rather than passing an entire repository to an LLM, Defintra calculates the subgraph reachable from the task's focal components:
1. **Subgraph Extraction**: Identifies relevant requirements, decisions, contracts, and component interfaces.
2. **Role Filtering**: Prunes details irrelevant to the agent's specific role (e.g. hiding CSS tokens from a backend engineer).
3. **Target Formatting**: Formats syntax specifically for the target model (e.g., Claude `<defintra_context>` XML tags or OpenAI Markdown headers).
4. **Token Packing**: Enforces hard token constraints via greedy priority knapsack allocation.

---

## 🧪 Testing

Defintra includes a comprehensive test suite covering all engines, CLI workflows, APIs, and the UI server:

```bash
# Run all tests with pytest
python -m pytest

# Run tests with coverage report
python -m pytest --cov=defintra tests/
```

All 38 test suites pass consistently across:
- `test_brownfield.py` — AST & framework route ingestion
- `test_compiler.py` — Context compilation and token pruning
- `test_conflicts.py` — Contradiction detection & resolution
- `test_database.py` — SQLite schema and graph persistence
- `test_decisions.py` — Decision ledger & disagreement tracking
- `test_discovery.py` — Fast path and deep LLM decomposition
- `test_ears.py` — EARS syntax validation and parsing
- `test_entropy.py` — Spec health and ambiguity scoring
- `test_export_and_schema.py` — DIR JSON export & markdown serialization
- `test_graph.py` — NetworkX graph algorithms & blast radius
- `test_mcp.py` — Model Context Protocol tools & server handlers
- `test_operations.py` — Runbooks & incident feedback loop
- `test_stability_and_diff.py` — Stability budgets & semantic spec diffs
- `test_team_coordinator.py` — Multi-agent role handoff pipelines
- `test_testing_and_sandbox.py` — Test pack generation & workspace sandboxes
- `test_ui.py` — Web Control Center HTTP server, APIs, and dashboard

---

## 📂 Project Structure

```
Defintra/
├── defintra/
│   ├── cli/             # Typer CLI commands & command groups
│   ├── context/         # Minimum Sufficient Context compiler & token optimizer
│   ├── core/
│   │   ├── audit/       # Cryptographic provenance & audit trails
│   │   ├── brownfield/  # Codebase AST scanner & route/model parser
│   │   ├── conflicts/   # Contradiction detection & resolution engine
│   │   ├── db/          # SQLite database schema & migrations
│   │   ├── decisions/   # Decision ledger & preserved disagreement engine
│   │   ├── diff/        # Semantic DIR spec diffing engine
│   │   ├── discovery/   # Fast-path parser & LLM decomposition
│   │   ├── entropy/     # Spec health, entropy & ambiguity scoring
│   │   ├── governance/  # Architecture stability budget & churn index
│   │   ├── graph/       # Knowledge graph traversals & blast radius calculation
│   │   ├── models/      # Pydantic entity models (EARS, Nodes, Edges, Enums)
│   │   ├── operations/  # Incident feedback loop & automated runbooks
│   │   ├── requirements/# EARS syntax parser & requirement criteria
│   │   ├── sandbox/     # Isolated worktrees & pre-commit governance gates
│   │   ├── team/        # Multi-agent role coordinator & model routing
│   │   └── testing/     # Human QA test packs & Pytest suite generation
│   ├── export/          # JSON DIR schema & Markdown export serializers
│   ├── mcp/             # Model Context Protocol (MCP) server & tool registry
│   ├── schemas/         # JSON schemas for DIR compliance
│   └── ui/              # Interactive Web Control Center & dashboard (HTML/CSS/JS)
├── tests/               # Full test suite (38 unit & integration tests)
├── pyproject.toml       # Build configuration & dependencies
├── SPECIFICATION.md     # 50-section formal technical specification
└── README.md            # Project documentation & reference
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
