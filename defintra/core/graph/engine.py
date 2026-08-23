"""
Project Knowledge Graph Engine (§7, §9, §13, §14, §21).
Provides NetworkX-backed dependency graph representation, forward & reverse traceability,
blast-radius impact analysis, confidence propagation, and Mermaid/ASCII rendering.
"""

from typing import Any, Dict, List, Set, Tuple
import networkx as nx

from defintra.core.db.database import Database
from defintra.core.models.entities import (
    ApprovalLevel,
    ArtifactState,
    ChangeRisk,
    Component,
    Contract,
    Decision,
    DependencyEdge,
    DependencyKind,
    EntityType,
    Requirement,
)


class BlastRadiusReport:
    def __init__(
        self,
        target_node: str,
        affected_nodes: List[Dict[str, Any]],
        unaffected_components: List[str],
        risk_level: ChangeRisk,
        approval_required: ApprovalLevel,
        total_blast_count: int,
    ):
        self.target_node = target_node
        self.affected_nodes = affected_nodes
        self.unaffected_components = unaffected_components
        self.risk_level = risk_level
        self.approval_required = approval_required
        self.total_blast_count = total_blast_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_node": self.target_node,
            "total_blast_count": self.total_blast_count,
            "risk_level": self.risk_level.value,
            "approval_required": self.approval_required.value,
            "affected_nodes": self.affected_nodes,
            "unaffected_components": self.unaffected_components,
        }


class ProjectGraph:
    def __init__(self, db: Database, project_id: str):
        self.db = db
        self.project_id = project_id
        self.graph = nx.DiGraph()
        self.build_graph()

    def build_graph(self):
        self.graph.clear()

        # Load entities
        reqs = self.db.get_requirements(self.project_id)
        decs = self.db.get_decisions(self.project_id)
        asms = self.db.get_assumptions(self.project_id)
        comps = self.db.get_components(self.project_id)
        contracts = self.db.get_contracts(self.project_id)
        deps = self.db.get_dependencies(self.project_id)

        for r in reqs:
            self.graph.add_node(
                r.id,
                entity_type=EntityType.REQUIREMENT,
                title=r.title,
                status=r.status.value,
                confidence=r.provenance.confidence,
                obj=r,
            )

        for d in decs:
            self.graph.add_node(
                d.id,
                entity_type=EntityType.DECISION,
                title=d.title,
                status=d.status.value,
                confidence=d.provenance.confidence,
                obj=d,
            )

        for a in asms:
            self.graph.add_node(
                a.id,
                entity_type=EntityType.ASSUMPTION,
                title=a.statement[:30] + "...",
                status=a.status,
                confidence=a.confidence,
                obj=a,
            )

        for c in comps:
            self.graph.add_node(
                c.id,
                entity_type=EntityType.COMPONENT,
                title=c.name,
                status=c.stability_state.value,
                confidence=1.0,
                obj=c,
            )

        for ct in contracts:
            self.graph.add_node(
                ct.id,
                entity_type=EntityType.CONTRACT,
                title=f"{ct.contract_type}: {ct.name}",
                status=ct.status.value,
                confidence=1.0,
                obj=ct,
            )

        # Add explicit edges
        for dep in deps:
            if dep.source_id in self.graph and dep.target_id in self.graph:
                self.graph.add_edge(
                    dep.source_id,
                    dep.target_id,
                    kind=dep.dependency_kind.value,
                    description=dep.description,
                )

        # Add implicit edges from entity linkages (e.g. req.affected_components)
        for r in reqs:
            for comp_name in r.affected_components:
                comp_node = next(
                    (c.id for c in comps if c.name.lower() == comp_name.lower() or c.id == comp_name),
                    None,
                )
                if comp_node and comp_node in self.graph:
                    self.graph.add_edge(r.id, comp_node, kind=DependencyKind.AFFECTS.value)

        for d in decs:
            for comp_name in d.affected_components:
                comp_node = next(
                    (c.id for c in comps if c.name.lower() == comp_name.lower() or c.id == comp_name),
                    None,
                )
                if comp_node and comp_node in self.graph:
                    self.graph.add_edge(d.id, comp_node, kind=DependencyKind.AFFECTS.value)

    def calculate_blast_radius(self, node_id: str) -> BlastRadiusReport:
        """
        Calculates downstream impact if node_id is modified (§14, §15).
        """
        if node_id not in self.graph:
            return BlastRadiusReport(
                target_node=node_id,
                affected_nodes=[],
                unaffected_components=[],
                risk_level=ChangeRisk.LOW,
                approval_required=ApprovalLevel.NONE,
                total_blast_count=0,
            )

        # Downstream reachable nodes via BFS/DFS
        descendants = nx.descendants(self.graph, node_id)
        affected_nodes_info = []

        components = self.db.get_components(self.project_id)
        all_comp_ids = {c.id for c in components}
        affected_comp_ids = set()

        for d_id in descendants:
            data = self.graph.nodes.get(d_id, {})
            etype = data.get("entity_type", EntityType.PROJECT)
            status = data.get("status", "PROPOSED")
            if etype == EntityType.COMPONENT or d_id in all_comp_ids:
                affected_comp_ids.add(d_id)

            affected_nodes_info.append(
                {
                    "id": d_id,
                    "type": etype.value if hasattr(etype, "value") else str(etype),
                    "title": data.get("title", ""),
                    "status": status,
                }
            )

        unaffected_components = [
            c.name for c in components if c.id not in affected_comp_ids and c.id != node_id
        ]

        # Calculate Risk and Governance
        blast_count = len(descendants)
        target_data = self.graph.nodes.get(node_id, {})
        target_status = target_data.get("status", "PROPOSED")

        if blast_count >= 6 or target_status in [ArtifactState.APPROVED.value, ArtifactState.VERIFIED.value]:
            risk_level = ChangeRisk.HIGH
            approval_required = ApprovalLevel.USER
        elif blast_count >= 2:
            risk_level = ChangeRisk.MEDIUM
            approval_required = ApprovalLevel.USER
        else:
            risk_level = ChangeRisk.LOW
            approval_required = ApprovalLevel.NONE

        if blast_count >= 10:
            risk_level = ChangeRisk.CRITICAL
            approval_required = ApprovalLevel.TWO_PERSON

        return BlastRadiusReport(
            target_node=node_id,
            affected_nodes=affected_nodes_info,
            unaffected_components=unaffected_components,
            risk_level=risk_level,
            approval_required=approval_required,
            total_blast_count=blast_count,
        )

    def trace_origin(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Reverse Traceability (§21): Traces upstream ancestors to answer "Why does this exist?".
        """
        if node_id not in self.graph:
            return []

        ancestors = nx.ancestors(self.graph, node_id)
        origins = []
        for anc_id in ancestors:
            data = self.graph.nodes.get(anc_id, {})
            origins.append(
                {
                    "id": anc_id,
                    "type": data.get("entity_type", "").value
                    if hasattr(data.get("entity_type", ""), "value")
                    else str(data.get("entity_type", "")),
                    "title": data.get("title", ""),
                    "confidence": data.get("confidence", 1.0),
                }
            )
        return origins

    def propagate_confidence(self) -> Dict[str, float]:
        """
        Confidence Propagation (§9):
        Calculates effective confidence down the graph.
        Effective confidence of node = min(own_confidence, min(ancestors_confidence)).
        """
        effective_confidences = {}
        for node in nx.topological_sort(self.graph) if nx.is_directed_acyclic_graph(self.graph) else self.graph.nodes:
            own_conf = self.graph.nodes[node].get("confidence", 0.9)
            predecessors = list(self.graph.predecessors(node))
            if not predecessors:
                effective_confidences[node] = own_conf
            else:
                pred_min = min(effective_confidences.get(p, 1.0) for p in predecessors)
                effective_confidences[node] = round(min(own_conf, pred_min), 2)

        return effective_confidences

    def to_mermaid(self) -> str:
        """
        Generates Mermaid diagram representing the requirement & dependency graph.
        """
        lines = ["graph TD"]
        for node, data in self.graph.nodes(data=True):
            etype = data.get("entity_type", "")
            etype_str = etype.value if hasattr(etype, "value") else str(etype)
            title = data.get("title", node).replace('"', "'")
            lines.append(f'    {node}["{node}: {title} ({etype_str})"]')

        for u, v, data in self.graph.edges(data=True):
            kind = data.get("kind", "relates")
            lines.append(f"    {u} -->|{kind}| {v}")

        return "\n".join(lines)

    def to_ascii_tree(self) -> str:
        """
        Renders plain text hierarchical view of the graph.
        """
        lines = []
        root_nodes = [n for n in self.graph.nodes if self.graph.in_degree(n) == 0]
        if not root_nodes:
            root_nodes = list(self.graph.nodes)[:10]

        visited = set()

        def _render(node_id: str, prefix: str = ""):
            visited.add(node_id)
            data = self.graph.nodes.get(node_id, {})
            title = data.get("title", "")
            etype = data.get("entity_type", "")
            etype_str = etype.value if hasattr(etype, "value") else str(etype)
            lines.append(f"{prefix}├── [{node_id}] {title} ({etype_str})")

            children = list(self.graph.successors(node_id))
            for i, child in enumerate(children):
                if child not in visited:
                    next_prefix = prefix + "│   "
                    _render(child, next_prefix)

        for root in root_nodes:
            _render(root)

        return "\n".join(lines)
