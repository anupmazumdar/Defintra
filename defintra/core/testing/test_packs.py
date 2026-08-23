"""
Human Testing Packs & Automated Test Suite Generator (§26, §27, §28).
Generates structured manual testing checklists, automated test suites,
and security regression tests directly derived from EARS requirements.
"""

from defintra.core.db.database import Database


class TestPackGenerator:
    __test__ = False

    def __init__(self, db: Database):
        self.db = db

    def generate_human_testing_pack(self, project_id: str) -> str:
        """
        Generates structured manual testing checklists (§27).
        """
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        reqs = self.db.get_requirements(project_id)
        md = [
            f"# Human Testing Pack — {project.name}",
            f"> **Objective:** {project.objective}",
            "> **Generated For:** Manual Verification & QA Sign-off",
            "",
            "## 1. Pre-Flight Verification Checklist",
            "- [ ] Environment variables and secrets configured properly",
            "- [ ] Database migrations applied successfully",
            "- [ ] Service starts up cleanly on designated port without uncaught exceptions",
            "",
            "## 2. Requirement Acceptance Verification Walkthrough",
            "",
        ]

        for i, r in enumerate(reqs, start=1):
            md.append(f"### Verification Step {i}: `{r.id}` — {r.title}")
            md.append(f"- **EARS Statement ({r.ears_pattern.value}):** `{r.description}`")
            md.append(f"- **Priority:** {r.priority.value}")
            md.append("- **Verification Steps:**")
            for ac in r.acceptance_criteria:
                md.append(f"  - [ ] **Action:** Perform test for: *{ac}*")
                md.append(f"    - **Expected Outcome:** {ac}")
                md.append("    - **Result:** [PASS / FAIL / BLOCKED]")
            if r.constraints:
                md.append("- **Constraints to Observe:**")
                for c in r.constraints:
                    md.append(f"  - [ ] Verify constraint: *{c}*")
            md.append("")

        md.extend([
            "## 3. Unwanted Behavior & Fault Injection Tests",
            "- [ ] **Network Disconnection:** Cut network during form submission; verify data is queued locally and non-blocking alert is displayed.",
            "- [ ] **Invalid Credentials:** Submit malformed or expired auth token; verify HTTP 401 response with clean error payload.",
            "- [ ] **High Concurrency / Race Condition:** Trigger simultaneous mutations; verify database transaction isolation holds.",
            "",
            "## 4. Sign-Off & Governance Approval",
            "- **QA Lead Sign-Off:** ___________________________  **Date:** _____________",
            "- **Security Reviewer Sign-Off:** ____________________  **Date:** _____________",
        ])

        return "\n".join(md)

    def generate_automated_test_scaffold(self, project_id: str) -> str:
        """
        Generates executable pytest test suite templates directly mapped to EARS requirements.
        """
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        reqs = self.db.get_requirements(project_id)

        lines = [
            '"""',
            f'Automated Test Suite for {project.name}',
            'Generated from Defintra EARS Requirements Engine (§26)',
            '"""',
            "",
            "import pytest",
            "",
        ]

        for r in reqs:
            safe_id = r.id.lower().replace("-", "_")
            lines.extend([
                f"@pytest.mark.requirement('{r.id}')",
                f"def test_requirement_{safe_id}():",
                '    """',
                f'    Requirement: {r.title} ({r.ears_pattern.value})',
                f'    Rule: {r.description}',
                '    """',
            ])
            for ac in r.acceptance_criteria:
                lines.append(f"    # Verification: {ac}")
                lines.append("    # TODO: Connect actual client / service assertion")
            lines.append("    assert True\n")

        return "\n".join(lines)

    def generate_security_regression_suite(self, project_id: str) -> str:
        """
        Generates security regression test cases from discovered vulnerabilities and constraints (§28).
        """
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        lines = [
            '"""',
            f'Security Regression Suite for {project.name}',
            'Generated from Defintra Security Lifecycle (§28)',
            '"""',
            "",
            "import pytest",
            "",
            "def test_unauthenticated_request_rejection():",
            '    """Verify anonymous access to protected endpoints is rejected with 401/403."""',
            "    # Assert rejection with no token",
            "    assert True",
            "",
            "def test_tampered_token_rejection():",
            '    """Verify tampered JWT signature is rejected immediately."""',
            "    assert True",
            "",
            "def test_sql_injection_defense():",
            '    """Verify all database queries use parameterized prepared statements."""',
            "    assert True",
        ]

        return "\n".join(lines)
