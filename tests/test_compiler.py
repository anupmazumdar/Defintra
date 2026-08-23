import pytest
from defintra.context.compiler import AgentRole, ContextCompiler, TargetFormat
from defintra.context.optimizer import TokenEstimator, TokenOptimizer
from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_compiler.db"
    return Database(str(db_file))


def test_token_estimator_and_optimizer():
    sample_text = "This is a sample technical requirement statement that shall be validated."
    tokens = TokenEstimator.estimate_tokens(sample_text)
    assert tokens > 5

    items = ["PostgreSQL required", "postgresql required", "  PostgreSQL Required  ", "Redis Cache"]
    deduped = TokenOptimizer.deduplicate_strings(items)
    assert len(deduped) == 2

    candidates = [
        {"content": "High priority requirement A", "priority_score": 0.9},
        {"content": "Medium priority requirement B", "priority_score": 0.5},
        {"content": "Low priority requirement C", "priority_score": 0.1},
    ]
    included, excluded, used = TokenOptimizer.fit_to_budget(candidates, max_tokens=15)
    assert len(included) >= 1
    assert len(excluded) >= 1


def test_context_compiler_rendering(test_db):
    engine = DiscoveryEngine(test_db)
    project = engine.run_fast_path("Attendance App", "Build college attendance app with QR scan and PostgreSQL")

    compiler = ContextCompiler(test_db)
    compiled = compiler.compile(
        task_description="Build JWT login endpoint and database connection",
        project_id=project.id,
        role=AgentRole.BACKEND_ENGINEER,
    )

    assert len(compiled.requirements) > 0
    assert len(compiled.decisions) > 0
    assert compiled.token_count > 0

    # Test Claude XML format
    claude_xml = compiled.render(TargetFormat.CLAUDE)
    assert "<defintra_context>" in claude_xml
    assert "<locked_decisions>" in claude_xml

    # Test OpenAI/Markdown format
    openai_md = compiled.render(TargetFormat.OPENAI)
    assert "# Defintra Task Context:" in openai_md
    assert "## 2. Mandatory Architectural Decisions (LOCKED)" in openai_md

    # Test JSON format
    json_out = compiled.render(TargetFormat.JSON)
    assert '"role": "BACKEND_ENGINEER"' in json_out
