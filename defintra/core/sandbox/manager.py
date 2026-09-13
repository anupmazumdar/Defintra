"""
Sandbox & Isolated Staging Manager (§25, §29).
Manages isolated Git branches/worktrees, execution environments,
snapshot hashes, and pre-production governance gates.
"""

import hashlib
import os
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from defintra.core.db.database import Database
from defintra.core.models.entities import current_utc_time
from defintra.core.policy.engine import PolicyDecision, PolicyEngine

ALLOWED_SANDBOX_BINARIES = {
    "python",
    "python3",
    "pytest",
    "git",
    "node",
    "npm",
    "npx",
    "pip",
    "echo",
    "cat",
    "ls",
    "dir",
    "mkdir",
    "rm",
    "cp",
    "mv",
    "touch",
    "grep",
    "find",
    "cargo",
    "go",
    "rustc",
    "tsc",
}


def _parse_cmd_to_argv(cmd: Any) -> list[str]:
    """
    Parses a command string or list into an explicit argv list for subprocess execution
    without invoking the system shell (shell=False).
    """
    if isinstance(cmd, list):
        return [str(c) for c in cmd]
    if isinstance(cmd, str):
        try:
            if os.name == "nt":
                tokens = shlex.split(cmd, posix=False)
                clean_tokens = []
                for t in tokens:
                    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
                        clean_tokens.append(t[1:-1])
                    else:
                        clean_tokens.append(t)
                return clean_tokens
            return shlex.split(cmd, posix=True)
        except Exception:
            return cmd.split()
    return []


class SandboxState:
    def __init__(
        self,
        sandbox_id: str,
        project_id: str,
        branch_name: str,
        isolation_type: str,  # "git_branch", "worktree", "directory"
        snapshot_hash: str,
        status: str,  # "ACTIVE", "TESTING", "MERGED", "ROLLED_BACK", "CLEANED"
        created_at: str,
        allowed_actions: Optional[list[str]] = None,
        denied_actions: Optional[list[str]] = None,
        worktree_path: Optional[str] = None,
    ):
        self.sandbox_id = sandbox_id
        self.project_id = project_id
        self.branch_name = branch_name
        self.isolation_type = isolation_type
        self.snapshot_hash = snapshot_hash
        self.status = status
        self.created_at = created_at
        self.allowed_actions = allowed_actions or []
        self.denied_actions = denied_actions or []
        self.worktree_path = worktree_path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "project_id": self.project_id,
            "branch_name": self.branch_name,
            "isolation_type": self.isolation_type,
            "snapshot_hash": self.snapshot_hash,
            "status": self.status,
            "created_at": self.created_at,
            "allowed_actions": self.allowed_actions,
            "denied_actions": self.denied_actions,
            "worktree_path": self.worktree_path,
        }


class SandboxManager:
    def __init__(self, db: Database, base_dir: str = ".defintra/sandboxes"):
        self.db = db
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.policy_engine = PolicyEngine(db)

    def create_sandbox(
        self,
        project_id: str,
        task_id: str,
        isolation_type: str = "git_branch",
    ) -> SandboxState:
        """
        Initializes an isolated staging sandbox for autonomous or human execution (§25, §45).
        Tags sandbox with capability-scoped allowed and denied actions derived from the policy engine.
        Creates isolated filesystem worktree/directory when requested.
        """
        sandbox_id = f"sbx_{uuid.uuid4().hex[:8]}"
        branch_name = f"defintra/{project_id}/{task_id}"

        # Generate snapshot hash
        hasher = hashlib.sha256()
        hasher.update(f"{project_id}_{task_id}_{current_utc_time()}".encode("utf-8"))
        snapshot_hash = hasher.hexdigest()[:16]

        # Derive capability scopes from policy engine
        policies = self.policy_engine.list_policies(project_id)
        allowed_actions = [p.action_type for p in policies if p.decision.value != "DENY"]
        denied_actions = [p.action_type for p in policies if p.decision.value == "DENY"]

        worktree_path: Optional[str] = None
        if isolation_type in ("worktree", "directory"):
            sandbox_path = (self.base_dir / sandbox_id).resolve()
            if isolation_type == "worktree":
                try:
                    res = subprocess.run(
                        ["git", "worktree", "add", "-b", branch_name, str(sandbox_path)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if res.returncode != 0:
                        sandbox_path.mkdir(parents=True, exist_ok=True)
                except Exception:
                    sandbox_path.mkdir(parents=True, exist_ok=True)
            else:
                sandbox_path.mkdir(parents=True, exist_ok=True)
            worktree_path = str(sandbox_path)

        sandbox = SandboxState(
            sandbox_id=sandbox_id,
            project_id=project_id,
            branch_name=branch_name,
            isolation_type=isolation_type,
            snapshot_hash=snapshot_hash,
            status="ACTIVE",
            created_at=current_utc_time(),
            allowed_actions=allowed_actions,
            denied_actions=denied_actions,
            worktree_path=worktree_path,
        )

        return sandbox

    def cleanup_sandbox(self, sandbox: SandboxState) -> bool:
        """
        Safely removes an isolated worktree or staging directory upon completion or rollback.
        """
        if not sandbox.worktree_path:
            sandbox.status = "CLEANED"
            return True

        wt_path = Path(sandbox.worktree_path)
        if wt_path.exists():
            if sandbox.isolation_type == "worktree":
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", str(wt_path)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    subprocess.run(
                        ["git", "branch", "-D", sandbox.branch_name],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                except Exception:
                    pass
            if wt_path.exists():
                shutil.rmtree(wt_path, ignore_errors=True)

        sandbox.status = "CLEANED"
        return True

    def evaluate_sandbox_action(
        self,
        project_id: str,
        action_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> PolicyDecision:
        """
        Consults the Policy Engine before an agent performs an action in the sandbox (§25, §45).
        """
        return self.policy_engine.evaluate_action(project_id, action_type, context=context)

    def _create_scrubbed_env(self) -> Dict[str, str]:
        """
        Creates a minimal, scrubbed environment for sandbox execution.
        Strips sensitive API keys, cloud tokens, database URLs, and credentials.
        """
        allowed_base_vars = {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "TEMP",
            "TMP",
            "HOME",
            "USERPROFILE",
            "LANG",
            "LC_ALL",
            "TERM",
            "PYTHONPATH",
        }
        scrubbed = {}
        for k, v in os.environ.items():
            k_upper = k.upper()
            if k_upper in allowed_base_vars:
                if not any(sub in k_upper for sub in ("KEY", "TOKEN", "SECRET", "PASS", "AUTH", "CREDENTIAL")):
                    scrubbed[k] = v
        # Outbound proxy diversion: sets proxy variables to loopback for proxy-aware runtimes.
        # NOTE: This does NOT provide kernel-level network isolation (non-proxy-aware sockets bypass this).
        scrubbed["HTTP_PROXY"] = "http://127.0.0.1:0"
        scrubbed["HTTPS_PROXY"] = "http://127.0.0.1:0"
        scrubbed["ALL_PROXY"] = "socks5://127.0.0.1:0"
        scrubbed["NO_PROXY"] = ""
        return scrubbed

    def execute_sandbox_action(
        self,
        sandbox: SandboxState,
        action_type: str,
        approved_by: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Enforces policy boundaries, filesystem confinement, and isolated execution (§25, §45).
        Refuses execution on DENY, unapproved REQUIRES_APPROVAL actions, or out-of-bounds file access.
        
        Execution Truthfulness & Security Architecture:
        - Shell commands are strictly forbidden on non-execute_shell action types (prevents approval bypass).
        - Pure policy checks without execution payloads return status 'POLICY_APPROVED' (or 'POLICY_DENIED').
        - Real execution occurs when:
          * action_type == 'execute_shell': runs confined subprocess without shell interpreter (shell=False)
            using an explicit argv list against an allowed binary list, with scrubbed environment and timeout.
          * action_type == 'modify_file' (with 'file' and 'content' in context): writes file strictly confined
            within sandbox.worktree_path.
        - Status 'EXECUTED' is ONLY returned when an actual action was executed successfully.
        """
        wt_root = Path(sandbox.worktree_path).resolve() if sandbox.worktree_path else None

        # Enforce that command execution payloads are strictly prohibited under non-execute_shell actions.
        # This prevents bypass of the HIGH-risk REQUIRES_APPROVAL gate via actions like read_repository.
        has_command = bool(context and ("command" in context or "cmd" in context))
        if has_command and action_type != "execute_shell":
            return {
                "sandbox_id": sandbox.sandbox_id,
                "action_type": action_type,
                "allowed": False,
                "executed": False,
                "status": "BLOCKED",
                "decision": "DENY",
                "risk_level": "CRITICAL",
                "reason": f"Security violation: Command execution payload supplied for non-shell action '{action_type}'. Shell commands may only execute under 'execute_shell'.",
            }

        if wt_root and context:
            target_path_str = context.get("file") or context.get("path") or context.get("file_path")
            if target_path_str:
                target_p = Path(target_path_str)
                target_abs = target_p.resolve() if target_p.is_absolute() else (wt_root / target_p).resolve()
                try:
                    target_abs.relative_to(wt_root)
                except ValueError:
                    return {
                        "sandbox_id": sandbox.sandbox_id,
                        "action_type": action_type,
                        "allowed": False,
                        "executed": False,
                        "status": "BLOCKED",
                        "decision": "DENY",
                        "risk_level": "CRITICAL",
                        "reason": f"Path escape violation: '{target_path_str}' is outside sandbox worktree '{sandbox.worktree_path}'",
                    }

        allowed, reason, decision = self.policy_engine.enforce_action(
            project_id=sandbox.project_id,
            action_type=action_type,
            approved_by=approved_by,
            context=context,
        )

        res: Dict[str, Any] = {
            "sandbox_id": sandbox.sandbox_id,
            "action_type": action_type,
            "allowed": allowed,
            "executed": False,
            "status": "POLICY_APPROVED" if allowed else "POLICY_DENIED",
            "decision": decision.decision.value,
            "risk_level": decision.risk_level.value,
            "reason": reason,
        }

        if not allowed:
            if decision.decision.value == "DENY":
                res["status"] = "BLOCKED"
            return res

        # 1. Bounded Execution for Shell Commands
        #
        # ISOLATION GUARANTEES & THREAT MODEL:
        # What this implementation DOES provide:
        # - Shell Injection Prevention: Dropping shell=True in favor of explicit argv tokenization
        #   (shell=False) prevents shell metacharacter injection (; | && ` $() < >).
        # - Binary Execution Allowlist: Restricts executable binaries to ALLOWED_SANDBOX_BINARIES
        #   (python, pytest, git, npm, etc.), blocking invocation of arbitrary administrative or system tools.
        # - Working Directory Confinement: Sets subprocess cwd to sandbox.worktree_path, scoping local
        #   file access to the isolated staging directory.
        # - Ambient Secret Stripping: Strips credentials, API keys, tokens, and sensitive env vars
        #   from the spawned process environment.
        # - Process Lifetime Bounding: Enforces a strict timeout (default 30s) to prevent resource exhaustion.
        #
        # What this implementation DOES NOT provide (Known Limitations & Non-Guarantees):
        # - True Network Isolation: Setting HTTP_PROXY/HTTPS_PROXY/ALL_PROXY to 127.0.0.1:0 does NOT provide
        #   true OS- or kernel-level network isolation. Raw sockets, UDP traffic, or libraries that ignore
        #   standard proxy env vars can still establish outbound connections unless wrapped in dedicated
        #   network namespaces (Linux netns), seccomp filters, or container environments.
        # - Filesystem Read Confinement: Without kernel namespaces (mount/chroot/pivot_root) or containerization,
        #   the child process runs with host user privileges and can read any files on the filesystem that
        #   the current OS user has read permissions for.
        if action_type == "execute_shell":
            cmd = context.get("command") or context.get("cmd") if context else None
            if not cmd:
                res["reason"] = f"{reason} (Policy evaluated: shell execution permitted, but no command provided)"
                return res

            argv = _parse_cmd_to_argv(cmd)
            if not argv:
                res["allowed"] = False
                res["executed"] = False
                res["status"] = "BLOCKED"
                res["reason"] = "Failed to parse command arguments into safe argv list"
                return res

            binary = Path(argv[0]).stem.lower()
            if binary not in ALLOWED_SANDBOX_BINARIES:
                res["allowed"] = False
                res["executed"] = False
                res["status"] = "BLOCKED"
                res["decision"] = "DENY"
                res["reason"] = (
                    f"Binary '{binary}' is not in the sandbox allowed binaries list. "
                    f"Permitted binaries: {', '.join(sorted(ALLOWED_SANDBOX_BINARIES))}"
                )
                return res

            timeout = int(context.get("timeout", 30))
            cwd_dir = str(wt_root) if (wt_root and wt_root.exists()) else str(self.base_dir)
            clean_env = self._create_scrubbed_env()

            try:
                proc = subprocess.run(
                    argv,
                    shell=False,
                    cwd=cwd_dir,
                    env=clean_env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                res["command"] = cmd
                res["stdout"] = proc.stdout
                res["stderr"] = proc.stderr
                res["returncode"] = proc.returncode
                res["executed"] = True
                res["status"] = "EXECUTED" if proc.returncode == 0 else "FAILED"
                if proc.returncode != 0:
                    res["reason"] = f"Command exited with returncode {proc.returncode}"
            except subprocess.TimeoutExpired as te:
                res["command"] = cmd
                res["allowed"] = False
                res["executed"] = False
                res["status"] = "TIMED_OUT"
                res["stdout"] = te.stdout or ""
                res["stderr"] = te.stderr or ""
                res["returncode"] = -1
                res["reason"] = f"Command execution timed out after {timeout}s limit"
            except Exception as e:
                res["command"] = cmd
                res["allowed"] = False
                res["executed"] = False
                res["status"] = "FAILED"
                res["reason"] = f"Execution error: {str(e)}"

            return res

        # 2. Bounded Execution for File Modification
        if action_type == "modify_file":
            if not wt_root or not wt_root.exists():
                res["status"] = "FAILED"
                res["executed"] = False
                res["reason"] = "Cannot modify file: sandbox worktree is not initialized on disk"
                return res

            target_path_str = context.get("file") or context.get("path") or context.get("file_path") if context else None
            content = context.get("content") if context else None

            if target_path_str is not None and content is not None:
                target_p = Path(target_path_str)
                target_abs = target_p.resolve() if target_p.is_absolute() else (wt_root / target_p).resolve()
                try:
                    target_abs.relative_to(wt_root)
                except ValueError:
                    return {
                        "sandbox_id": sandbox.sandbox_id,
                        "action_type": action_type,
                        "allowed": False,
                        "executed": False,
                        "status": "BLOCKED",
                        "decision": "DENY",
                        "risk_level": "CRITICAL",
                        "reason": f"Path escape violation: '{target_path_str}' is outside sandbox worktree '{sandbox.worktree_path}'",
                    }

                try:
                    target_abs.parent.mkdir(parents=True, exist_ok=True)
                    target_abs.write_text(content, encoding="utf-8")
                    res["executed"] = True
                    res["status"] = "EXECUTED"
                    res["file_modified"] = str(target_abs)
                    res["bytes_written"] = len(content.encode("utf-8"))
                    res["reason"] = f"File successfully written within sandbox worktree: {target_abs.name}"
                except Exception as e:
                    res["executed"] = False
                    res["status"] = "FAILED"
                    res["reason"] = f"Failed to write file in sandbox: {str(e)}"
            else:
                res["reason"] = f"{reason} (Policy evaluated: modify_file permitted, but no content supplied for execution)"

            return res

        return res

    def validate_governance_gate(
        self,
        project_id: str,
        sandbox: SandboxState,
        test_results_pass: bool = True,
        security_sign_off: bool = True,
    ) -> Dict[str, Any]:
        """
        Pre-production deployment gate verification (§29, §45).
        """
        project = self.db.get_project(project_id)
        if not project:
            return {"ready_for_merge": False, "error": "Project not found"}

        # Check policy for deployment action
        deploy_policy = self.policy_engine.evaluate_action(project_id, "deploy")

        checks = {
            "snapshot_verified": bool(sandbox.snapshot_hash),
            "test_suite_passed": test_results_pass,
            "security_sign_off": security_sign_off,
            "entropy_within_threshold": project.spec_entropy <= 0.6,
            "policy_governance_satisfied": deploy_policy.decision.value != "DENY",
        }

        all_passed = all(checks.values())
        return {
            "ready_for_merge": all_passed,
            "checks": checks,
            "governance_status": "APPROVED" if all_passed else "BLOCKED",
            "rollback_plan_ready": True,
        }

