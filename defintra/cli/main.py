"""
Defintra CLI (§38, §46 V0).
Interactive command-line interface for Requirement Intelligence, EARS specs,
Decision Ledger, Spec Health tracking, and DIR export.
"""

from pathlib import Path
from typing import Optional
import typer
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.tree import Tree

from defintra.core.audit.logger import DiscoveryAuditLogger
from defintra.core.db.database import Database
from defintra.core.decisions.ledger import DecisionLedger
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.entropy.calculator import EntropyCalculator
from defintra.core.graph.engine import ProjectGraph
from defintra.export.exporter import Exporter

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
):
    """
    Export dual-track outputs: DIR JSON Schema v1 payload + Human-readable Markdown spec.
    """
    db = get_db()
    project = db.get_project(project_id) if project_id else db.get_first_project()
    if not project:
        console.print("[red]No active project found.[/red]")
        raise typer.Exit(1)

    exporter = Exporter(db, project.id)
    with console.status("[bold cyan]Exporting DIR JSON and Markdown specifications..."):
        written = exporter.export_all(output_dir)

    console.print(f"[bold green]Export completed to '{output_dir}':[/bold green]")
    for fname, fpath in written.items():
        console.print(f"  [cyan][OK][/cyan] {fname} -> [dim]{fpath}[/dim]")


if __name__ == "__main__":
    app()
