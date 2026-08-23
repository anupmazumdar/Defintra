"""
Defintra CLI (§38, §46 V0–V7).
Interactive command-line interface for Requirement Intelligence, EARS specs,
Decision Ledger, Context Compilation, Brownfield Ingestion, Conflict Engine,
Testing Packs, Sandboxing, AI Team Orchestration, Incident Feedback, Runbooks,
Architecture Stability Budget, and Semantic Spec Diffing.
"""

import json
from pathlib import Path
from typing import Optional
import typer
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.tree import Tree

from defintra.context.compiler import AgentRole, ContextCompiler, TargetFormat
from defintra.core.audit.logger import DiscoveryAuditLogger
from defintra.core.brownfield.scanner import BrownfieldScanner
from defintra.core.conflicts.engine import ConflictEngine
from defintra.core.db.database import Database
from defintra.core.decisions.ledger import DecisionLedger
from defintra.core.diff.engine import SpecDiffEngine
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.discovery.llm import DeepPathEngine
from defintra.core.entropy.calculator import EntropyCalculator
from defintra.core.governance.recovery import FailureRecoveryEngine
from defintra.core.governance.stability import StabilityBudgetEngine
from defintra.core.governance.staleness import StalenessEngine
from defintra.core.graph.engine import ProjectGraph
from defintra.core.operations.feedback import IncidentTracer
from defintra.core.operations.improvements import PostDeploymentAdvisor
from defintra.core.operations.runbooks import RunbookGenerator
from defintra.core.sandbox.manager import SandboxManager
from defintra.core.team.coordinator import StructuredEventType, TeamCoordinator
from defintra.core.testing.test_packs import TestPackGenerator
from defintra.export.exporter import Exporter
from defintra.ui.server import start_ui_server

app = typer.Typer(
    name="defintra",
    help="Defintra: Project Intelligence and Control Layer for AI Software Engineering.",
    add_completion=False,
)
console = Console()


def get_db() -> Database:
    return Database(".defintra/project.db")


@app.command()
def init(
    name: str = typer.Argument(..., help="Name of the project to initialize"),
    domain: str = typer.Option("COLLEGE_STUDENT", "--domain", "-d", help="Domain template (COLLEGE_STUDENT, SAAS, INTERNAL_TOOL)"),
):
    """
    Initialize a new Defintra project workspace and local SQLite knowledge graph.
    """
    db = get_db()
    engine = DiscoveryEngine(db)
    project = engine.run_fast_path(name, f"Initial project initialization for {name}")

    console.print(
        Panel.fit(
            f"[bold green]Defintra initialized successfully![/bold green]\n"
            f"[cyan]Project ID:[/cyan] {project.id}\n"
            f"[cyan]Name:[/cyan] {project.name}\n"
            f"[cyan]Domain:[/cyan] {project.domain}\n"
            f"[cyan]Database:[/cyan] .defintra/project.db\n"
            f"[cyan]Spec Health:[/cyan] {project.spec_health_score}% (Entropy: {round(project.spec_entropy, 2)})",
            title="Defintra Initialization",
            border_style="green",
        )
    )
    console.print("[dim]Next: Run `defintra analyze \"<your idea or PRD>\"` or `defintra question`[/dim]")


@app.command()
def analyze(
    input_text: str = typer.Argument(..., help="Natural language idea prompt or path to a PRD text file"),
    project_name: Optional[str] = typer.Option(None, "--name", "-n", help="Project name"),
    deep: bool = typer.Option(False, "--deep", help="Run Deep Path recursive decomposition"),
):
    """
    Analyze raw human intent, parse EARS requirements, seed decisions & unknowns, and calculate spec health.
    """
    db = get_db()
    engine = DiscoveryEngine(db)

    # Check if input is a file
    p = Path(input_text)
    if p.exists() and p.is_file():
        raw_content = p.read_text(encoding="utf-8")
        p_name = project_name or p.stem
    else:
        raw_content = input_text
        p_name = project_name or (raw_content.split(".")[0][:30] if raw_content else "New Project")

    with console.status("[bold cyan]Extracting intent, decomposing requirements into EARS, checking unknowns..."):
        project = engine.run_fast_path(p_name, raw_content)
        if deep:
            deep_engine = DeepPathEngine()
            deep_reqs, deep_unks = deep_engine.decompose(project.id, raw_content)
            for dr in deep_reqs:
                db.save_requirement(dr)
            for du in deep_unks:
                db.save_unknown(du)

    reqs = db.get_requirements(project.id)
    decs = db.get_decisions(project.id)
    asms = db.get_assumptions(project.id)
    unks = db.get_unknowns(project.id)
    conflicts = db.get_conflicts(project.id)
    audit = db.get_audit_entries(project.id)

    health_report = EntropyCalculator.compute(reqs, decs, asms, unks, conflicts)

    console.print(
        Panel(
            f"[bold white]{project.name}[/bold white]\n"
            f"[dim]{project.objective[:120]}...[/dim]\n\n"
            f"[bold]Spec Health Score:[/bold] [{'green' if health_report.health_score > 70 else 'yellow'}]{health_report.health_score}%[/]\n"
            f"[bold]Spec Entropy:[/bold] {round(health_report.entropy, 3)} / 1.0\n"
            f"[bold]EARS Requirements:[/bold] {len(reqs)} | [bold]Decisions:[/bold] {len(decs)} | [bold]Open Unknowns:[/bold] {len(unks)} | [bold]Silent Assumptions:[/bold] {len(audit)}",
            title="Analysis Summary",
            border_style="cyan",
        )
    )

    # Display requirements table
    table = Table(title="Generated Requirements (EARS Syntax)")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Pattern", style="magenta")
    table.add_column("Statement", style="white")
    table.add_column("Priority", style="yellow")
    table.add_column("Status", style="green")

    for r in reqs:
        table.add_row(r.id, r.ears_pattern.value, r.description, r.priority.value, r.status.value)
    console.print(table)


@app.command()
def question(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Run interactive adaptive questioning to resolve open Unknowns and reduce spec entropy.
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found. Run `defintra init <name>` first.[/red]")
        raise typer.Exit(1)

    engine = DiscoveryEngine(db)
    unknowns = db.get_unknowns(project.id, status_filter="OPEN")

    if not unknowns:
        console.print("[green]All unknowns for this project have been resolved![/green]")
        return

    console.print(f"[bold cyan]Adaptive Questioning Loop for '{project.name}'[/bold cyan]")
    console.print(f"[dim]{len(unknowns)} open unknowns remaining. Answer each or press enter to skip.[/dim]\n")

    for i, unk in enumerate(unknowns):
        console.print(
            Panel(
                f"[bold yellow]Question [{i+1}/{len(unknowns)}]:[/bold yellow] {unk.question}\n"
                f"[dim]Impact: {unk.impact} | Category: {unk.category}[/dim]",
                border_style="yellow",
            )
        )
        ans = typer.prompt("Your Answer (leave blank to skip)", default="", show_default=False)
        if ans.strip():
            report = engine.answer_unknown(project.id, unk.id, ans.strip())
            console.print(
                f"[green][OK] Recorded resolution.[/green] Updated Spec Health: [bold]{report.health_score}%[/bold] (Entropy: {round(report.entropy, 2)})\n"
            )

    console.print("[bold green]Questioning session completed![/bold green]")


@app.command(name="compile")
def compile_task(
    task: str = typer.Argument(..., help="The specific programming task to compile context for"),
    role: str = typer.Option("GENERAL", "--role", "-r", help="Agent role: GENERAL, BACKEND_ENGINEER, FRONTEND_ENGINEER, DATABASE_ENGINEER, SECURITY_ENGINEER, QA_ENGINEER"),
    target: str = typer.Option("markdown", "--target", "-t", help="Target format: claude, openai, gemini, antigravity, markdown, json"),
    tokens: int = typer.Option(4000, "--tokens", help="Maximum token budget"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Compile minimum sufficient context for AI coding agents with explainable inclusion/exclusion (§21).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    try:
        agent_role = AgentRole[role.upper()]
    except Exception:
        agent_role = AgentRole.GENERAL

    try:
        tgt_fmt = TargetFormat[target.upper()]
    except Exception:
        tgt_fmt = TargetFormat.MARKDOWN

    compiler = ContextCompiler(db)
    with console.status("[bold cyan]Compiling minimum sufficient context..."):
        compiled = compiler.compile(
            task_description=task,
            project_id=project.id,
            role=agent_role,
            max_tokens=tokens,
        )

    rendered_output = compiled.render(tgt_fmt)

    console.print(
        Panel(
            f"[bold]Target Format:[/bold] {tgt_fmt.value} | [bold]Role:[/bold] {agent_role.value}\n"
            f"[bold]Estimated Tokens:[/bold] {compiled.token_count} | [bold]Compression Ratio:[/bold] {compiled.compression_ratio:.1f}%\n"
            f"[bold]Included Requirements:[/bold] {len(compiled.requirements)} | [bold]Included Decisions:[/bold] {len(compiled.decisions)}",
            title="Context Compilation Metrics (§21, §23)",
            border_style="cyan",
        )
    )
    console.print(rendered_output)


@app.command()
def scan(
    repo_path: str = typer.Argument(".", help="Path to existing codebase directory to scan"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Project name for the scanned repository"),
):
    """
    Ingest an existing codebase into the Defintra knowledge graph (Brownfield Ingestion §1.5, §45).
    """
    db = get_db()
    scanner = BrownfieldScanner(db)

    with console.status(f"[bold cyan]Scanning codebase at '{repo_path}'..."):
        report = scanner.scan_repository(repo_path, project_name=name)

    console.print(
        Panel(
            f"[bold green]Repository Ingested Successfully![/bold green]\n"
            f"[bold]Project ID:[/bold] {report.project_id}\n"
            f"[bold]Files Scanned:[/bold] {report.files_scanned}\n"
            f"[bold]Detected Tech Stack:[/bold] {', '.join(report.detected_tech_stack) or 'Generic'}\n"
            f"[bold]Discovered Components:[/bold] {len(report.components_found)}\n"
            f"[bold]Discovered Contracts:[/bold] {len(report.contracts_found)}\n"
            f"[bold]Discovered Dependencies:[/bold] {report.dependencies_found}",
            title="Brownfield Ingestion Report",
            border_style="green",
        )
    )


@app.command()
def conflicts(
    detect: bool = typer.Option(True, "--detect/--no-detect", help="Run automated conflict detection"),
    resolve_id: Optional[str] = typer.Option(None, "--resolve", "-r", help="Conflict ID to resolve"),
    winner: Optional[str] = typer.Option(None, "--winner", "-w", help="Winning entity ID"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Resolution notes"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Detect and resolve contradictions between requirements, decisions, and constraints (§18).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    engine = ConflictEngine(db)

    if resolve_id:
        res_notes = notes or "Resolved by engineer via CLI"
        c = engine.resolve_conflict(project.id, resolve_id, res_notes, winner)
        console.print(f"[green][OK] Conflict '{c.id}' resolved![/green] Resolution: {res_notes}")
        return

    if detect:
        confs = engine.detect_conflicts(project.id)
    else:
        confs = db.get_conflicts(project.id)

    if not confs:
        console.print("[green]No active conflicts detected in the knowledge graph![/green]")
        return

    table = Table(title=f"Conflicts in '{project.name}' (§18)")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Severity", style="red")
    table.add_column("Title", style="white")
    table.add_column("Entities", style="dim")
    table.add_column("Status", style="yellow")

    for c in confs:
        table.add_row(c.id, c.severity, c.title, f"{c.entity_a_ref} vs {c.entity_b_ref}", c.status)

    console.print(table)


@app.command(name="test-pack")
def generate_test_pack(
    pack_type: str = typer.Option("human", "--type", "-t", help="Type of test pack: human, automated, security"),
    output_file: Optional[str] = typer.Option(None, "--out", "-o", help="Optional output filepath"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Generate structured Human Testing Packs, Automated test suites, or Security regression tests (§26, §27, §28).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    gen = TestPackGenerator(db)
    if pack_type.lower() == "automated":
        content = gen.generate_automated_test_scaffold(project.id)
    elif pack_type.lower() == "security":
        content = gen.generate_security_regression_suite(project.id)
    else:
        content = gen.generate_human_testing_pack(project.id)

    if output_file:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        console.print(f"[bold green]Test pack written to '{output_file}'[/bold green]")
    else:
        console.print(content)


@app.command()
def team(
    task: str = typer.Argument(..., help="Task description to dispatch to the AI team"),
    role: str = typer.Option("SOFTWARE_ARCHITECT", "--role", "-r", help="Assigned role (SOFTWARE_ARCHITECT, BACKEND_ENGINEER, FRONTEND_ENGINEER, SECURITY_ENGINEER, QA_ENGINEER)"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Coordinate and dispatch tasks across specialized AI team roles with model routing (§16, §17, §19).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    try:
        agent_role = AgentRole[role.upper()]
    except Exception:
        agent_role = AgentRole.SOFTWARE_ARCHITECT

    coordinator = TeamCoordinator(db)
    res = coordinator.dispatch_task(project.id, task, agent_role)

    routing = res["routing"]
    console.print(
        Panel(
            f"[bold]Dispatch ID:[/bold] {res['dispatch_id']}\n"
            f"[bold]Task:[/bold] {res['task']}\n"
            f"[bold]Assigned Role:[/bold] [cyan]{res['assigned_role']}[/cyan]\n"
            f"[bold]Recommended AI Model:[/bold] [green]{routing['recommended_model']}[/green]\n"
            f"[bold]Routing Rationale:[/bold] {routing['reason']}\n"
            f"[bold]Context Compiled:[/bold] {res['compiled_context_summary']['requirements_count']} requirements, {res['compiled_context_summary']['decisions_count']} decisions ({res['compiled_context_summary']['token_count']} tokens)",
            title="AI Team Collaboration Dispatch (§16, §17)",
            border_style="cyan",
        )
    )


@app.command()
def incident(
    error_text: str = typer.Argument(..., help="Error message, stack trace, or incident description"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Map production incident/stack trace back to originating requirements, contracts, and assumptions (§30).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    tracer = IncidentTracer(db)
    report = tracer.trace_incident(error_text, project.id)

    console.print(
        Panel(
            f"[bold]Incident Summary:[/bold] {error_text[:100]}...\n"
            f"[bold]Mapped Knowledge Graph Nodes:[/bold] {len(report.mapped_nodes)}\n"
            f"[bold]Potentially Refuted Assumptions:[/bold] {len(report.refuted_assumptions)}\n"
            f"[bold]Fix Blast Radius Risk:[/bold] [{'red' if report.blast_radius_risk in ['HIGH', 'CRITICAL'] else 'green'}]{report.blast_radius_risk}[/]",
            title="Production Incident Traceback (§30)",
            border_style="yellow",
        )
    )

    if report.mapped_nodes:
        table = Table(title="Originating Knowledge Graph Nodes")
        table.add_column("ID", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Title", style="white")
        table.add_column("Relevance", style="dim")
        for node in report.mapped_nodes:
            table.add_row(node["id"], node["type"], node["title"], node["relevance"])
        console.print(table)

    if report.recommended_regression_tests:
        console.print("\n[bold yellow]Recommended Regression Tests:[/bold yellow]")
        for test_case in report.recommended_regression_tests:
            console.print(f"  [dim]-[/dim] {test_case}")


@app.command()
def runbook(
    runbook_type: str = typer.Option("backup", "--type", "-t", help="Runbook type: backup, disaster_recovery, rollback, general"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Generate automated operations and maintenance runbooks (§31).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    gen = RunbookGenerator(db)
    content = gen.generate_runbook(project.id, runbook_type)
    console.print(content)


@app.command()
def stability(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Check Architecture Stability Budget, churn index, and modification velocity (§33).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    engine = StabilityBudgetEngine(db)
    rep = engine.evaluate_stability(project.id)

    color = "red" if rep.is_budget_exceeded else "green"
    console.print(
        Panel(
            f"[bold]Project:[/bold] {project.name}\n"
            f"[bold]Architecture Churn Index:[/bold] [{color}]{rep.churn_index:.3f}[/] / 1.0 (Threshold: 0.50)\n"
            f"[bold]Stability Score:[/bold] [{color}]{rep.stability_score:.1f}%[/]\n"
            f"[bold]Budget Exceeded:[/bold] [{color}]{'YES' if rep.is_budget_exceeded else 'NO'}[/]\n\n"
            f"- Decisions: {rep.metrics['approved_decisions']} approved, {rep.metrics['superseded_decisions']} superseded\n"
            f"- Components: {rep.metrics['implemented_components']} implemented of {rep.metrics['total_components']} total",
            title="Architecture Stability Budget (§33)",
            border_style=color,
        )
    )
    if rep.warnings:
        for w in rep.warnings:
            console.print(f"[bold red]WARNING:[/bold red] {w}")
    for r in rep.recommendations:
        console.print(f"[dim]-[/dim] {r}")


@app.command()
def diff(
    spec_a: str = typer.Argument(..., help="Path to base DIR JSON file or snapshot"),
    spec_b: str = typer.Argument(..., help="Path to modified DIR JSON file or snapshot"),
):
    """
    Semantic diff between two DIR specifications highlighting breaking contract changes (§49).
    """
    try:
        report = SpecDiffEngine.diff_from_files(spec_a, spec_b)
        console.print(report.render_markdown())
    except Exception as e:
        console.print(f"[red]Error performing diff: {e}[/red]")


@app.command()
def sandbox(
    action: str = typer.Argument("create", help="Sandbox action: create, validate"),
    task_id: str = typer.Option("task_001", "--task", help="Task ID for isolation branch"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Manage isolated staging sandboxes and pre-production governance gates (§25, §29).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    mgr = SandboxManager(db)
    if action == "create":
        sbx = mgr.create_sandbox(project.id, task_id)
        console.print(
            Panel(
                f"[bold green]Isolated Sandbox Created![/bold green]\n"
                f"[cyan]Sandbox ID:[/cyan] {sbx.sandbox_id}\n"
                f"[cyan]Branch:[/cyan] {sbx.branch_name}\n"
                f"[cyan]Snapshot Hash:[/cyan] {sbx.snapshot_hash}\n"
                f"[cyan]Status:[/cyan] {sbx.status}",
                title="Execution Sandbox (§25)",
                border_style="green",
            )
        )
    elif action == "validate":
        sbx = mgr.create_sandbox(project.id, task_id)
        gate = mgr.validate_governance_gate(project.id, sbx)
        console.print(
            Panel(
                f"[bold]Governance Status:[/bold] {gate['governance_status']}\n"
                f"[bold]Ready For Merge:[/bold] {gate['ready_for_merge']}\n"
                f"[bold]Checks:[/bold] {gate['checks']}",
                title="Pre-Production Governance Gate (§29)",
                border_style="green" if gate["ready_for_merge"] else "yellow",
            )
        )


@app.command()
def status(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Show comprehensive project health, entropy breakdown, decision ledger, and graph summary.
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found. Run `defintra init <name>` first.[/red]")
        raise typer.Exit(1)

    reqs = db.get_requirements(project.id)
    decs = db.get_decisions(project.id)
    asms = db.get_assumptions(project.id)
    unks = db.get_unknowns(project.id)
    comps = db.get_components(project.id)
    conflicts = db.get_conflicts(project.id)
    audit = db.get_audit_entries(project.id)

    report = EntropyCalculator.compute(reqs, decs, asms, unks, conflicts)

    # Health Meter Display
    color = "green" if report.health_score >= 80 else ("yellow" if report.health_score >= 50 else "red")
    console.print(
        Panel(
            f"[bold]Project:[/bold] {project.name} ([dim]{project.id}[/dim])\n"
            f"[bold]Domain:[/bold] {project.domain} | [bold]Source Type:[/bold] {project.source_type}\n\n"
            f"[bold]Spec Health Score:[/bold] [{color}]{report.health_score}%[/]\n"
            f"[bold]Spec Entropy:[/bold] {round(report.entropy, 3)} / 1.0\n\n"
            f"- Requirements: {len(reqs)} | - Components: {len(comps)} | - Decisions: {len(decs)}\n"
            f"- Assumptions: {len(asms)} | - Open Unknowns: {len([u for u in unks if u.status == 'OPEN'])} | - Active Conflicts: {len(conflicts)}\n"
            f"- Discovery Audit (Silent Assumptions): {len(audit)}",
            title="Defintra Spec Health & State",
            border_style=color,
        )
    )

    # Decisions with Preserved Disagreements
    if decs:
        dec_table = Table(title="Decision Ledger (with Preserved Disagreement)")
        dec_table.add_column("ID", style="cyan", no_wrap=True)
        dec_table.add_column("Decision", style="white")
        dec_table.add_column("Rejected Alternatives", style="dim")
        dec_table.add_column("Status", style="green")
        for d in decs:
            rej_str = ", ".join([f"{a.alternative} ({a.reason_rejected})" for a in d.rejected_alternatives]) or "None"
            dec_table.add_row(d.id, f"{d.title}: {d.decision}", rej_str, d.status.value)
        console.print(dec_table)

    if report.recommendations:
        console.print("\n[bold yellow]Spec Health Recommendations:[/bold yellow]")
        for rec in report.recommendations:
            console.print(f"  [dim]-[/dim] {rec}")


@app.command()
def graph(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
    format: str = typer.Option("ascii", "--format", "-f", help="Output format: ascii or mermaid"),
):
    """
    Render visual dependency and requirement graph.
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    p_graph = ProjectGraph(db, project.id)
    if format.lower() == "mermaid":
        console.print("```mermaid")
        console.print(p_graph.to_mermaid())
        console.print("```")
    else:
        console.print(f"[bold cyan]Knowledge & Dependency Graph for '{project.name}':[/bold cyan]")
        console.print(p_graph.to_ascii_tree())


@app.command(name="blast-radius")
def blast_radius(
    node_id: str = typer.Argument(..., help="ID of the requirement, decision, or component to simulate changes for"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Simulate a proposed change and calculate blast radius, affected nodes, risk level, and unaffected components.
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    p_graph = ProjectGraph(db, project.id)
    report = p_graph.calculate_blast_radius(node_id)

    color = "red" if report.risk_level.value in ["HIGH", "CRITICAL"] else "green"
    console.print(
        Panel(
            f"[bold]Target Node:[/bold] {node_id}\n"
            f"[bold]Total Blast Count:[/bold] {report.total_blast_count}\n"
            f"[bold]Risk Level:[/bold] [{color}]{report.risk_level.value}[/]\n"
            f"[bold]Required Approval:[/bold] {report.approval_required.value}\n\n"
            f"[bold]Explicitly Unaffected Components ({len(report.unaffected_components)}):[/bold]\n"
            f"[dim]{', '.join(report.unaffected_components) or 'None'}[/dim]",
            title=f"Impact Analysis & Blast Radius (§14)",
            border_style=color,
        )
    )

    if report.affected_nodes:
        table = Table(title="Directly & Indirectly Affected Nodes")
        table.add_column("ID", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Title", style="white")
        table.add_column("Status", style="yellow")
        for node in report.affected_nodes:
            table.add_row(node["id"], str(node["type"]), node["title"], node["status"])
        console.print(table)


@app.command()
def audit(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Display Discovery Audit Log of silent assumptions the system made without asking the user (§17).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    entries = db.get_audit_entries(project.id)
    if not entries:
        console.print("[dim]No silent assumptions logged for this project.[/dim]")
        return

    table = Table(title=f"Discovery Audit Log for '{project.name}' (§17)")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Silent Assumption", style="white")
    table.add_column("Reason Skipped", style="dim")
    table.add_column("Risk", style="yellow")

    for entry in entries:
        table.add_row(entry.id, entry.silent_assumption, entry.reason_skipped, entry.risk_level.value)

    console.print(table)


@app.command(name="export")
def export_spec(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
    output_dir: str = typer.Option(".defintra/export", "--out", "-o", help="Output directory"),
    rules: Optional[str] = typer.Option(None, "--rules", "-r", help="Directly export agent rule file: cursor (.cursorrules), claude (CLAUDE.md), or agents (AGENTS.md)"),
):
    """
    Export dual-track outputs: DIR JSON Schema v1 payload + Human-readable Markdown spec + Agent rules (§22).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    exporter = Exporter(db, project.id)
    if rules:
        target_path = exporter.export_agent_rules(rules)
        console.print(f"[bold green]Agent rule file written to '{target_path}'[/bold green]")
        return

    with console.status("[bold cyan]Exporting DIR JSON, Markdown, and Agent rule specifications..."):
        written = exporter.export_all(output_dir)

    console.print(f"[bold green]Export completed to '{output_dir}':[/bold green]")
    for fname, fpath in written.items():
        console.print(f"  [cyan][OK][/cyan] {fname} -> [dim]{fpath}[/dim]")


@app.command()
def staleness(
    revalidate_id: Optional[str] = typer.Option(None, "--revalidate", "-r", help="Node ID to re-validate and restore full confidence"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Check confidence decay and detect stale requirements, decisions, and assumptions (§9).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    engine = StalenessEngine(db)
    if revalidate_id:
        success = engine.revalidate_node(project.id, revalidate_id)
        if success:
            console.print(f"[bold green]Node '{revalidate_id}' successfully re-validated! Confidence restored.[/bold green]")
        else:
            console.print(f"[bold red]Node '{revalidate_id}' not found.[/bold red]")
            raise typer.Exit(1)
        return

    rep = engine.evaluate_staleness(project.id)
    color = "green" if rep.system_staleness_score <= 0.20 else ("yellow" if rep.system_staleness_score <= 0.50 else "red")

    console.print(
        Panel(
            f"[bold]Project:[/bold] {project.name}\n"
            f"[bold]Total Nodes Checked:[/bold] {rep.total_nodes_checked}\n"
            f"[bold]Average Confidence:[/bold] {rep.average_confidence:.2f} / 1.0\n"
            f"[bold]System Staleness Score:[/bold] [{color}]{rep.system_staleness_score:.2f}[/]\n"
            f"[bold]Stale Nodes Surfaced:[/bold] [{color}]{len(rep.stale_nodes)}[/]",
            title="Confidence Decay & Staleness Report (§9)",
            border_style=color,
        )
    )

    if rep.stale_nodes:
        table = Table(title="Stale / Decayed Knowledge Graph Nodes")
        table.add_column("Node ID", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta")
        table.add_column("Original", style="white")
        table.add_column("Decayed", style="yellow")
        table.add_column("Staleness Reason", style="dim")
        for s in rep.stale_nodes:
            table.add_row(s.node_id, s.node_type, f"{s.original_confidence:.2f}", f"{s.decayed_confidence:.2f}", s.staleness_reason)
        console.print(table)
        console.print("\n[dim]Tip: Run `defintra staleness --revalidate <NODE_ID>` to verify and restore confidence.[/dim]")


@app.command()
def advise(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Generate post-deployment continuous improvement and optimization recommendations (§32).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    advisor = PostDeploymentAdvisor(db)
    suggestions = advisor.generate_recommendations(project.id)

    console.print(f"[bold cyan]Post-Deployment Continuous Improvement Advisory for '{project.name}' (§32):[/bold cyan]\n")

    for s in suggestions:
        risk_color = "red" if s.change_risk.value in ["HIGH", "CRITICAL"] else ("yellow" if s.change_risk.value == "MEDIUM" else "green")
        steps_text = "\n".join([f"  [cyan]{i+1}.[/cyan] {step}" for i, step in enumerate(s.action_plan)])
        console.print(
            Panel(
                f"[bold white]{s.title}[/bold white]  [dim](Category: {s.category} | ROI Score: {s.roi_score}/10)[/dim]\n\n"
                f"[bold]Expected Benefit:[/bold] {s.expected_benefit}\n"
                f"[bold]Change Risk:[/bold] [{risk_color}]{s.change_risk.value}[/] | [bold]Estimated Effort:[/bold] {s.estimated_effort}\n\n"
                f"[bold]Action Plan:[/bold]\n{steps_text}",
                title=f"[{s.id}] {s.category}",
                border_style="cyan",
            )
        )


@app.command()
def recover(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Diagnose systemic failure modes and generate self-healing recovery actions (§48).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    recovery_engine = FailureRecoveryEngine(db)
    report = recovery_engine.diagnose_project(project.id)

    color = "green" if report.system_health_status == "HEALTHY" else ("yellow" if report.system_health_status == "DEGRADED" else "red")
    console.print(
        Panel(
            f"[bold]Project:[/bold] {project.name}\n"
            f"[bold]System Diagnostic Status:[/bold] [{color}]{report.system_health_status}[/]\n"
            f"[bold]Active Failure Modes Detected:[/bold] [{color}]{len(report.diagnoses)}[/]",
            title="System Failure Diagnosis & Recovery Engine (§48)",
            border_style=color,
        )
    )

    if not report.diagnoses:
        console.print("[bold green]Zero systemic failure modes detected. Project architecture is fully aligned![/bold green]")
        return

    for d in report.diagnoses:
        steps = "\n".join([f"  [yellow]→[/yellow] {step}" for step in d.remediation_steps])
        console.print(
            Panel(
                f"[bold red]{d.title}[/bold red]  [dim]({d.failure_type} | Severity: {d.severity})[/dim]\n\n"
                f"[bold]Impact:[/bold] {d.impact_summary}\n"
                f"[bold]Root Cause Nodes:[/bold] {', '.join(d.root_cause_nodes)}\n\n"
                f"[bold]Structured Recovery Plan:[/bold]\n{steps}\n"
                + (f"\n[bold green]Auto-Fix Command:[/bold green] `{d.auto_fix_command}`" if d.auto_fix_command else ""),
                title=f"[{d.failure_id}] {d.severity}",
                border_style="red" if d.severity == "CRITICAL" else "yellow",
            )
        )


@app.command()
def adr(
    decision_id: Optional[str] = typer.Option(None, "--id", "-i", help="Specific decision ID to generate ADR for"),
    output_dir: str = typer.Option("docs/adr", "--out", "-o", help="Output directory for ADR Markdown files"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Generate formal Architecture Decision Records (ADRs) with multi-dimensional trade-off matrices (§10, §11).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    from defintra.core.decisions.adr import ADRGenerator
    gen = ADRGenerator(db)

    if decision_id:
        content = gen.generate_adr(project.id, decision_id)
        console.print(Panel(content, title=f"ADR: {decision_id}", border_style="cyan"))
        return

    written = gen.export_all_adrs(project.id, output_dir)
    console.print(f"[bold green]Exported {len(written)} Architecture Decision Records to '{output_dir}':[/bold green]")
    for did, fpath in written.items():
        console.print(f"  [cyan][OK][/cyan] {did} -> [dim]{fpath}[/dim]")


@app.command()
def schedule(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Generate implementation roadmap, critical path, and parallel AI agent execution tracks (§13, §16).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    from defintra.core.tasks.scheduler import TaskScheduler
    scheduler = TaskScheduler(db)
    sched = scheduler.schedule_project(project.id)

    console.print(
        Panel(
            f"[bold]Project:[/bold] {project.name}\n"
            f"[bold]Total Execution Phases:[/bold] {sched.total_phases}\n"
            f"[bold]Parallelism Factor:[/bold] {sched.parallelism_factor} concurrent agent tracks\n"
            f"[bold]Critical Path:[/bold] {' → '.join(sched.critical_path)}",
            title="Multi-Agent Implementation Roadmap & Scheduler (§13, §16)",
            border_style="cyan",
        )
    )

    for p in sched.phases:
        tracks_text = "\n".join([f"  [cyan]•[/cyan] {t}" for t in p.parallel_tracks])
        console.print(
            Panel(
                f"[bold white]Phase {p.phase_number}: {p.name}[/bold white]\n"
                f"[bold]Assigned AI Role:[/bold] [magenta]{p.assigned_role.value}[/magenta]\n"
                f"[bold]Primary Focal Entities:[/bold] {', '.join(p.primary_entities)}\n\n"
                f"[bold]Parallel Execution Tracks:[/bold]\n{tracks_text}\n\n"
                f"[bold green]Gate Requirement:[/bold green] {p.gate_condition}",
                title=f"Phase {p.phase_number}",
                border_style="blue",
            )
        )


@app.command()
def contracts(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Inspect and validate semantic version compatibility across API, Database, and UI contracts (§12, §49).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    from defintra.core.contracts.versioning import ContractVersioningEngine
    v_engine = ContractVersioningEngine(db)
    results = v_engine.validate_project_contracts(project.id)

    table = Table(title="Shared Component Contracts & Semantic Versions (§12, §49)")
    table.add_column("Contract ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Type", style="magenta")
    table.add_column("SemVer", style="green")
    table.add_column("Status", style="yellow")

    for c in results:
        table.add_row(c["contract_id"], c["name"], c["type"], c["version"], c["status"])

    console.print(table)


@app.command(name="ui")
def launch_ui(
    port: int = typer.Option(8765, "--port", "-p", help="Port to run web dashboard on"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open browser automatically"),
):
    """
    Launch the interactive Defintra Control Center & Web Dashboard in your browser (§5, §7, §21).
    """
    console.print(
        Panel.fit(
            f"[bold cyan]Defintra Control Center[/bold cyan]\n"
            f"[green]Dashboard URL:[/green] [link=http://127.0.0.1:{port}]http://127.0.0.1:{port}[/link]\n"
            f"[dim]Press Ctrl+C to stop the dashboard server.[/dim]",
            title="Web Control Center",
            border_style="cyan",
        )
    )
    start_ui_server(port=port, open_browser=not no_browser)


@app.command(name="dashboard")
def launch_dashboard(
    port: int = typer.Option(8765, "--port", "-p", help="Port to run web dashboard on"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open browser automatically"),
):
    """
    Alias for `defintra ui`.
    """
    launch_ui(port=port, no_browser=no_browser)


if __name__ == "__main__":
    app()
