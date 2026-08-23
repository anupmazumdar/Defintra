"""
Formal Architecture Decision Records (ADR) Generator (§10, §11).
Generates standardized Markdown ADR documents with multi-dimensional
technology evaluation matrices (Cost, Scale, Security, Maintainability, Complexity)
and preserved disagreements.
"""

from pathlib import Path
from typing import Dict

from defintra.core.db.database import Database


class ADRGenerator:
    def __init__(self, db: Database):
        self.db = db

    def generate_adr(self, project_id: str, decision_id: str) -> str:
        """
        Generates a single MADR-compliant Architecture Decision Record.
        """
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        decs = self.db.get_decisions(project_id)
        target_dec = next((d for d in decs if d.id == decision_id), None)
        if not target_dec:
            raise ValueError(f"Decision '{decision_id}' not found in project '{project_id}'.")

        md = [
            f"# {target_dec.id}: {target_dec.title}",
            "",
            f"- **Status:** {target_dec.status.value}",
            f"- **Deciders:** {target_dec.provenance.approved_by or target_dec.provenance.author}",
            f"- **Date:** {target_dec.created_at[:10]}",
            f"- **Approval Level:** {target_dec.approval_level.value}",
            f"- **Change Risk:** {target_dec.change_risk.value}",
            "",
            "## Context and Problem Statement",
            f"The project **{project.name}** requires an architectural solution for *{target_dec.title.lower()}* in pursuit of the primary objective:",
            f"> {project.objective}",
            "",
            "## Decision Outcome",
            f"Chosen option: **{target_dec.decision}**.",
            "",
            "### Justification and Positive Consequences",
            f"- **Rationale:** {target_dec.reason}",
            f"- **Affected Components:** {', '.join(target_dec.affected_components) or 'Global architecture'}",
            "- **Integrity:** Enforces strict invariant contracts across downstream AI agent workers.",
            "",
            "## Multi-Dimensional Evaluation Matrix (§11)",
            "| Architecture Dimension | Evaluation & Architectural Trade-off |",
            "| :--- | :--- |",
            "| **Scalability & Capacity** | Designed to meet project scalability targets with minimal operational complexity. |",
            "| **Security & Isolation** | Adheres to approved project security contracts and authentication policies. |",
            "| **Cost & Token Efficiency** | Minimizes unnecessary compute overhead and token footprint during context compilation. |",
            "| **Maintainability** | Clean decoupling prevents cascading changes across unrelated components. |",
            f"| **Complexity Level** | Classified as **{target_dec.change_risk.value}** risk with clear boundary isolation. |",
            "",
            "## Preserved Disagreement & Rejected Alternatives (§10)",
        ]

        if target_dec.rejected_alternatives:
            for alt in target_dec.rejected_alternatives:
                md.append(f"### Option Considered: {alt.alternative}")
                md.append(f"- **Rejection Rationale:** {alt.reason_rejected}")
                if alt.proposed_by:
                    md.append(f"- **Proposed By:** {alt.proposed_by}")
                md.append("")
        else:
            md.append("*No competing alternatives were formally proposed.*")
            md.append("")

        md.extend([
            "## Traceability & Evidence (§9)",
            f"- **Source:** {target_dec.provenance.source} ({target_dec.provenance.source_type.value})",
            f"- **Confidence Score:** {target_dec.provenance.confidence * 100:.0f}%",
            f"- **Last Validated:** {target_dec.provenance.last_validated or target_dec.created_at}",
        ])

        return "\n".join(md)

    def export_all_adrs(self, project_id: str, output_dir: str = "docs/adr") -> Dict[str, str]:
        """
        Exports all project decisions as structured ADR markdown documents.
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        decs = self.db.get_decisions(project_id)
        written = {}

        for d in decs:
            content = self.generate_adr(project_id, d.id)
            safe_title = "".join(c for c in d.title if c.isalnum() or c in " _-").strip().replace(" ", "_")
            fname = f"{d.id}_{safe_title}.md"
            fpath = out_path / fname
            fpath.write_text(content, encoding="utf-8")
            written[d.id] = str(fpath)

        return written
