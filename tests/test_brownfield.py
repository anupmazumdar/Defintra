import pytest
from pathlib import Path
from defintra.core.brownfield.scanner import BrownfieldScanner
from defintra.core.db.database import Database


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_brownfield.db"
    return Database(str(db_file))


def test_brownfield_scanner(test_db, tmp_path):
    # Setup mock repository files
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()

    server_file = repo_dir / "server.py"
    server_file.write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/api/v1/students")
def get_students():
    return []

@app.post("/api/v1/attendance")
def submit_attendance():
    return {"status": "ok"}
""", encoding="utf-8")

    model_file = repo_dir / "models.py"
    model_file.write_text("""
class StudentModel(Base):
    id = Column(Integer, primary_key=True)

class AttendanceModel(Base):
    id = Column(Integer, primary_key=True)
""", encoding="utf-8")

    scanner = BrownfieldScanner(test_db)
    report = scanner.scan_repository(str(repo_dir), project_name="Mock Student API")

    assert report.files_scanned >= 2
    assert "Python" in report.detected_tech_stack
    assert len(report.components_found) >= 2
    assert len(report.contracts_found) >= 1

    # Verify saved in db
    project = test_db.get_project(report.project_id)
    assert project is not None
    assert project.source_type == "repo"
