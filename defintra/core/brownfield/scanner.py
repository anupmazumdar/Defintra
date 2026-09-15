"""
Brownfield Repository Scanner (§1.5, §38, §45).
Scans an existing codebase to extract architecture components, contracts,
data models, API endpoints, and dependencies into the Defintra Knowledge Graph.
"""

import ast
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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

    @staticmethod
    def _parse_python_ast(content: str) -> Tuple[List[str], List[str]]:
        """
        Parses Python source code using Python's standard library `ast` module (§38).
        Extracts:
        - FastAPI / Flask / Django route decorators from sync and async function definitions.
        - Database model classes (SQLAlchemy declarative models, Django models, __tablename__).
        """
        endpoints: List[str] = []
        models: List[str] = []

        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            return [], []

        for node in ast.walk(tree):
            # 1. API Route Extraction from decorated functions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call):
                        func_node = dec.func
                        route_path: Optional[str] = None
                        http_methods: List[str] = []

                        # Pattern @app.get('/...') or @router.post('/...')
                        if isinstance(func_node, ast.Attribute):
                            method_name = func_node.attr.lower()
                            if method_name in ("get", "post", "put", "delete", "patch", "options", "head"):
                                http_methods.append(method_name.upper())
                            elif method_name in ("route", "api_route"):
                                for kw in dec.keywords:
                                    if kw.arg == "methods":
                                        if isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                                            for elt in kw.value.elts:
                                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                                    http_methods.append(elt.value.upper())
                                if not http_methods:
                                    http_methods.append("GET")

                        # Pattern @get('/...')
                        elif isinstance(func_node, ast.Name):
                            method_name = func_node.id.lower()
                            if method_name in ("get", "post", "put", "delete", "patch", "options", "head"):
                                http_methods.append(method_name.upper())

                        # Extract route path argument
                        if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                            route_path = dec.args[0].value
                        else:
                            for kw in dec.keywords:
                                if kw.arg in ("path", "rule") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                                    route_path = kw.value.value

                        if route_path and http_methods:
                            for m in http_methods:
                                endpoints.append(f"{m} {route_path}")

            # 2. Database model class extraction (SQLAlchemy / Django / Peewee)
            elif isinstance(node, ast.ClassDef):
                is_model = False
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        if any(term in base.id for term in ("Base", "Model", "Document", "Entity")):
                            is_model = True
                            break
                    elif isinstance(base, ast.Attribute):
                        if any(term in base.attr for term in ("Model", "Base", "Document")):
                            is_model = True
                            break
                    elif isinstance(base, ast.Call):
                        is_model = True
                        break

                if is_model:
                    table_name = None
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name) and target.id == "__tablename__":
                                    if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                                        table_name = item.value.value
                    models.append(table_name or node.name)

        return endpoints, models

    @staticmethod
    def _infer_route_behavior(method: str, route: str) -> str:
        method_upper = method.upper().strip()
        route_clean = route.strip()
        segments = [
            seg for seg in route_clean.split("/")
            if seg and seg.lower() not in ("api", "v1", "v2", "v3", "v4", "v0")
        ]
        resource_parts = [s for s in segments if not (s.startswith("{") or s.startswith(":") or s.isdigit())]
        resource = resource_parts[-1] if resource_parts else (segments[-1] if segments else "resource")
        resource_phrase = resource.strip("{}").replace("_", " ").replace("-", " ")

        if method_upper == "GET":
            if any(h in route_clean.lower() for h in ("health", "ping", "status", "ready")):
                return "verify server health metrics and return service status payload"
            if any(s.startswith("{") or s.startswith(":") for s in route_clean.split("/")):
                return f"retrieve and return the specified {resource_phrase} record matching the provided identifier"
            return f"retrieve and return the active collection of {resource_phrase} matching request parameters"
        elif method_upper == "POST":
            if any(a in route_clean.lower() for a in ("auth", "login", "token", "session")):
                return "verify credentials, authenticate the client, and issue secure session tokens"
            return f"validate payload schema, process the {resource_phrase} request, and persist new entity records"
        elif method_upper == "PUT":
            return f"validate payload schema, replace the target {resource_phrase} entity, and return updated state"
        elif method_upper == "PATCH":
            return f"validate partial payload updates, modify the target {resource_phrase} entity, and persist changes"
        elif method_upper == "DELETE":
            return f"verify authorization privileges and delete or soft-delete the specified {resource_phrase} entity"
        else:
            return f"process the {method_upper} request for {route_clean} and return appropriate response payload"

    @staticmethod
    def _detect_frameworks(files: List[Path]) -> List[str]:
        frameworks: Set[str] = set()
        for f in files:
            if not f.is_file():
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                content_lower = content.lower()
                if "fastapi" in content_lower:
                    frameworks.add("FastAPI")
                if "flask" in content_lower:
                    frameworks.add("Flask")
                if "django" in content_lower:
                    frameworks.add("Django")
                if "express" in content_lower or "require('express')" in content_lower:
                    frameworks.add("Express.js")
                if "sqlalchemy" in content_lower or "__tablename__" in content_lower:
                    frameworks.add("SQLAlchemy ORM")
                if "react" in content_lower or "from 'react'" in content_lower:
                    frameworks.add("React")
                if "next" in content_lower:
                    frameworks.add("Next.js")
                if "vue" in content_lower:
                    frameworks.add("Vue.js")
            except Exception:
                pass
        return sorted(list(frameworks))

    @staticmethod
    def _format_sample_paths(files: List[Path], root: Path) -> str:
        if not files:
            return "repository files"
        sample_paths = []
        for f in files[:3]:
            try:
                sample_paths.append(str(f.relative_to(root)).replace("\\", "/"))
            except ValueError:
                sample_paths.append(f.name)
        desc = ", ".join(sample_paths)
        if len(files) > 3:
            desc += f" (and {len(files) - 3} more)"
        return desc


    def scan_repository(
        self,
        repo_path: str,
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> ScanReport:
        root = Path(repo_path).resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Target repository path '{repo_path}' does not exist or is not a directory.")

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
            if f_path.suffix == ".py":
                try:
                    content = f_path.read_text(encoding="utf-8", errors="ignore")
                    # Real Python AST parsing
                    ast_endpoints, ast_models = self._parse_python_ast(content)
                    if ast_endpoints:
                        api_endpoints.extend(ast_endpoints)
                    if ast_models:
                        sql_tables.extend(ast_models)

                    # Regex fallback if AST parsing detected no routes
                    if not ast_endpoints:
                        routes = re.findall(r"@(?:app|router)\.(get|post|put|delete|patch)\([\"']([^\"']+)[\"']", content)
                        for method, route in routes:
                            api_endpoints.append(f"{method.upper()} {route}")

                    # Regex fallback if AST parsing detected no models
                    if not ast_models:
                        tables = re.findall(r"class\s+([A-Za-z0-9_]+)\(.*(?:Base|Model).*\):", content)
                        for t in tables:
                            sql_tables.append(t)
                except (OSError, UnicodeDecodeError):
                    pass

            elif f_path.suffix in [".ts", ".js"]:
                try:
                    content = f_path.read_text(encoding="utf-8", errors="ignore")
                    # Express / JS route pattern matches
                    express_routes = re.findall(r"(?:app|router)\.(get|post|put|delete|patch)\([\"']([^\"']+)[\"']", content)
                    for method, route in express_routes:
                        api_endpoints.append(f"{method.upper()} {route}")
                except (OSError, UnicodeDecodeError):
                    pass

            elif f_path.suffix == ".sql":
                try:
                    content = f_path.read_text(encoding="utf-8", errors="ignore")
                    create_tables = re.findall(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)", content, re.IGNORECASE)
                    sql_tables.extend(create_tables)
                except (OSError, UnicodeDecodeError):
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

        # 4. Create Inferred Initial & Task-Specific EARS Requirements (§1.5, §38)
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

        # 4.1 Discovered API Routes Requirements (Event-Driven)
        # "WHEN a request hits [METHOD] [route], the system shall [inferred behavior]"
        unique_endpoints = sorted(list(set(api_endpoints)))
        backend_comp_name = (
            components[f"COMP-BACKEND_{p_id}"].name
            if f"COMP-BACKEND_{p_id}" in components
            else "Backend & API Services"
        )
        for idx, ep in enumerate(unique_endpoints, start=1):
            parts = ep.split(" ", 1)
            if len(parts) == 2:
                method, route = parts[0].upper(), parts[1]
            else:
                method, route = "GET", ep

            behavior = self._infer_route_behavior(method, route)
            route_req = EARSEngine.create_requirement(
                req_id=f"REQ-ROUTE-{idx:02d}_{p_id}",
                project_id=p_id,
                title=f"API Route: {method} {route}",
                system_name="system",
                response=behavior,
                pattern=EARSPattern.EVENT_DRIVEN,
                trigger=f"a request hits {method} {route}",
                priority=RequirementPriority.HIGH,
                category="API_ROUTE",
                affected_components=[backend_comp_name],
                acceptance_criteria=[
                    f"Return HTTP 200/2xx upon successful processing of {method} {route}",
                    f"Validate all request inputs, parameters, and payloads for {route}",
                    f"Return appropriate HTTP error codes on invalid requests or missing resources for {route}",
                ],
                confidence=0.95,
            )
            route_req.status = ArtifactState.IMPLEMENTED
            self.db.save_requirement(route_req)

        # 4.2 Discovered Models / Schemas Requirements (Data Contract)
        unique_models = sorted(list(set(sql_tables)))
        db_comp_name = (
            components[f"COMP-DATABASE_{p_id}"].name
            if f"COMP-DATABASE_{p_id}" in components
            else "Database & Data Storage"
        )
        for idx, model_name in enumerate(unique_models, start=1):
            model_req = EARSEngine.create_requirement(
                req_id=f"REQ-MODEL-{idx:02d}_{p_id}",
                project_id=p_id,
                title=f"Data Contract: {model_name}",
                system_name="database storage layer",
                response=f"persist and enforce schema structure, relational integrity, and field validation for the {model_name} data model",
                pattern=EARSPattern.UBIQUITOUS,
                priority=RequirementPriority.HIGH,
                category="DATA_CONTRACT",
                affected_components=[db_comp_name],
                acceptance_criteria=[
                    f"Ensure database schema maintains structural definitions for {model_name}",
                    f"Enforce primary keys, unique constraints, and foreign key relationships for {model_name}",
                    f"Prevent invalid or malformed records from persisting into {model_name}",
                ],
                confidence=0.95,
            )
            model_req.status = ArtifactState.IMPLEMENTED
            self.db.save_requirement(model_req)

        # 4.3 Discovered Components Requirements (Component-Level Architecture)
        backend_frameworks = self._detect_frameworks(backend_files)
        frontend_frameworks = self._detect_frameworks(frontend_files)
        db_frameworks = self._detect_frameworks(db_files)

        if f"COMP-BACKEND_{p_id}" in components:
            fw_desc = ", ".join(backend_frameworks) if backend_frameworks else "modular server"
            sample_paths = self._format_sample_paths(backend_files, root)
            comp_backend_req = EARSEngine.create_requirement(
                req_id=f"REQ-COMP-BACKEND_{p_id}",
                project_id=p_id,
                title=f"Component Architecture: {components[f'COMP-BACKEND_{p_id}'].name}",
                system_name=components[f"COMP-BACKEND_{p_id}"].name,
                response=f"organize request routing, business logic, and service controllers adhering to {fw_desc} patterns across {sample_paths}",
                pattern=EARSPattern.UBIQUITOUS,
                priority=RequirementPriority.HIGH,
                category="ARCHITECTURE",
                affected_components=[components[f"COMP-BACKEND_{p_id}"].name],
                acceptance_criteria=[
                    f"Maintain clean separation of concerns in {components[f'COMP-BACKEND_{p_id}'].name}",
                    f"Adhere to {fw_desc} architectural conventions for all backend service files",
                ],
                confidence=0.9,
            )
            comp_backend_req.status = ArtifactState.IMPLEMENTED
            self.db.save_requirement(comp_backend_req)

        if f"COMP-FRONTEND_{p_id}" in components:
            fw_desc = ", ".join(frontend_frameworks) if frontend_frameworks else "responsive web"
            sample_paths = self._format_sample_paths(frontend_files, root)
            comp_frontend_req = EARSEngine.create_requirement(
                req_id=f"REQ-COMP-FRONTEND_{p_id}",
                project_id=p_id,
                title=f"Component Architecture: {components[f'COMP-FRONTEND_{p_id}'].name}",
                system_name=components[f"COMP-FRONTEND_{p_id}"].name,
                response=f"render user interfaces, manage client-side state, and handle user interactions adhering to {fw_desc} patterns across {sample_paths}",
                pattern=EARSPattern.UBIQUITOUS,
                priority=RequirementPriority.MEDIUM,
                category="ARCHITECTURE",
                affected_components=[components[f"COMP-FRONTEND_{p_id}"].name],
                acceptance_criteria=[
                    f"Ensure responsive UI layout and state handling in {components[f'COMP-FRONTEND_{p_id}'].name}",
                    f"Adhere to {fw_desc} component conventions for all frontend client files",
                ],
                confidence=0.9,
            )
            comp_frontend_req.status = ArtifactState.IMPLEMENTED
            self.db.save_requirement(comp_frontend_req)

        if f"COMP-DATABASE_{p_id}" in components:
            fw_desc = ", ".join(db_frameworks) if db_frameworks else "relational database"
            sample_paths = self._format_sample_paths(db_files, root)
            comp_db_req = EARSEngine.create_requirement(
                req_id=f"REQ-COMP-DATABASE_{p_id}",
                project_id=p_id,
                title=f"Component Architecture: {components[f'COMP-DATABASE_{p_id}'].name}",
                system_name=components[f"COMP-DATABASE_{p_id}"].name,
                response=f"manage schema migrations, relational constraints, and persistent storage operations adhering to {fw_desc} patterns across {sample_paths}",
                pattern=EARSPattern.UBIQUITOUS,
                priority=RequirementPriority.HIGH,
                category="DATA_CONTRACT",
                affected_components=[components[f"COMP-DATABASE_{p_id}"].name],
                acceptance_criteria=[
                    f"Maintain schema migration history and relational integrity in {components[f'COMP-DATABASE_{p_id}'].name}",
                    f"Adhere to {fw_desc} patterns for all database entities and tables",
                ],
                confidence=0.9,
            )
            comp_db_req.status = ArtifactState.IMPLEMENTED
            self.db.save_requirement(comp_db_req)

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
