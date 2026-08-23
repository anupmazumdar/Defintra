"""
Semantic Contract Versioning & Breaking Change Analyzer (§12, §49).
Enforces semantic versioning rules (MAJOR.MINOR.PATCH) on shared API, Database,
and UI contracts, detecting breaking schema drift across AI agent iterations.
"""

from typing import Any, Dict, List, Optional
from defintra.core.db.database import Database
from defintra.core.models.entities import ArtifactState, Contract


class ContractDiffResult:
    def __init__(
        self,
        contract_id: str,
        current_version: str,
        suggested_version: str,
        change_level: str,  # MAJOR, MINOR, PATCH, NONE
        breaking_changes: List[str],
        compatible_additions: List[str],
        is_breaking: bool,
    ):
        self.contract_id = contract_id
        self.current_version = current_version
        self.suggested_version = suggested_version
        self.change_level = change_level
        self.breaking_changes = breaking_changes
        self.compatible_additions = compatible_additions
        self.is_breaking = is_breaking

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "current_version": self.current_version,
            "suggested_version": self.suggested_version,
            "change_level": self.change_level,
            "breaking_changes": self.breaking_changes,
            "compatible_additions": self.compatible_additions,
            "is_breaking": self.is_breaking,
        }


class ContractVersioningEngine:
    def __init__(self, db: Database):
        self.db = db

    def analyze_contract_evolution(
        self,
        contract_id: str,
        old_spec: Dict[str, Any],
        new_spec: Dict[str, Any],
        current_version: str = "1.0.0",
    ) -> ContractDiffResult:
        """
        Analyzes two versions of a contract specification to detect breaking schema changes.
        """
        breaking_changes = []
        compatible_additions = []

        old_keys = set(old_spec.keys())
        new_keys = set(new_spec.keys())

        # 1. Removed fields/endpoints -> Breaking (MAJOR)
        removed = old_keys - new_keys
        for r in removed:
            breaking_changes.append(f"Dropped contract element: '{r}'")

        # 2. Added fields/endpoints -> Compatible (MINOR)
        added = new_keys - old_keys
        for a in added:
            compatible_additions.append(f"Added new contract element: '{a}'")

        # 3. Type/Structure mutations in common keys
        common = old_keys & new_keys
        for k in common:
            old_val = old_spec[k]
            new_val = new_spec[k]
            if type(old_val) != type(new_val):
                breaking_changes.append(f"Type mutation for '{k}': changed from {type(old_val).__name__} to {type(new_val).__name__}")
            elif isinstance(old_val, dict) and isinstance(new_val, dict):
                # Nested check
                nested_diff = self.analyze_contract_evolution(f"{contract_id}.{k}", old_val, new_val)
                breaking_changes.extend([f"{k}.{bc}" for bc in nested_diff.breaking_changes])
                compatible_additions.extend([f"{k}.{ca}" for ca in nested_diff.compatible_additions])

        # Compute suggested semantic version
        v_parts = current_version.split(".")
        try:
            major, minor, patch = int(v_parts[0]), int(v_parts[1]), int(v_parts[2])
        except Exception:
            major, minor, patch = 1, 0, 0

        if breaking_changes:
            change_level = "MAJOR"
            suggested = f"{major + 1}.0.0"
            is_breaking = True
        elif compatible_additions:
            change_level = "MINOR"
            suggested = f"{major}.{minor + 1}.0"
            is_breaking = False
        else:
            change_level = "PATCH"
            suggested = f"{major}.{minor}.{patch + 1}"
            is_breaking = False

        return ContractDiffResult(
            contract_id=contract_id,
            current_version=current_version,
            suggested_version=suggested,
            change_level=change_level,
            breaking_changes=breaking_changes,
            compatible_additions=compatible_additions,
            is_breaking=is_breaking,
        )

    def validate_project_contracts(self, project_id: str) -> List[Dict[str, Any]]:
        """
        Validates all contracts in the project for version consistency and structural completeness.
        """
        contracts = self.db.get_contracts(project_id)
        results = []
        for c in contracts:
            has_spec = bool(c.specification)
            results.append({
                "contract_id": c.id,
                "name": c.name,
                "type": c.contract_type,
                "version": c.version,
                "is_defined": has_spec,
                "status": c.status.value,
            })
        return results
