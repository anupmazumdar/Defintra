"""
Dual-Track Exporter (§22).
Produces both:
1. Structured machine-actionable DIR (Defintra Intermediate Representation) JSON
2. Human-readable narrative Project Brief & Architecture Specification (Markdown)
3. Separate component exports (requirements.json, decisions.json, etc.)
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from defintra.core.db.database import Database
from defintra.core.entropy.calculator import EntropyCalculator
from defintra.core.graph.engine import ProjectGraph
from defintra.schemas.validator import validate_dir


class Exporter:
    def __init__(self, db: Database, project_id: str):
        self.db = db
        self.project_id = project_id

    def build_dir_payload(self) -> Dict[str, Any]:
        project = self.db.get_project(self.project_id)
        if not project:
            raise ValueError(f"Project with ID '{self.project_id}' not found.")

        reqs = self.db.get_requirements(self.project_id)
        decs = self.db.get_decisions(self.project_id)
        asms = self.db.get_assumptions(self.project_id)
        unks = self.db.get_unknowns(self.project_id)
        comps = self.db.get_components(self.project_id)
        contracts = self.db.get_contracts(self.project_id)
        conflicts = self.db.get_conflicts(self.project_id)
        audit_entries = self.db.get_audit_entries(self.project_id)

        health_report = EntropyCalculator.compute(reqs, decs, asms, unks, conflicts)

        dir_data = {
            "schema_version": "1.0.0",
            "project": {
                "id": project.id,
                "name": project.name,
                "objective": project.objective,
                "domain": project.domain,
                "source_type": project.source_type,
            },
            "health": health_report.to_dict(),
            "requirements": [
                {
                    "id": r.id,
                    "title": r.title,
                    "description": r.description,
                    "ears_pattern": r.ears_pattern.value,
                    "priority": r.priority.value,
                    "status": r.status.value,
                    "category": r.category,
                    "affected_components": r.affected_components,
                    "constraints": r.constraints,
                    "acceptance_criteria": r.acceptance_criteria,
                }
                for r in reqs
            ],
            "decisions": [
                {
                    "id": d.id,
                    "title": d.title,
                    "decision": d.decision,
                    "reason": d.reason,
                    "rejected_alternatives": [alt.model_dump() for alt in d.rejected_alternatives],
                    "status": d.status.value,
                    "approval_level": d.approval_level.value,
                    "change_risk": d.change_risk.value,
                    "superseded_by": d.superseded_by,
                }
                for d in decs
            ],
            "assumptions": [
                {
                    "id": a.id,
                    "statement": a.statement,
                    "category": a.category,
                    "confidence": a.confidence,
                    "status": a.status,
                }
                for a in asms
            ],
            "unknowns": [
                {
                    "id": u.id,
                    "question": u.question,
                    "impact": u.impact,
                    "category": u.category,
                    "status": u.status,
                    "resolution": u.resolution,
                }
                for u in unks
            ],
            "components": [
                {
                    "id": c.id,
                    "name": c.name,
                    "component_type": c.component_type,
                    "description": c.description,
                    "stability_state": c.stability_state.value,
                    "blast_radius": c.blast_radius,
                }
                for c in comps
            ],
            "contracts": [
                {
                    "id": ct.id,
                    "name": ct.name,
                    "contract_type": ct.contract_type,
                    "version": ct.version,
                    "specification": ct.specification,
                    "status": ct.status.value,
                }
                for ct in contracts
            ],
            "conflicts": [
                {
                    "id": cf.id,
                    "title": cf.title,
                    "description": cf.description,
                    "entity_a_ref": cf.entity_a_ref,
                    "entity_b_ref": cf.entity_b_ref,
                    "severity": cf.severity,
                    "status": cf.status,
                    "resolution": cf.resolution,
                }
                for cf in conflicts
            ],
            "discovery_audit": [
                {
                    "id": entry.id,
                    "silent_assumption": entry.silent_assumption,
                    "reason_skipped": entry.reason_skipped,
                    "risk_level": entry.risk_level.value,
                    "category": entry.category,
                }
                for entry in audit_entries
            ],
        }

        # Validate DIR against schema
        is_valid, errors = validate_dir(dir_data)
        if not is_valid:
            print(f"Warning: DIR schema validation reported {len(errors)} issues: {errors}")

        return dir_data

    def generate_markdown_spec(self) -> str:
        project = self.db.get_project(self.project_id)
        if not project:
            return "# Project Specification\nNo project found."

        reqs = self.db.get_requirements(self.project_id)
        decs = self.db.get_decisions(self.project_id)
        asms = self.db.get_assumptions(self.project_id)
        unks = self.db.get_unknowns(self.project_id)
        comps = self.db.get_components(self.project_id)
        contracts = self.db.get_contracts(self.project_id)
        conflicts = self.db.get_conflicts(self.project_id)
        audit_entries = self.db.get_audit_entries(self.project_id)
        health_report = EntropyCalculator.compute(reqs, decs, asms, unks, conflicts)
        graph = ProjectGraph(self.db, self.project_id)

        md = [
            f"# {project.name} — Project Specification",
            f"> **Domain:** {project.domain} | **Source:** {project.source_type} | **Health Score:** {health_report.health_score}% (Entropy: {round(health_report.entropy, 2)})",
            "",
            "## 1. Executive Summary & Objective",
            project.objective,
            "",
            "## 2. Specification Health & Entropy Status",
            f"- **Entropy Rating:** {round(health_report.entropy, 3)} / 1.0",
            f"- **Spec Health Score:** {health_report.health_score}%",
            f"- **Open Unknowns:** {len([u for u in unks if u.status == 'OPEN'])}",
            f"- **Active Conflicts:** {len([c for c in conflicts if c.status == 'OPEN'])}",
            "",
            "### Recommendations:",
        ]

        for rec in health_report.recommendations:
            md.append(f"- {rec}")

        md.extend(["", "## 3. Requirements (EARS Syntax)", ""])
        for r in reqs:
            md.append(f"### `{r.id}`: {r.title}")
            md.append(f"- **Statement (EARS - {r.ears_pattern.value}):** `{r.description}`")
            md.append(f"- **Priority:** {r.priority.value} | **Status:** {r.status.value} | **Confidence:** {r.provenance.confidence}")
            if r.affected_components:
                md.append(f"- **Affected Components:** {', '.join(r.affected_components)}")
            if r.acceptance_criteria:
                md.append("- **Acceptance Criteria:**")
                for ac in r.acceptance_criteria:
                    md.append(f"  - [ ] {ac}")
            md.append("")

        md.extend(["## 4. Decision Ledger (with Preserved Disagreement)", ""])
        for d in decs:
            status_tag = f"[{d.status.value}]"
            md.append(f"### `{d.id}`: {d.title} {status_tag}")
            md.append(f"- **Decision:** {d.decision}")
            md.append(f"- **Rationale:** {d.reason}")
            md.append(f"- **Governance:** Level: `{d.approval_level.value}` | Change Risk: `{d.change_risk.value}`")
            if d.superseded_by:
                md.append(f"- **Superseded by:** `{d.superseded_by}`")
            if d.rejected_alternatives:
                md.append("- **Preserved Disagreement (Rejected Alternatives):**")
                for alt in d.rejected_alternatives:
                    md.append(f"  - **{alt.alternative}** (Proposed by: {alt.proposed_by or 'AI'}): *{alt.reason_rejected}*")
            md.append("")

        md.extend(["## 5. Architectural Components & Contracts", ""])
        if comps:
            md.append("### Components:")
            for c in comps:
                md.append(f"- **`{c.id}` ({c.name})**: {c.component_type} — *Status: {c.stability_state.value}*")
            md.append("")

        if contracts:
            md.append("### Contracts:")
            for ct in contracts:
                md.append(f"- **`{ct.id}` ({ct.name})**: {ct.contract_type} v{ct.version}")
            md.append("")

        md.extend(["## 6. Dependency Graph (Mermaid)", "", "```mermaid", graph.to_mermaid(), "```", ""])

        md.extend(["## 7. Assumptions & Unknowns", ""])
        md.append("### Assumptions:")
        for a in asms:
            md.append(f"- `[{a.id}]` ({a.category}, Confidence: {a.confidence}): {a.statement} — *Status: {a.status}*")
        md.append("")

        md.append("### Open Unknowns:")
        for u in unks:
            md.append(f"- `[{u.id}]` (Impact: {u.impact}, Category: {u.category}): **{u.question}** [Status: {u.status}]")
        md.append("")

        if audit_entries:
            md.extend(["## 8. Discovery Audit Log (Silent Assumptions)", ""])
            for entry in audit_entries:
                md.append(f"- `[{entry.id}]` ({entry.risk_level.value} Risk): **Assumed:** {entry.silent_assumption} | *Reason Skipped:* {entry.reason_skipped}")
            md.append("")

        return "\n".join(md)

    def generate_cursorrules(self) -> str:
        project = self.db.get_project(self.project_id)
        if not project:
            raise ValueError(f"Project '{self.project_id}' not found.")
        reqs = self.db.get_requirements(self.project_id)
        decs = self.db.get_decisions(self.project_id)

        lines = [
            "# Defintra Context & Project Rules (.cursorrules)",
            f"# Project: {project.name}",
            "",
            "## 1. Project Intent & Objective",
            f"{project.objective}",
            "",
            "## 2. Approved Architectural Invariants (Locked)",
        ]
        for d in decs:
            lines.append(f"- **{d.id} ({d.title}):** {d.decision} — *{d.reason}*")
        lines.append("")

        lines.append("## 3. Formal EARS Requirements to Satisfy")
        for r in reqs:
            lines.append(f"- `[{r.id}]` ({r.priority.value}): {r.description}")
            for ac in r.acceptance_criteria:
                lines.append(f"  - Criteria: {ac}")
        lines.append("")

        lines.extend([
            "## 4. Agent Execution Guidelines",
            "- Minimal change principle: only modify code directly related to the active task.",
            "- Never contradict locked architectural decisions or change contracts silently.",
            "- Write clean, type-annotated code with matching unit tests.",
        ])
        return "\n".join(lines)

    def generate_claude_md(self) -> str:
        project = self.db.get_project(self.project_id)
        if not project:
            raise ValueError(f"Project '{self.project_id}' not found.")
        reqs = self.db.get_requirements(self.project_id)
        decs = self.db.get_decisions(self.project_id)

        lines = [
            f"# CLAUDE.md — {project.name}",
            "> Project Intelligence & Context generated by Defintra",
            "",
            "## Project Overview",
            f"- **Name:** {project.name}",
            f"- **Objective:** {project.objective}",
            "",
            "## Essential Development Commands",
            "- `python -m pytest` : Run full automated test suite",
            "- `defintra status` : Inspect spec health and open unknowns",
            "- `defintra compile \"<task>\" --role BACKEND_ENGINEER` : Compile minimum sufficient context",
            "- `defintra test-pack --type automated` : Generate EARS-mapped pytest scaffolds",
            "",
            "## Approved Decisions & Architecture",
        ]
        for d in decs:
            lines.append(f"- `{d.id}`: {d.decision} (Reason: {d.reason})")
        lines.append("")

        lines.append("## Requirements Checklist")
        for r in reqs:
            lines.append(f"- [ ] `{r.id}`: {r.description}")
        return "\n".join(lines)

    def generate_agents_md(self) -> str:
        project = self.db.get_project(self.project_id)
        if not project:
            raise ValueError(f"Project '{self.project_id}' not found.")
        reqs = self.db.get_requirements(self.project_id)
        decs = self.db.get_decisions(self.project_id)

        lines = [
            f"# AGENTS.md — {project.name}",
            "> AI Agent Instructions & Architectural Boundaries",
            "",
            "## Role Boundaries & Governance",
            "- Follow the approved project decisions and contracts strictly.",
            "- Respect the Minimum Sufficient Context and do not modify unaffected components.",
            "",
            "## Key Invariants",
        ]
        for d in decs:
            lines.append(f"- **{d.id}:** {d.decision}")
        lines.append("")

        lines.append("## Active Requirements")
        for r in reqs:
            lines.append(f"- `{r.id}`: {r.description}")
        return "\n".join(lines)

    def export_agent_rules(self, target_format: str = "cursor", output_path: Optional[str] = None) -> str:
        fmt = target_format.lower()
        if fmt == "cursor" or fmt == ".cursorrules":
            content = self.generate_cursorrules()
            default_path = ".cursorrules"
        elif fmt == "claude" or fmt == "claude.md":
            content = self.generate_claude_md()
            default_path = "CLAUDE.md"
        else:
            content = self.generate_agents_md()
            default_path = "AGENTS.md"

        target_file = Path(output_path or default_path)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content, encoding="utf-8")
        return str(target_file)

    def export_all(self, output_dir: str = ".defintra/export") -> Dict[str, str]:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        dir_payload = self.build_dir_payload()
        md_spec = self.generate_markdown_spec()

        files_written = {}

        # 1. DIR JSON
        dir_file = out_path / "dir.json"
        dir_file.write_text(json.dumps(dir_payload, indent=2), encoding="utf-8")
        files_written["dir.json"] = str(dir_file)

        # 2. Markdown Spec
        spec_file = out_path / "spec.md"
        spec_file.write_text(md_spec, encoding="utf-8")
        files_written["spec.md"] = str(spec_file)

        # 3. Individual JSON artifacts
        for section in ["requirements", "decisions", "assumptions", "unknowns", "components", "contracts", "conflicts"]:
            f = out_path / f"{section}.json"
            f.write_text(json.dumps(dir_payload.get(section, []), indent=2), encoding="utf-8")
            files_written[f"{section}.json"] = str(f)

        # 4. Agent rule files
        cr_file = out_path / ".cursorrules"
        cr_file.write_text(self.generate_cursorrules(), encoding="utf-8")
        files_written[".cursorrules"] = str(cr_file)

        cl_file = out_path / "CLAUDE.md"
        cl_file.write_text(self.generate_claude_md(), encoding="utf-8")
        files_written["CLAUDE.md"] = str(cl_file)

        ag_file = out_path / "AGENTS.md"
        ag_file.write_text(self.generate_agents_md(), encoding="utf-8")
        files_written["AGENTS.md"] = str(ag_file)

        # 5. Architecture Decision Records (ADRs §10, §11)
        from defintra.core.decisions.adr import ADRGenerator
        adr_gen = ADRGenerator(self.db)
        adr_written = adr_gen.export_all_adrs(self.project_id, str(out_path / "adr"))
        for k, v in adr_written.items():
            files_written[f"adr/{k}"] = v

        # 6. Execution Schedule & Roadmap (§13, §16)
        from defintra.core.tasks.scheduler import TaskScheduler
        scheduler = TaskScheduler(self.db)
        sched_rep = scheduler.schedule_project(self.project_id)
        sched_file = out_path / "schedule.json"
        sched_file.write_text(json.dumps(sched_rep.to_dict(), indent=2), encoding="utf-8")
        files_written["schedule.json"] = str(sched_file)

        return files_written
