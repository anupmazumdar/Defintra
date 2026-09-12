import pytest

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

    # Verify contracts contain endpoints and tables
    contracts = test_db.get_contracts(report.project_id)
    endpoints = []
    tables = []
    for c in contracts:
        if c.contract_type == "API":
            endpoints.extend(c.specification.get("endpoints", []))
        elif c.contract_type == "DATABASE":
            tables.extend(c.specification.get("tables", []))

    assert "GET /api/v1/students" in endpoints
    assert "POST /api/v1/attendance" in endpoints
    assert "StudentModel" in tables or "AttendanceModel" in tables


def test_brownfield_python_ast_parser_direct():
    code = """
from fastapi import APIRouter
router = APIRouter()

@router.get(
    "/api/v2/analytics",
    tags=["analytics"],
    summary="Retrieve analytics dashboard metrics"
)
async def get_analytics():
    return {"metrics": []}

@router.api_route("/api/v2/webhook", methods=["POST", "PUT"])
def webhook_handler():
    return {"received": True}

class CourseEntity(Base):
    __tablename__ = "courses_table"
    id = Column(Integer, primary_key=True)

class AccountModel(models.Model):
    name = models.CharField(max_length=100)
"""
    endpoints, tables = BrownfieldScanner._parse_python_ast(code)

    assert "GET /api/v2/analytics" in endpoints
    assert "POST /api/v2/webhook" in endpoints
    assert "PUT /api/v2/webhook" in endpoints
    assert "courses_table" in tables
    assert "AccountModel" in tables


def test_brownfield_python_ast_syntax_error_handling():
    # Malformed Python code does not crash the parser
    bad_code = "def incomplete_function(:"
    endpoints, tables = BrownfieldScanner._parse_python_ast(bad_code)
    assert endpoints == []
    assert tables == []

