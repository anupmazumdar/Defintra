import pytest
from typer.testing import CliRunner

from defintra.cli.main import app
from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine

runner = CliRunner()


def test_database_delete_and_purge(tmp_path):
    db_file = tmp_path / "test_purge.db"
    db = Database(str(db_file))

    engine = DiscoveryEngine(db)
    p1 = engine.run_fast_path("Project Alpha", "Build e-commerce store")
    p2 = engine.run_fast_path("Project Beta", "Build analytics pipeline")

    projects = db.list_projects()
    assert len(projects) == 2

    # Cascade delete p1
    deleted = db.delete_project(p1.id)
    assert deleted is True
    assert db.get_project(p1.id) is None
    # Verify cascade deleted requirements
    assert len(db.get_requirements(p1.id)) == 0

    # p2 remains
    assert db.get_project(p2.id) is not None
    assert len(db.get_requirements(p2.id)) >= 1

    # Purge all
    purged_count = db.purge_all()
    assert purged_count == 1
    assert len(db.list_projects()) == 0


def test_cli_purge_command(tmp_path, monkeypatch):
    db_file = tmp_path / "cli_purge.db"
    monkeypatch.setattr("defintra.cli.main.get_db", lambda: Database(str(db_file)))

    db = Database(str(db_file))
    engine = DiscoveryEngine(db)
    p = engine.run_fast_path("Purge Target", "Build mobile client")

    # Purge single project
    res = runner.invoke(app, ["purge", "--project", p.id, "--force"])
    assert res.exit_code == 0
    assert "Successfully purged project" in res.stdout
    assert db.get_project(p.id) is None

    # Recreate and test purge all
    p2 = engine.run_fast_path("Purge All Target", "Build web client")
    res_all = runner.invoke(app, ["purge", "--all", "--force"])
    assert res_all.exit_code == 0
    assert "Successfully purged all projects" in res_all.stdout
    assert len(db.list_projects()) == 0
