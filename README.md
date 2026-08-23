# Defintra
> **Define. Validate. Compile. Build.**

Defintra is a project intelligence and control layer for AI software engineering. It maintains a traceable model of requirements, decisions, dependencies, contracts, code, tests, and changes, then compiles the minimum sufficient context an AI agent needs to build, change, test, and deploy safely.

---

## Key Capabilities

1. **Persistent Project Knowledge Graph**: Typed nodes for Facts, Decisions, Assumptions, Unknowns, Contracts, Components, and Dependencies stored in a local-first SQLite graph.
2. **EARS Requirement Notation**: Easy Approach to Requirements Syntax (Ubiquitous, Event-driven, State-driven, Optional, Unwanted behavior).
3. **Decision Ledger with Preserved Disagreement**: Permanent record of accepted choices along with rejected alternatives, reasons, and governance state.
4. **Confidence & Provenance Propagation**: Tracks evidence, confidence scores (0.0–1.0), and down-graph inheritance to surface weak assumptions.
5. **Spec Health & Entropy Metric**: Continuous score representing unresolved ambiguity, pending unknowns, and active conflicts.
6. **Discovery Audit Log**: Surfaces silent assumptions the system made without asking the user.
7. **DIR (Defintra Intermediate Representation)**: Versioned JSON Schema representing machine-actionable project state + human-readable markdown specs.

---

## Quick Start

### Installation
```bash
pip install -e .
```

### Basic Commands
```bash
# Initialize a new Defintra project
defintra init "College Attendance Management System"

# Analyze a raw idea or PRD text
defintra analyze "Build a mobile and web attendance app for university professors with QR code scanning and offline support."

# Run interactive adaptive questioning with live entropy tracking
defintra question

# Check project health, confidence, and graph statistics
defintra status

# Export to DIR schema and human-readable Markdown spec
defintra export --format all
```

---

## Architecture & Roadmap
For the comprehensive 50-section specification and technical architecture, see [SPECIFICATION.md](SPECIFICATION.md).
