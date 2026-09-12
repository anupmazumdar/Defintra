"""
Defintra CLI (§38, §46 V0–V7).
Interactive command-line interface for Requirement Intelligence, EARS specs,
Decision Ledger, Context Compilation, Brownfield Ingestion, Conflict Engine,
Testing Packs, Sandboxing, AI Team Orchestration, Incident Feedback, Runbooks,
Architecture Stability Budget, and Semantic Spec Diffing.
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from defintra.context.compiler import AgentRole, ContextCompiler, TargetFormat
from defintra.core.brownfield.scanner import BrownfieldScanner
from defintra.core.conflicts.engine import ConflictEngine
from defintra.core.db.database import Database
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
from defintra.core.team.coordinator import TeamCoordinator
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
    except KeyError:
        agent_role = AgentRole.GENERAL

    try:
        tgt_fmt = TargetFormat[target.upper()]
    except KeyError:
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
    allow_external: bool = typer.Option(False, "--allow-external", help="Allow scanning outside workspace root"),
):
    """
    Ingest an existing codebase into the Defintra knowledge graph (Brownfield Ingestion §1.5, §45).
    """
    target = Path(repo_path).resolve()
    if not target.exists() or not target.is_dir():
        console.print(f"[bold red]Error: Target repository path '{repo_path}' is not an existing directory.[/bold red]")
        raise typer.Exit(1)

    workspace_root = Path(".").resolve()
    if not allow_external:
        try:
            target.relative_to(workspace_root)
        except ValueError:
            console.print(
                f"[bold red]Security Error: Path traversal rejected. '{repo_path}' resolves outside current workspace.[/bold red]\n"
                "[dim]Use --allow-external if you intended to scan an external directory.[/dim]"
            )
            raise typer.Exit(1)

    db = get_db()
    scanner = BrownfieldScanner(db)

    with console.status(f"[bold cyan]Scanning codebase at '{target}'..."):
        report = scanner.scan_repository(str(target), project_name=name)

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
    task: str = typer.Argument(..., help="Task description or goal for AI agent role"),
    role: str = typer.Option("SOFTWARE_ARCHITECT", "--role", "-r", help="Target agent role (BACKEND_ENGINEER, FRONTEND_ENGINEER, SOFTWARE_ARCHITECT, SECURITY_ENGINEER, QA_ENGINEER)"),
    complexity: str = typer.Option("MEDIUM", "--complexity", "-c", help="Task complexity: LOW, MEDIUM, HIGH, CRITICAL"),
    execute: bool = typer.Option(True, "--execute/--no-execute", help="Execute task with routed AI provider and Adaptive Execution loop (§16, §20)"),
    approved_by: Optional[str] = typer.Option(None, "--approved-by", help="Explicit human authorization if action requires governance approval (§45)"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Coordinate and dispatch tasks across specialized AI team roles with model routing (§16, §17, §19, §20).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    try:
        agent_role = AgentRole[role.upper()]
    except KeyError:
        agent_role = AgentRole.SOFTWARE_ARCHITECT

    coordinator = TeamCoordinator(db)
    res = coordinator.dispatch_task(
        project_id=project.id,
        task_title=task,
        role=agent_role,
        task_complexity=complexity,
        execute=execute,
        approved_by=approved_by,
    )

    routing = res["routing"]
    exec_snippet = res.get("execution_output", "")[:400]
    
    if res.get("status") == "BLOCKED_BY_POLICY":
        pe = res.get("policy_enforcement", {})
        console.print(
            Panel(
                f"[bold red]EXECUTION REFUSED BY POLICY ENGINE (§45)[/bold red]\n\n"
                f"[bold]Inferred Action:[/bold] {pe.get('action')}\n"
                f"[bold]Governance Decision:[/bold] [bold red]{pe.get('decision')}[/bold red] (Risk: {pe.get('risk_level')})\n"
                f"[bold]Rationale:[/bold] {pe.get('reason')}\n\n"
                f"[dim]If authorized, provide explicit authorization using `--approved-by <name>`.[/dim]",
                title="Policy Governance Gate",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    provider_desc = res.get("provider", "None")
    if res.get("is_mock"):
        provider_desc = f"{provider_desc} [yellow](Heuristic Mock / Offline Engine)[/yellow]"
    else:
        provider_desc = f"[green]{provider_desc}[/green] (Model: {routing['recommended_model']})"

    attempts_info = ""
    if res.get("attempts_log") and len(res["attempts_log"]) > 1:
        attempts_info = f"\n[bold]Adaptive Execution Attempts:[/bold] {len(res['attempts_log'])} (Diagnostic retry/fallback triggered)"

    console.print(
        Panel(
            f"[bold]Dispatch ID:[/bold] {res['dispatch_id']}\n"
            f"[bold]Task:[/bold] {res['task']}\n"
            f"[bold]Assigned Role:[/bold] [cyan]{res['assigned_role']}[/cyan]\n"
            f"[bold]AI Execution Engine:[/bold] {provider_desc}\n"
            f"[bold]Routing Rationale:[/bold] {routing['reason']}\n"
            f"[bold]Context Compiled:[/bold] {res['compiled_context_summary']['requirements_count']} requirements, {res['compiled_context_summary']['decisions_count']} decisions ({res['compiled_context_summary']['token_count']} tokens){attempts_info}\n\n"
            f"[bold]Agent Execution Response Snippet:[/bold]\n[dim]{exec_snippet}...[/dim]",
            title="AI Team Collaboration & Task Execution (§16, §17)",
            border_style="cyan",
        )
    )


@app.command()
def events(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Display the chronological immutable stream of multi-agent structured coordination events (§17, §34).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    coordinator = TeamCoordinator(db)
    evts = coordinator.get_events(project.id)

    if not evts:
        console.print("[yellow]No team events recorded yet. Run `defintra team <task>` to dispatch agent tasks.[/yellow]")
        return

    table = Table(title="Multi-Agent Structured Coordination Event Log (§17, §34)")
    table.add_column("Event ID", style="cyan")
    table.add_column("Event Type", style="green")
    table.add_column("Actor Role", style="magenta")
    table.add_column("Summary", style="white")
    table.add_column("Timestamp", style="dim")

    for e in evts:
        table.add_row(e["id"], e["event_type"], e["actor_role"], e["summary"], e["created_at"][:19])

    console.print(table)


@app.command()
def route(
    role: str = typer.Argument("SOFTWARE_ARCHITECT", help="Target agent role (e.g. BACKEND_ENGINEER, SECURITY_ENGINEER)"),
    complexity: str = typer.Option("MEDIUM", "--complexity", "-c", help="Task complexity tier (LOW, MEDIUM, HIGH, CRITICAL)"),
):
    """
    Inspect optimal AI model routing recommendations, context window tiers, and cost estimates (§19).
    """
    db = get_db()
    coordinator = TeamCoordinator(db)
    try:
        agent_role = AgentRole[role.upper()]
    except KeyError:
        agent_role = AgentRole.SOFTWARE_ARCHITECT

    routing = coordinator.route_model(agent_role, task_complexity=complexity.upper())
    console.print(
        Panel(
            f"[bold]Target Role:[/bold] [cyan]{agent_role.value}[/cyan]\n"
            f"[bold]Task Complexity:[/bold] [yellow]{complexity.upper()}[/yellow]\n"
            f"[bold]Recommended AI Model:[/bold] [bold green]{routing.recommended_model}[/bold green]\n"
            f"[bold]Context Window Tier:[/bold] {routing.context_window_tier}\n"
            f"[bold]Estimated Cost Tier:[/bold] {routing.estimated_cost_tier}\n"
            f"[bold]Selection Rationale:[/bold] {routing.reason}",
            title="AI Model Routing Recommendation (§19)",
            border_style="green",
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
            title="Impact Analysis & Blast Radius (§14)",
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


@app.command()
def snapshot(
    create_tag: Optional[str] = typer.Option(None, "--create", "-c", help="Create a new immutable snapshot with version tag (e.g. v1.0.0)"),
    restore_id: Optional[str] = typer.Option(None, "--restore", "-r", help="Restore project state from a snapshot ID"),
    description: str = typer.Option("Release checkpoint", "--desc", "-d", help="Description for snapshot"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Manage cryptographic SHA-256 project snapshots, release tags, and rollbacks (§29, §49).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    from defintra.core.governance.snapshot import SnapshotManager
    mgr = SnapshotManager(db)

    if create_tag:
        snap = mgr.create_snapshot(project.id, version_tag=create_tag, description=description)
        console.print(
            Panel(
                f"[bold]Snapshot ID:[/bold] {snap.snapshot_id}\n"
                f"[bold]Version Tag:[/bold] {snap.version_tag}\n"
                f"[bold]SHA-256 Checksum:[/bold] [dim]{snap.checksum}[/dim]\n"
                f"[bold]Description:[/bold] {snap.description}",
                title="Cryptographic Snapshot Created (§49)",
                border_style="green",
            )
        )
        return

    if restore_id:
        success = mgr.restore_snapshot(restore_id)
        if success:
            console.print(f"[bold green]Successfully restored project state from snapshot '{restore_id}'![/bold green]")
        else:
            console.print(f"[bold red]Snapshot '{restore_id}' not found.[/bold red]")
            raise typer.Exit(1)
        return

    snapshots = mgr.list_snapshots(project.id)
    if not snapshots:
        console.print("[yellow]No snapshots recorded yet. Run `defintra snapshot --create v1.0.0` to save a release tag.[/yellow]")
        return

    table = Table(title="Immutable Project Snapshots & Release Lineage (§49)")
    table.add_column("Snapshot ID", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Checksum (SHA-256)", style="dim")
    table.add_column("Description", style="white")
    table.add_column("Date", style="magenta")

    for s in snapshots:
        table.add_row(s["snapshot_id"], s["version_tag"], s["checksum"][:16] + "...", s["description"], s["created_at"][:19])

    console.print(table)


@app.command()
def metrics(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Monitor production operational metrics, SLO compliance, and component health (§30).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    from defintra.core.operations.metrics import ProductionMetricsTracker
    tracker = ProductionMetricsTracker(db)
    rep = tracker.evaluate_production_health(project.id)

    color = "green" if rep.overall_status == "HEALTHY" else ("yellow" if rep.overall_status == "DEGRADED" else "red")
    console.print(
        Panel(
            f"[bold]Project:[/bold] {project.name}\n"
            f"[bold]Operational Health Status:[/bold] [{color}]{rep.overall_status}[/]\n"
            f"[bold]Overall SLO Compliance Rate:[/bold] [{color}]{rep.slo_compliance_rate}%[/]",
            title="Production Metrics & SLO Performance (§30)",
            border_style=color,
        )
    )

    table = Table(title="Production Service Level Objectives (SLOs)")
    table.add_column("SLO Metric", style="cyan")
    table.add_column("Current", style="white")
    table.add_column("Target", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Focal Component", style="dim")

    for m in rep.metrics:
        status_tag = "[green]COMPLIANT[/green]" if m.is_compliant else "[red]BREACHED[/red]"
        table.add_row(m.name, f"{m.current_value}{m.unit}", f"{m.target_value}{m.unit}", status_tag, m.affected_component)

    console.print(table)


@app.command()
def gate(
    task_id: str = typer.Option("production_release", "--task", "-t", help="Task ID to gate"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Evaluate pre-production deployment governance gates and release readiness (§29).
    Exits with code 0 if ready for merge/deploy, or code 1 if blocked.
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    from defintra.core.sandbox.manager import SandboxManager
    sbx = SandboxManager(db)
    sandbox = sbx.create_sandbox(project.id, task_id=task_id)
    res = sbx.validate_governance_gate(project.id, sandbox)

    color = "green" if res["ready_for_merge"] else "yellow"
    console.print(
        Panel(
            f"[bold]Project:[/bold] {project.name}\n"
            f"[bold]Pre-Production Release Gate:[/bold] [{color}]{'APPROVED / READY' if res['ready_for_merge'] else 'ACTION REQUIRED'}[/]\n\n"
            + "\n".join([f"  {'[green][PASS][/green]' if v else '[red][FAIL][/red]'} {k}" for k, v in res["checks"].items()]),
            title="Pre-Production Deployment Governance Gate (§29)",
            border_style=color,
        )
    )

    if not res["ready_for_merge"]:
        console.print("[bold red]Release blocked by governance policies. Resolve failing checks before merge.[/bold red]")
        raise typer.Exit(1)
    else:
        console.print("[bold green]All pre-production criteria satisfied! Safe to merge and deploy.[/bold green]")


policy_app = typer.Typer(help="Autonomous agent governance and action policy engine (§45)")
app.add_typer(policy_app, name="policy")

sandbox_app = typer.Typer(help="Sandbox and staging execution environment manager (§25)")
app.add_typer(sandbox_app, name="sandbox")


@policy_app.command(name="check")
def policy_check(
    action: str = typer.Argument(..., help="Action type to evaluate (e.g. read_repository, modify_file, execute_shell, deploy, access_secret)"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Evaluate an action request against the governance policy engine (§45).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    p_id = project.id if project else "default"

    from defintra.core.policy.engine import PolicyEngine
    pe = PolicyEngine(db)
    decision = pe.evaluate_action(p_id, action)

    color = "green" if decision.decision.value == "ALLOW" else ("red" if decision.decision.value == "DENY" else "yellow")
    console.print(
        Panel(
            f"[bold]Action Type:[/bold] {decision.action_type}\n"
            f"[bold]Governance Decision:[/bold] [{color}]{decision.decision.value}[/]\n"
            f"[bold]Risk Level:[/bold] {decision.risk_level.value}\n"
            f"[bold]Required Approval:[/bold] {decision.required_approval.value}\n"
            f"[bold]Rationale:[/bold] {decision.reason}",
            title="Agent Governance Policy Evaluation (§45)",
            border_style=color,
        )
    )


@policy_app.command(name="list")
def policy_list(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    List all configured governance policies and action permissions (§45).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    p_id = project.id if project else None

    from defintra.core.policy.engine import PolicyEngine
    pe = PolicyEngine(db)
    policies = pe.list_policies(p_id)

    table = Table(title="Autonomous Agent Governance & Action Policy Table (§45)")
    table.add_column("Action Type", style="cyan", no_wrap=True)
    table.add_column("Decision", style="bold")
    table.add_column("Risk Level", style="magenta")
    table.add_column("Required Approval", style="yellow")
    table.add_column("Description", style="white")

    for p in policies:
        color = "green" if p.decision.value == "ALLOW" else ("red" if p.decision.value == "DENY" else "yellow")
        table.add_row(
            p.action_type,
            f"[{color}]{p.decision.value}[/]",
            p.risk_level.value,
            p.required_approval.value,
            p.description,
        )

    console.print(table)


@sandbox_app.command(name="create")
def sandbox_create(
    task: str = typer.Option("task_execution", "--task", "-t", help="Task ID to sandbox"),
    isolation: str = typer.Option("git_branch", "--type", help="Isolation type (git_branch, worktree, directory)"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Create an isolated staging sandbox for a risky agent implementation (§25).
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    from defintra.core.sandbox.manager import SandboxManager
    sbx = SandboxManager(db)
    res = sbx.create_sandbox(project.id, task_id=task, isolation_type=isolation)
    console.print(
        Panel(
            f"[bold]Sandbox ID:[/bold] {res.sandbox_id}\n"
            f"[bold]Project:[/bold] {project.name}\n"
            f"[bold]Branch:[/bold] [cyan]{res.branch_name}[/cyan]\n"
            f"[bold]Isolation:[/bold] {res.isolation_type}\n"
            f"[bold]Snapshot Hash:[/bold] [dim]{res.snapshot_hash}[/dim]\n"
            f"[bold]Allowed Actions:[/bold] {len(res.allowed_actions)} actions permitted\n"
            f"[bold]Status:[/bold] [green]{res.status}[/green]",
            title="Isolated Sandbox Created (§25)",
            border_style="green",
        )
    )


@sandbox_app.command(name="exec")
def sandbox_exec(
    action: str = typer.Argument(..., help="Action to execute inside sandbox (e.g. read_repository, modify_file, execute_shell, deploy)"),
    command: Optional[str] = typer.Option(None, "--command", "-c", help="Shell command to execute inside sandbox worktree (for execute_shell)"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Target file path inside sandbox worktree (for modify_file)"),
    content: Optional[str] = typer.Option(None, "--content", help="File content to write inside sandbox worktree (for modify_file)"),
    timeout: int = typer.Option(30, "--timeout", help="Subprocess execution timeout in seconds"),
    task: str = typer.Option("task_execution", "--task", "-t", help="Task ID"),
    approved_by: Optional[str] = typer.Option(None, "--approved-by", help="Authorization name if action requires governance approval (§45)"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Execute a bounded, governed action inside an isolated staging sandbox (§25, §45).
    Runs bounded shell commands or modifies files strictly confined to the sandbox worktree.
    When invoked without execution payloads, evaluates policy authorization only.
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    from defintra.core.sandbox.manager import SandboxManager
    sbx = SandboxManager(db)
    sandbox = sbx.create_sandbox(project.id, task_id=task)

    context = {}
    if command:
        context["command"] = command
    if file:
        context["file"] = file
    if content:
        context["content"] = content
    if timeout:
        context["timeout"] = timeout

    res = sbx.execute_sandbox_action(
        sandbox,
        action_type=action,
        approved_by=approved_by,
        context=context or None,
    )

    if not res["allowed"]:
        console.print(
            Panel(
                f"[bold red]SANDBOX ACTION REFUSED BY POLICY ENGINE[/bold red]\n\n"
                f"[bold]Action:[/bold] {action}\n"
                f"[bold]Decision:[/bold] [bold red]{res['decision']}[/bold red] (Risk: {res['risk_level']})\n"
                f"[bold]Rationale:[/bold] {res['reason']}",
                title="Policy Violation (§45)",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    if res.get("status") == "EXECUTED":
        details = [
            f"[bold]Sandbox ID:[/bold] {sandbox.sandbox_id}",
            f"[bold]Action:[/bold] {action}",
            "[bold]Execution Status:[/bold] [bold green]EXECUTED[/bold green]",
            f"[bold]Rationale:[/bold] {res['reason']}",
        ]
        if "stdout" in res and res["stdout"]:
            details.append(f"\n[bold]Output (stdout):[/bold]\n{res['stdout']}")
        if "stderr" in res and res["stderr"]:
            details.append(f"\n[bold yellow]Stderr:[/bold yellow]\n{res['stderr']}")
        if "file_modified" in res:
            details.append(f"\n[bold]Modified File:[/bold] {res['file_modified']} ({res.get('bytes_written', 0)} bytes written)")

        console.print(
            Panel(
                "\n".join(details),
                title="Sandbox Action Executed (§25, §45)",
                border_style="green",
            )
        )
    else:
        status_color = "green" if res.get("status") == "POLICY_APPROVED" else "yellow"
        console.print(
            Panel(
                f"[bold]Sandbox ID:[/bold] {sandbox.sandbox_id}\n"
                f"[bold]Action:[/bold] {action}\n"
                f"[bold]Policy Status:[/bold] [{status_color}]{res['status']}[/{status_color}] (Evaluation only — no execution performed)\n"
                f"[bold]Decision:[/bold] {res['decision']} (Risk: {res['risk_level']})\n"
                f"[bold]Rationale:[/bold] {res['reason']}",
                title="Sandbox Policy Evaluation (§25, §45)",
                border_style="blue",
            )
        )


@sandbox_app.command(name="authorize")
def sandbox_authorize(
    action: str = typer.Argument(..., help="Action to evaluate against Policy Engine (e.g. read_repository, modify_file, execute_shell, deploy)"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Target file path to verify filesystem confinement"),
    approved_by: Optional[str] = typer.Option(None, "--approved-by", help="Authorization name if action requires approval (§45)"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID"),
):
    """
    Evaluate policy boundaries without performing any execution (§25, §45).
    Evaluates whether an action is allowed or denied under the governance policy.
    NOTE: This command evaluates policy only and performs no execution.
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    from defintra.core.sandbox.manager import SandboxManager
    sbx = SandboxManager(db)
    sandbox = sbx.create_sandbox(project.id, task_id="policy_authorization")
    context = {"file": file} if file else None
    res = sbx.execute_sandbox_action(sandbox, action_type=action, approved_by=approved_by, context=context)

    if not res["allowed"]:
        console.print(
            Panel(
                f"[bold red]SANDBOX ACTION DISALLOWED BY POLICY[/bold red]\n\n"
                f"[bold]Action:[/bold] {action}\n"
                f"[bold]Status:[/bold] [bold red]{res['status']}[/bold red]\n"
                f"[bold]Decision:[/bold] [bold red]{res['decision']}[/bold red] (Risk: {res['risk_level']})\n"
                f"[bold]Rationale:[/bold] {res['reason']}\n\n"
                f"[dim]Note: defintra sandbox authorize evaluates policy only; no action was executed.[/dim]",
                title="Policy Evaluation: DENIED (§45)",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    console.print(
        Panel(
            f"[bold]Sandbox ID:[/bold] {sandbox.sandbox_id}\n"
            f"[bold]Action:[/bold] {action}\n"
            f"[bold]Status:[/bold] [bold green]{res['status']}[/bold green]\n"
            f"[bold]Decision:[/bold] [bold green]{res['decision']}[/bold green] (Risk: {res['risk_level']})\n"
            f"[bold]Rationale:[/bold] {res['reason']}\n\n"
            f"[dim]Note: defintra sandbox authorize evaluates policy only; no action was executed.[/dim]",
            title="Policy Evaluation: APPROVED (§45)",
            border_style="green",
        )
    )


benchmark_app = typer.Typer(help="Empirical benchmark harness comparing Defintra vs naive prompting (§40, §46)")
app.add_typer(benchmark_app, name="benchmark")


@benchmark_app.command(name="run")
def benchmark_run(
    input_file: str = typer.Option(..., "--input", "-i", help="Idea text or path to PRD / requirements text file"),
    name: str = typer.Option("Benchmark Evaluation", "--name", "-n", help="Project name for benchmark"),
):
    """
    Run empirical comparative benchmark: Defintra structured pipeline vs naive prompt baseline (§40).
    """
    db = get_db()
    from defintra.core.benchmark.runner import BenchmarkRunner
    runner = BenchmarkRunner(db)
    res = runner.run_benchmark(input_text_or_path=input_file, project_name=name)

    table = Table(title="Empirical Intelligence Benchmark Comparison (§40, §46 V0)")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Defintra Structured Graph", style="bold green")
    table.add_column("Naive Prompt Baseline", style="yellow")
    table.add_column("Comparative Advantage", style="magenta")

    table.add_row(
        "Requirements Coverage",
        f"{res.defintra_req_count} typed EARS requirements",
        f"{res.naive_req_count} unstructured points",
        f"+{max(0, res.defintra_req_count - res.naive_req_count)} structured specs",
    )
    table.add_row(
        "Spec Health Score",
        f"{res.defintra_health_score}/100",
        "N/A (Unmeasured)",
        "Quantified Quality",
    )
    table.add_row(
        "Spec Ambiguity (Entropy)",
        f"{res.defintra_entropy} (0.0=Perfect)",
        "N/A (High Entropy)",
        "Grounded Knowledge",
    )
    table.add_row(
        "Compiled Context Size",
        f"{res.defintra_token_count} tokens",
        f"{res.naive_token_count} tokens",
        f"{round(res.defintra_token_count / max(res.naive_token_count, 1), 1)}x Density",
    )
    table.add_row(
        "Processing Latency",
        f"{res.defintra_duration_ms} ms",
        f"{res.naive_duration_ms} ms",
        "Local-First Speed",
    )

    console.print(table)
    console.print(
        Panel(
            f"[bold]Summary:[/bold] {res.comparison_summary}",
            title=f"Benchmark Run [{res.benchmark_id}]",
            border_style="green",
        )
    )


@benchmark_app.command(name="history")
def benchmark_history(
    limit: int = typer.Option(10, "--limit", "-l", help="Number of benchmark runs to display"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project ID"),
):
    """
    Display historical benchmark comparisons and trends over time (§40).
    """
    db = get_db()
    from defintra.core.benchmark.runner import BenchmarkRunner
    runner = BenchmarkRunner(db)
    history = runner.get_history(project_id=project_id, limit=limit)

    if not history:
        console.print("[yellow]No benchmark history found. Run `defintra benchmark run --input <file>` first.[/yellow]")
        return

    table = Table(title="Benchmark Historical Trends (§40, §46)")
    table.add_column("Run ID", style="cyan")
    table.add_column("Input Preview", style="white")
    table.add_column("Defintra Reqs", style="green")
    table.add_column("Naive Reqs", style="yellow")
    table.add_column("Health", style="bold")
    table.add_column("Tokens", style="magenta")
    table.add_column("Recorded At", style="dim")

    for h in history:
        table.add_row(
            h.benchmark_id,
            h.input_summary[:35] + "...",
            str(h.defintra_req_count),
            str(h.naive_req_count),
            f"{h.defintra_health_score}%",
            f"{h.defintra_token_count}",
            h.created_at[:19],
        )

    console.print(table)



@app.command(name="ui")
def launch_ui(
    port: int = typer.Option(8765, "--port", "-p", help="Port to run web dashboard on"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open browser automatically"),
    token: Optional[str] = typer.Option(None, "--token", help="Optional session token for authentication"),
    revoke: bool = typer.Option(False, "--revoke", help="Revoke active session token on running dashboard server"),
):
    """
    Launch the interactive Defintra Control Center & Web Dashboard in your browser (§5, §7, §21).
    """
    if revoke:
        import urllib.request
        if not token:
            console.print("[red]Error: You must supply the token to revoke using --token <token>[/red]")
            raise typer.Exit(1)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/token/revoke",
            headers={"Authorization": f"Bearer {token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    console.print(f"[bold green]Session token successfully revoked on port {port}.[/bold green]")
                    raise typer.Exit(0)
        except Exception as e:
            console.print(f"[bold red]Failed to revoke token on port {port}: {e}[/bold red]")
            raise typer.Exit(1)

    import secrets
    auth_token = token or secrets.token_urlsafe(24)
    auth_url = f"http://127.0.0.1:{port}/?token={auth_token}"
    console.print(
        Panel.fit(
            f"[bold cyan]Defintra Control Center[/bold cyan]\n"
            f"[green]Authenticated URL:[/green] [link={auth_url}]{auth_url}[/link]\n"
            f"[cyan]Session Token:[/cyan] [bold]{auth_token}[/bold]\n"
            f"[dim]Press Ctrl+C to stop the dashboard server.[/dim]",
            title="Web Control Center",
            border_style="cyan",
        )
    )
    start_ui_server(port=port, open_browser=not no_browser, auth_token=auth_token)


@app.command(name="dashboard")
def launch_dashboard(
    port: int = typer.Option(8765, "--port", "-p", help="Port to run web dashboard on"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open browser automatically"),
    token: Optional[str] = typer.Option(None, "--token", help="Optional session token for authentication"),
    revoke: bool = typer.Option(False, "--revoke", help="Revoke active session token on running dashboard server"),
):
    """
    Alias for `defintra ui`.
    """
    launch_ui(port=port, no_browser=no_browser, token=token, revoke=revoke)


@app.command(name="mcp")
def run_mcp_server(
    db_path: str = typer.Option(".defintra/project.db", "--db", help="Path to Defintra SQLite database"),
):
    """
    Launch the Defintra Model Context Protocol (MCP) server over stdio (§44).
    """
    from defintra.mcp.server import handle_stdio_rpc
    handle_stdio_rpc()


@app.command(name="purge")
def purge_data(
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Target project ID to purge"),
    all_projects: bool = typer.Option(False, "--all", "-a", help="Purge all project data and exports"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """
    Purge project data from knowledge graph and workspace exports (right-to-erasure / privacy purge).
    """
    import shutil
    db = get_db()

    if not project_id and not all_projects:
        console.print("[yellow]Please specify --project <id> or --all to purge data.[/yellow]")
        raise typer.Exit(1)

    if not force:
        target = "ALL project records and exports" if all_projects else f"project '{project_id}'"
        confirm = typer.confirm(f"Are you sure you want to permanently delete {target}?")
        if not confirm:
            console.print("[dim]Operation cancelled.[/dim]")
            return

    if all_projects:
        count = db.purge_all()
        export_dir = Path(".defintra/export")
        if export_dir.exists():
            shutil.rmtree(export_dir, ignore_errors=True)
        console.print(f"[bold green]Successfully purged all projects ({count} deleted) and cleaned .defintra/export/.[/bold green]")
    else:
        project = db.get_project(project_id)
        if not project:
            console.print(f"[red]Project '{project_id}' not found.[/red]")
            raise typer.Exit(1)
        db.delete_project(project_id)
        console.print(f"[bold green]Successfully purged project '{project_id}' and all cascaded knowledge graph entities.[/bold green]")


if __name__ == "__main__":
    app()

