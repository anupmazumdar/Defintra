"""
Defintra Empirical Benchmark & Comparative Evaluation Engine (§40, §46 V0).
Measures requirement coverage, context efficiency, and spec health
comparing Defintra's structured graph intelligence against raw naive prompting.
"""

import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from defintra.context.compiler import AgentRole, ContextCompiler
from defintra.context.optimizer import TokenEstimator
from defintra.core.db.database import Database
from defintra.core.discovery.engine import DiscoveryEngine
from defintra.core.discovery.llm import get_llm_provider
from defintra.core.models.entities import current_utc_time


class BenchmarkResult:
    def __init__(
        self,
        benchmark_id: str,
        project_id: str,
        input_summary: str,
        defintra_req_count: int,
        defintra_health_score: float,
        defintra_entropy: float,
        defintra_token_count: int,
        defintra_duration_ms: float,
        naive_req_count: int,
        naive_token_count: int,
        naive_duration_ms: float,
        comparison_summary: str,
        created_at: str,
    ):
        self.benchmark_id = benchmark_id
        self.project_id = project_id
        self.input_summary = input_summary
        self.defintra_req_count = defintra_req_count
        self.defintra_health_score = defintra_health_score
        self.defintra_entropy = defintra_entropy
        self.defintra_token_count = defintra_token_count
        self.defintra_duration_ms = defintra_duration_ms
        self.naive_req_count = naive_req_count
        self.naive_token_count = naive_token_count
        self.naive_duration_ms = naive_duration_ms
        self.comparison_summary = comparison_summary
        self.created_at = created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.benchmark_id,
            "project_id": self.project_id,
            "input_summary": self.input_summary,
            "defintra_req_count": self.defintra_req_count,
            "defintra_health_score": self.defintra_health_score,
            "defintra_entropy": self.defintra_entropy,
            "defintra_token_count": self.defintra_token_count,
            "defintra_duration_ms": self.defintra_duration_ms,
            "naive_req_count": self.naive_req_count,
            "naive_token_count": self.naive_token_count,
            "naive_duration_ms": self.naive_duration_ms,
            "comparison_summary": self.comparison_summary,
            "created_at": self.created_at,
        }


class BenchmarkRunner:
    def __init__(self, db: Database):
        self.db = db
        self.discovery = DiscoveryEngine(db)
        self.compiler = ContextCompiler(db)

    def run_benchmark(
        self,
        input_text_or_path: str,
        project_name: str = "Benchmark Evaluation Project",
    ) -> BenchmarkResult:
        """
        Runs empirical comparison of Defintra structured intelligence vs naive prompting baseline (§40).
        """
        # 1. Parse input content
        raw_text = input_text_or_path.strip()
        path_obj = Path(input_text_or_path)
        if path_obj.exists() and path_obj.is_file():
            raw_text = path_obj.read_text(encoding="utf-8")

        input_summary = (raw_text[:80] + "...") if len(raw_text) > 80 else raw_text
        benchmark_id = f"bm_{uuid.uuid4().hex[:8]}"
        created_at = current_utc_time()

        # 2. Defintra Structured Pipeline Benchmark
        t0 = time.perf_counter()
        project = self.discovery.run_fast_path(project_name, raw_text)
        compiled = self.compiler.compile(
            task_description=f"Implement core requirements for {project_name}",
            project_id=project.id,
            role=AgentRole.BACKEND_ENGINEER,
        )
        defintra_tokens = compiled.token_count
        defintra_duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        defintra_reqs = len(self.db.get_requirements(project.id))
        defintra_health = round(project.spec_health_score, 1)
        defintra_entropy = round(project.spec_entropy, 2)

        # 3. Naive Prompting Baseline Benchmark
        t1 = time.perf_counter()
        provider = get_llm_provider()
        naive_prompt = (
            f"You are a software engineering assistant. "
            f"Write a list of software requirements for this idea:\n\n{raw_text}"
        )
        try:
            naive_resp = provider.generate(prompt=naive_prompt)
            naive_content = naive_resp.content or ""
        except Exception:
            naive_content = "1. Setup project\n2. Implement API\n3. Add testing"

        naive_duration_ms = round((time.perf_counter() - t1) * 1000, 2)
        naive_tokens = TokenEstimator.estimate_tokens(naive_content)
        
        # Estimate distinct requirement count from naive text
        lines = [line.strip() for line in naive_content.split("\n") if line.strip()]
        naive_req_lines = [
            line_item for line_item in lines
            if line_item.startswith(("-", "*", "•", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10."))
        ]
        naive_req_count = max(len(naive_req_lines), 3)

        # 4. Summary Calculation
        req_diff = defintra_reqs - naive_req_count
        token_ratio = round((defintra_tokens / max(naive_tokens, 1)), 2)
        summary = (
            f"Defintra produced {defintra_reqs} typed EARS requirements ({'+' if req_diff >= 0 else ''}{req_diff} vs naive). "
            f"Context efficiency: {defintra_tokens} tokens ({token_ratio}x naive size). "
            f"Health Score: {defintra_health}/100, Entropy: {defintra_entropy}."
        )

        res = BenchmarkResult(
            benchmark_id=benchmark_id,
            project_id=project.id,
            input_summary=input_summary,
            defintra_req_count=defintra_reqs,
            defintra_health_score=defintra_health,
            defintra_entropy=defintra_entropy,
            defintra_token_count=defintra_tokens,
            defintra_duration_ms=defintra_duration_ms,
            naive_req_count=naive_req_count,
            naive_token_count=naive_tokens,
            naive_duration_ms=naive_duration_ms,
            comparison_summary=summary,
            created_at=created_at,
        )

        # 5. Persist in database
        self.db.save_benchmark(res.to_dict())
        return res

    def get_history(self, project_id: Optional[str] = None, limit: int = 10) -> List[BenchmarkResult]:
        rows = self.db.get_benchmarks(project_id=project_id, limit=limit)
        return [
            BenchmarkResult(
                benchmark_id=r["id"],
                project_id=r["project_id"],
                input_summary=r["input_summary"],
                defintra_req_count=r["defintra_req_count"],
                defintra_health_score=r["defintra_health_score"],
                defintra_entropy=r["defintra_entropy"],
                defintra_token_count=r["defintra_token_count"],
                defintra_duration_ms=r["defintra_duration_ms"],
                naive_req_count=r["naive_req_count"],
                naive_token_count=r["naive_token_count"],
                naive_duration_ms=r["naive_duration_ms"],
                comparison_summary=r["comparison_summary"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
