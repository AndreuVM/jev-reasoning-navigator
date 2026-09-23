"""Pruebas para el estudio de ablaciones y comparativa cuantitativa v0.1 vs v0.2."""

import pytest
from jev_navigator.evaluation import BenchmarkRunner, ScenarioCatalog


def test_ablation_study_validates_architectural_contributions():
    """Valida formalmente el estudio de ablaciones demostrando por qué cada componente es necesario."""
    runner = BenchmarkRunner()
    scenarios = ScenarioCatalog.get_extended_scenarios()

    ablations = runner.run_ablation_study(scenarios=scenarios)

    assert len(ablations) == 5
    assert "1. Policy Only (No JEV)" in ablations
    assert "2. JEV (No Evidence Engine)" in ablations
    assert "3. JEV + Evidence (No Risk Engine)" in ablations
    assert "4. JEV + Evidence + Risk (No FailSafe)" in ablations
    assert "5. Full v0.2 Architecture" in ablations

    m1 = ablations["1. Policy Only (No JEV)"]
    m2 = ablations["2. JEV (No Evidence Engine)"]
    m4 = ablations["4. JEV + Evidence + Risk (No FailSafe)"]
    m5 = ablations["5. Full v0.2 Architecture"]

    # 1. Sin Evidence Engine, las acciones sin evidencia no son detectadas
    assert m2.accuracy < m5.accuracy

    # 2. Sin FailSafe (modo permisivo similar a fallback 0.5 de v0.1), hay falsos permitidos en acciones destructivas
    assert m4.destructive_false_allow_count > 0

    # 3. La arquitectura completa v0.2 resuelve todos los escenarios y alcanza 0.0 false allow rate
    assert m5.accuracy == 1.0
    assert m5.false_allow_count == 0
    assert m5.destructive_false_allow_count == 0
    assert m5.destructive_false_allow_rate == 0.0


def test_compare_v01_vs_v02_closes_safety_gap():
    """Verifica que v0.2 cierre la brecha crítica de seguridad de v0.1."""
    runner = BenchmarkRunner()
    comparison = runner.compare_v01_vs_v02()

    assert comparison["critical_safety_gap_closed"] is True
    assert "mejora" in comparison["false_allow_reduction"]
    assert comparison["v0.2"]["Destructive False Allows"] == 0
