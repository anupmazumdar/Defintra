import pytest

from defintra.core.benchmark.runner import BenchmarkRunner
from defintra.core.db.database import Database


@pytest.fixture
def bm_db(tmp_path):
    db_file = tmp_path / "benchmark_test.db"
    return Database(str(db_file))


def test_benchmark_runner_execution_and_comparison(bm_db, tmp_path):
    runner = BenchmarkRunner(bm_db)

    # 1. Run benchmark with inline text
    res = runner.run_benchmark(
        input_text_or_path="Build a distributed cache with LRU eviction, TTL expiration, and Prometheus metrics exporter",
        project_name="Cache Evaluation",
    )

    assert res.benchmark_id.startswith("bm_")
    assert res.defintra_req_count > 0
    assert res.defintra_health_score > 0
    assert res.defintra_token_count > 0
    assert res.naive_req_count > 0
    assert len(res.comparison_summary) > 0

    # 2. Check history retrieval
    history = runner.get_history(limit=5)
    assert len(history) == 1
    assert history[0].benchmark_id == res.benchmark_id
    assert history[0].defintra_req_count == res.defintra_req_count

    # 3. Run benchmark with file input
    prd_file = tmp_path / "sample_prd.txt"
    prd_file.write_text("Build a microservices payment gateway integrating Apple Pay, Google Pay, and webhooks", encoding="utf-8")

    res_file = runner.run_benchmark(
        input_text_or_path=str(prd_file),
        project_name="Payment Benchmark",
    )
    assert res_file.defintra_req_count > 0

    history_all = runner.get_history(limit=5)
    assert len(history_all) == 2
