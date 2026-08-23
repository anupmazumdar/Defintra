"""
Brownfield Repository Scanner (§1.5, §38, §45).
Scans an existing codebase to extract architecture components, contracts,
data models, API endpoints, and dependencies into the Defintra Knowledge Graph.
"""

import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set

from defintra.core.db.database import Database
from defintra.core.models.entities import (
    ArtifactState,
    Component,
    Contract,
    DependencyEdge,
    DependencyKind,
    EARSPattern,
    EntityType,
    Project,
    RequirementPriority,
    current_utc_time,
)
from defintra.core.requirements.ears import EARSEngine


class ScanReport:
    def __init__(
        self,
        project_id: str,
        repo_path: str,
        files_scanned: int,
        detected_tech_stack: List[str],
        components_found: List[Dict[str, Any]],
        contracts_found: List[Dict[str, Any]],
        dependencies_found: int,
    ):
        self.project_id = project_id
        self.repo_path = repo_path
        self.files_scanned = files_scanned
        self.detected_tech_stack = detected_tech_stack
        self.components_found = components_found
        self.contracts_found = contracts_found
        self.dependencies_found = dependencies_found

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "repo_path": self.repo_path,
            "files_scanned": self.files_scanned,
            "detected_tech_stack": self.detected_tech_stack,
            "components_found": self.components_found,
            "contracts_found": self.contracts_found,
            "dependencies_found": self.dependencies_found,
        }


class BrownfieldScanner:
    def __init__(self, db: Database):
        self.db = db

    def scan_repository(
        self,
        repo_path: str,
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> ScanReport:
        root = Path(repo_path).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Target repository path '{repo_path}' does not exist.")

        p_name = project_name or root.name
        p_id = project_id or re.sub(r"[^a-zA-Z0-9_-]", "_", p_name.lower().strip())

        # Save Project Entity FIRST to satisfy foreign keys
        project = Project(
            id=p_id,
            name=p_name,
            objective=f"Brownfield codebase ingested from {root}",
            domain="INGESTED_REPOSITORY",
            source_type="repo",
            spec_entropy=0.35,
            spec_health_score=75.0,
            created_at=current_utc_time(),
            updated_at=current_utc_time(),
        )
        self.db.save_project(project)

        # Ignore patterns
        ignore_dirs = {
            ".git",
            ".defintra",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            ".pytest_cache",
            "dist",
            "build",
            ".egg-info",
        }

        files_scanned = 0
        tech_stack: Set[str] = set()
        components: Dict[str, Component] = {}
        contracts: List[Contract] = []
        dependencies: List[DependencyEdge] = []

        all_file_paths: List[Path] = []

        for current_root, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.endswith(".egg-info")]
            for f in files:
                all_file_paths.append(Path(current_root) / f)

        files_scanned = len(all_file_paths)

        # 1. Tech Stack & Architecture Component Detection
        has_python = any(f.suffix == ".py" for f in all_file_paths)
        has_ts_js = any(f.suffix in [".ts", ".tsx", ".js", ".jsx"] for f in all_file_paths)
        has_docker = any("Dockerfile" in f.name or "docker-compose" in f.name for f in all_file_paths)
        has_sql = any(f.suffix == ".sql" or "schema" in f.stem.lower() for f in all_file_paths)

        if has_python:
            tech_stack.add("Python")
        if has_ts_js:
            tech_stack.add("TypeScript/JavaScript")
        if has_docker:
            tech_stack.add("Docker / Containerized")
        if has_sql:
            tech_stack.add("SQL Database")

        # 2. Extract Specific Components
        # Backend Component
        backend_files = [
            f for f in all_file_paths
            if any(k in f.parts for k in ["api", "backend", "server", "routes", "controllers", "services"])
            or f.suffix == ".py" or f.name in ["main.go", "server.js", "app.py"]
        ]
        if backend_files or has_python:
            comp_backend = Component(
                id=f"COMP-BACKEND_{p_id}",
                project_id=p_id,
                name="Backend & API Services",
                component_type="BACKEND",
                description=f"Inferred from {len(backend_files)} server files in repository",
                stability_state=ArtifactState.IMPLEMENTED,
            )
            components[comp_backend.id] = comp_backend
            self.db.save_component(comp_backend)

        # Frontend Component
        frontend_files = [
            f for f in all_file_paths
            if any(k in f.parts for k in ["src", "components", "pages", "app", "ui", "views"])
            and f.suffix in [".tsx", ".jsx", ".vue", ".html", ".css"]
        ]
        if frontend_files or has_ts_js:
            comp_frontend = Component(
                id=f"COMP-FRONTEND_{p_id}",
                project_id=p_id,
                name="Frontend Web Application",
                component_type="FRONTEND",
                description=f"Inferred from {len(frontend_files)} client-side UI files",
                stability_state=ArtifactState.IMPLEMENTED,
            )
            components[comp_frontend.id] = comp_frontend
            self.db.save_component(comp_frontend)

        # Database Component
        db_files = [
            f for f in all_file_paths
            if any(k in f.parts for k in ["db", "models", "migrations", "schemas"])
            or f.suffix == ".sql" or "model" in f.stem.lower()
        ]
        if db_files or has_sql:
            comp_db = Component(
                id=f"COMP-DATABASE_{p_id}",
                project_id=p_id,
                name="Database & Data Storage",
                component_type="DATABASE",
                description=f"Inferred from {len(db_files)} schema/model files",
                stability_state=ArtifactState.IMPLEMENTED,
            )
            components[comp_db.id] = comp_db
            self.db.save_component(comp_db)

        # 3. Extract Routes & Contracts from Code
        api_endpoints: List[str] = []
        sql_tables: List[str] = []

        for f_path in all_file_paths:
            if f_path.suffix in [".py", ".ts", ".js"]:
                try:
                    content = f_path.read_text(encoding="utf-8", errors="ignore")
                    # Python FastAPI / Flask route matches
                    routes = re.findall(r"@(?:app|router)\.(get|post|put|delete|patch)\([\"']([^\"']+)[\"']", content)
                    for method, route in routes:
                        api_endpoints.append(f"{method.upper()} {route}")

                    # Express / JS route matches
                    express_routes = re.findall(r"(?:app|router)\.(get|post|put|delete|patch)\([\"']([^\"']+)[\"']", content)
                    for method, route in express_routes:
                        api_endpoints.append(f"{method.upper()} {route}")

                    # SQL / SQLAlchemy table matches
                    tables = re.findall(r"class\s+([A-Za-z0-9_]+)\(.*(?:Base|Model).*\):", content)
                    for t in tables:
                        sql_tables.append(t)
                except Exception:
                    pass

            elif f_path.suffix == ".sql":
                try:
                    content = f_path.read_text(encoding="utf-8", errors="ignore")
                    create_tables = re.findall(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)", content, re.IGNORECASE)
                    sql_tables.extend(create_tables)
                except Exception:
                    pass

        # Create API Contract if endpoints found
        if api_endpoints:
            api_contract = Contract(
                id=f"CONTRACT-API_{p_id}",
                project_id=p_id,
                name="Discovered REST API Endpoints",
                contract_type="API",
                version="1.0.0",
                specification={"endpoints": sorted(list(set(api_endpoints)))},
                status=ArtifactState.IMPLEMENTED,
            )
            contracts.append(api_contract)
            self.db.save_contract(api_contract)

        # Create Database Contract if tables found
        if sql_tables:
            db_contract = Contract(
                id=f"CONTRACT-DB_{p_id}",
                project_id=p_id,
                name="Discovered Database Schema",
                contract_type="DATABASE",
                version="1.0.0",
                specification={"tables": sorted(list(set(sql_tables)))},
                status=ArtifactState.IMPLEMENTED,
            )
            contracts.append(db_contract)
            self.db.save_contract(db_contract)

        # 4. Create Inferred Initial EARS Requirements
        req1 = EARSEngine.create_requirement(
            req_id=f"REQ-BROWNFIELD-01_{p_id}",
            project_id=p_id,
            title="Repository API Contract Integrity",
            system_name="Backend Service",
            response="serve verified API endpoints conforming to the extracted route contract",
            pattern=EARSPattern.UBIQUITOUS,
            priority=RequirementPriority.HIGH,
            affected_components=[c.name for c in components.values()],
            acceptance_criteria=[
                f"Ensure {len(api_endpoints)} discovered endpoints maintain route signatures",
                "Ensure backward compatibility across changes",
            ],
            confidence=0.9,
        )
        req1.status = ArtifactState.IMPLEMENTED
        self.db.save_requirement(req1)

        # 5. Add Dependencies
        if f"COMP-BACKEND_{p_id}" in components and f"COMP-DATABASE_{p_id}" in components:
            dep = DependencyEdge(
                id=f"DEP-BACKEND-DB_{p_id}",
                project_id=p_id,
                source_type=EntityType.COMPONENT,
                source_id=f"COMP-BACKEND_{p_id}",
                target_type=EntityType.COMPONENT,
                target_id=f"COMP-DATABASE_{p_id}",
                dependency_kind=DependencyKind.REQUIRES,
                description="Backend API services require database persistence layer",
            )
            dependencies.append(dep)
            self.db.save_dependency(dep)

        if f"COMP-FRONTEND_{p_id}" in components and f"COMP-BACKEND_{p_id}" in components:
            dep2 = DependencyEdge(
                id=f"DEP-FRONTEND-BACKEND_{p_id}",
                project_id=p_id,
                source_type=EntityType.COMPONENT,
                source_id=f"COMP-FRONTEND_{p_id}",
                target_type=EntityType.COMPONENT,
                target_id=f"COMP-BACKEND_{p_id}",
                dependency_kind=DependencyKind.REQUIRES,
                description="Frontend communicates with Backend API",
            )
            dependencies.append(dep2)
            self.db.save_dependency(dep2)

        return ScanReport(
            project_id=p_id,
            repo_path=str(root),
            files_scanned=files_scanned,
            detected_tech_stack=sorted(list(tech_stack)),
            components_found=[c.model_dump() for c in components.values()],
            contracts_found=[ct.model_dump() for ct in contracts],
            dependencies_found=len(dependencies),
        )
