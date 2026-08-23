"""
Semantic Spec Diffing & Versioning Engine (§49).
Performs semantic diffs between two DIR specifications or versions,
highlighting breaking contract changes, new requirements, and modified decisions.
"""

import json
from pathlib import Path
from typing import Any, Dict, List


class SpecDiffReport:
    def __init__(
        self,
        added_requirements: List[Dict[str, str]],
        removed_requirements: List[Dict[str, str]],
        modified_requirements: List[Dict[str, Any]],
        breaking_contract_changes: List[str],
        superseded_decisions: List[str],
        entropy_delta: float,
        health_score_delta: float,
    ):
        self.added_requirements = added_requirements
        self.removed_requirements = removed_requirements
        self.modified_requirements = modified_requirements
        self.breaking_contract_changes = breaking_contract_changes
        self.superseded_decisions = superseded_decisions
        self.entropy_delta = entropy_delta
        self.health_score_delta = health_score_delta

    def to_dict(self) -> Dict[str, Any]:
        return {
            "added_requirements": self.added_requirements,
            "removed_requirements": self.removed_requirements,
            "modified_requirements": self.modified_requirements,
            "breaking_contract_changes": self.breaking_contract_changes,
            "superseded_decisions": self.superseded_decisions,
            "entropy_delta": round(self.entropy_delta, 4),
            "health_score_delta": round(self.health_score_delta, 2),
            "is_breaking": len(self.breaking_contract_changes) > 0,
        }

    def render_markdown(self) -> str:
        lines = [
            "# Defintra Semantic Specification Diff",
            f"> **Breaking Changes Detected:** {'YES (High Risk)' if self.breaking_contract_changes else 'NO (Safe Evolution)'}",
            f"> **Health Delta:** {self.health_score_delta:+.1f}% | **Entropy Delta:** {self.entropy_delta:+.3f}",
            "",
        ]

        if self.breaking_contract_changes:
            lines.extend(["## ⚠️ Breaking Contract Changes", ""])
            for b in self.breaking_contract_changes:
                lines.append(f"- [BREAKING] {b}")
            lines.append("")

        if self.added_requirements:
            lines.extend(["## ➕ Added Requirements", ""])
            for r in self.added_requirements:
                lines.append(f"- **`{r['id']}`**: {r['title']} — `{r['statement']}`")
            lines.append("")

        if self.removed_requirements:
            lines.extend(["## ➖ Removed Requirements", ""])
            for r in self.removed_requirements:
                lines.append(f"- **`{r['id']}`**: {r['title']}")
            lines.append("")

        if self.modified_requirements:
            lines.extend(["## 📝 Modified Requirements", ""])
            for r in self.modified_requirements:
                lines.append(f"- **`{r['id']}`**: {r['title']} (Statement changed from `{r['old_statement']}` to `{r['new_statement']}`)")
            lines.append("")

        if self.superseded_decisions:
            lines.extend(["## 🔄 Superseded Decisions", ""])
            for d in self.superseded_decisions:
                lines.append(f"- {d}")
            lines.append("")

        if not any([self.added_requirements, self.removed_requirements, self.modified_requirements, self.breaking_contract_changes]):
            lines.append("No semantic differences detected between specifications.")

        return "\n".join(lines)


class SpecDiffEngine:
    @classmethod
    def diff_dirs(cls, dir_a: Dict[str, Any], dir_b: Dict[str, Any]) -> SpecDiffReport:
        reqs_a = {r["id"]: r for r in dir_a.get("requirements", [])}
        reqs_b = {r["id"]: r for r in dir_b.get("requirements", [])}

        contracts_a = {c["id"]: c for c in dir_a.get("contracts", [])}
        contracts_b = {c["id"]: c for c in dir_b.get("contracts", [])}

        decs_a = {d["id"]: d for d in dir_a.get("decisions", [])}
        decs_b = {d["id"]: d for d in dir_b.get("decisions", [])}

        # 1. Requirement diffs
        added_reqs = []
        for rid, r in reqs_b.items():
            if rid not in reqs_a:
                added_reqs.append({"id": rid, "title": r.get("title", ""), "statement": r.get("description", "")})

        removed_reqs = []
        for rid, r in reqs_a.items():
            if rid not in reqs_b:
                removed_reqs.append({"id": rid, "title": r.get("title", "")})

        modified_reqs = []
        for rid, r_b in reqs_b.items():
            if rid in reqs_a:
                r_a = reqs_a[rid]
                if r_a.get("description") != r_b.get("description"):
                    modified_reqs.append({
                        "id": rid,
                        "title": r_b.get("title", ""),
                        "old_statement": r_a.get("description", ""),
                        "new_statement": r_b.get("description", ""),
                    })

        # 2. Contract breaking changes
        breaking_changes = []
        for cid, c_a in contracts_a.items():
            if cid not in contracts_b:
                breaking_changes.append(f"Contract '{c_a.get('name', cid)}' was deleted.")
            else:
                c_b = contracts_b[cid]
                # Compare endpoints / tables
                spec_a = c_a.get("specification", {})
                spec_b = c_b.get("specification", {})
                for ep in spec_a.get("endpoints", []):
                    if ep not in spec_b.get("endpoints", []):
                        breaking_changes.append(f"Endpoint '{ep}' was removed from API contract '{cid}'.")

        # 3. Decision superseding
        superseded = []
        for did, d_b in decs_b.items():
            if d_b.get("status") == "SUPERSEDED" and (did not in decs_a or decs_a[did].get("status") != "SUPERSEDED"):
                superseded.append(f"Decision '{did}' was superseded by '{d_b.get('superseded_by')}'.")

        # 4. Health & Entropy delta
        health_a = dir_a.get("health", {}).get("health_score", 50.0)
        health_b = dir_b.get("health", {}).get("health_score", 50.0)
        health_delta = health_b - health_a

        entropy_a = dir_a.get("health", {}).get("entropy", 0.5)
        entropy_b = dir_b.get("health", {}).get("entropy", 0.5)
        entropy_delta = entropy_b - entropy_a

        return SpecDiffReport(
            added_requirements=added_reqs,
            removed_requirements=removed_reqs,
            modified_requirements=modified_reqs,
            breaking_contract_changes=breaking_changes,
            superseded_decisions=superseded,
            entropy_delta=entropy_delta,
            health_score_delta=health_delta,
        )

    @classmethod
    def diff_from_files(cls, file_a: str, file_b: str) -> SpecDiffReport:
        p_a = Path(file_a)
        p_b = Path(file_b)

        if not p_a.exists():
            raise FileNotFoundError(f"File '{file_a}' not found.")
        if not p_b.exists():
            raise FileNotFoundError(f"File '{file_b}' not found.")

        data_a = json.loads(p_a.read_text(encoding="utf-8"))
        data_b = json.loads(p_b.read_text(encoding="utf-8"))

        return cls.diff_dirs(data_a, data_b)
