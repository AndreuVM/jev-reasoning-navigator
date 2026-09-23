"""Baterías de pruebas, benchmarks y métricas v0.2."""

from jev_navigator.evaluation.metrics import (
    EvaluationMetrics,
    MetricsCalculator,
    compute_navigator_economic_value,
)
from jev_navigator.evaluation.reports import ReportGenerator
from jev_navigator.evaluation.runner import BenchmarkRunner
from jev_navigator.evaluation.scenarios import BenchmarkScenario, ScenarioCatalog

__all__ = [
    "BenchmarkScenario",
    "ScenarioCatalog",
    "BenchmarkRunner",
    "EvaluationMetrics",
    "MetricsCalculator",
    "ReportGenerator",
    "compute_navigator_economic_value",
]
