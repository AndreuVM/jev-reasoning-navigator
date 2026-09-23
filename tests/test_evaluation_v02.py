"""Pruebas unitarias para el framework de evaluación y métricas en v0.2."""

import pytest
from jev_navigator.domain.models import DecisionStatus
from jev_navigator.evaluation import (
    BenchmarkRunner,
    EvaluationMetrics,
    MetricsCalculator,
    ScenarioCatalog,
)
from jev_navigator.providers.replay import ReplayProvider
from jev_navigator.runtime import Navigator, SecureExecutor


def test_scenario_catalog_integrity():
    """Verifica que los catálogos canónicos contengan escenarios completos y válidos."""
    minimal = ScenarioCatalog.get_minimal_scenarios()
    assert len(minimal) == 5
    ids = [s.scenario_id for s in minimal]
    assert "safe_read" in ids
    assert "missing_evidence" in ids
    assert "destructive_unknown" in ids
    assert "provider_uncertain" in ids
    assert "forbidden_after_loop" in ids

    extended = ScenarioCatalog.get_extended_scenarios()
    assert len(extended) == 10
    ext_ids = [s.scenario_id for s in extended]
    assert "provider_down_destructive" in ext_ids
    assert "premature_finish_rejection" in ext_ids
    assert "shell_critical_destructive" in ext_ids


def test_metrics_calculator_correctness():
    """Verifica el cálculo formal de exactitud, precisión, recall, F1 y false allow rate."""
    sample_results = [
        # Caso 1: Verdadero Positivo ALLOW
        {"expected_status": DecisionStatus.ALLOW, "actual_status": DecisionStatus.ALLOW, "is_destructive": False, "latency_ms": 10.0},
        # Caso 2: Verdadero Positivo BLOCK
        {"expected_status": DecisionStatus.BLOCK, "actual_status": DecisionStatus.BLOCK, "is_destructive": True, "latency_ms": 12.0},
        # Caso 3: Verdadero Positivo REPLAN
        {"expected_status": DecisionStatus.REPLAN, "actual_status": DecisionStatus.REPLAN, "is_destructive": False, "latency_ms": 15.0},
        # Caso 4: Falso Permitido (Crítico) - esperaba BLOCK pero fue ALLOW
        {"expected_status": DecisionStatus.BLOCK, "actual_status": DecisionStatus.ALLOW, "is_destructive": True, "latency_ms": 8.0},
    ]

    metrics = MetricsCalculator.calculate(sample_results)

    assert metrics.total_scenarios == 4
    assert metrics.correct_decisions == 3
    assert metrics.accuracy == 0.75
    assert metrics.false_allow_count == 1
    assert metrics.destructive_false_allow_count == 1
    assert metrics.destructive_false_allow_rate == 0.5  # 1 de 2 destructivos
    assert metrics.latency_p50_ms == 11.0
    assert metrics.latency_mean_ms == 11.25


def test_benchmark_runner_executes_extended_suite():
    """Verifica que BenchmarkRunner ejecute la suite extendida con 100% de precisión en v0.2."""
    provider = ReplayProvider(default_scenario="safe_read")
    executor = SecureExecutor(dry_run=True)
    nav = Navigator(provider=provider, executor=executor)
    runner = BenchmarkRunner(navigator=nav)

    scenarios = ScenarioCatalog.get_extended_scenarios()
    report = runner.run_benchmark(scenarios=scenarios, suite_name="Test-Suite")

    assert report.suite_name == "Test-Suite"
    assert len(report.results) == 10
    # En v0.2 todos los 10 escenarios normativos deben decidirse correctamente
    assert report.metrics.correct_decisions == 10
    assert report.metrics.accuracy == 1.0
    assert report.metrics.false_allow_count == 0
    assert report.metrics.false_allow_rate == 0.0
    assert report.metrics.destructive_false_allow_count == 0
    assert report.metrics.latency_mean_ms > 0
