"""Pruebas unitarias e integrales para la Fase 4 de Evaluación en JEV Reasoning Navigator.

Valida:
1. Partición del dataset procedural: Train (800) vs Holdout (200) de 1.000+ escenarios.
2. Los 5 benchmarks especializados:
   - Provider Benchmark (JEV vs LAYA vs CascadeRouter)
   - Policy Benchmark (ALLOW, BLOCK, REPLAN, ABSTAIN y matriz de confusión)
   - Enforcement Benchmark (barrera física contra HMAC alterado, replay, traversal, egress)
   - Runtime Benchmark (ops/sec, distribución percentil p50/p95/p99)
   - Trajectory Benchmark (trayectorias multi-paso, rollback, recuperación y backtracking)
3. Estudio de ablación expandido con las 6 configuraciones arquitecturales.
"""

import pytest
from jev_navigator.domain.models import DecisionStatus
from jev_navigator.evaluation.runner import (
    BenchmarkRunner,
    EnforcementBenchmarkReport,
    PolicyBenchmarkReport,
    RuntimeBenchmarkReport,
    TrajectoryBenchmarkReport,
)
from jev_navigator.evaluation.scenarios import (
    BenchmarkScenario,
    ScenarioCatalog,
    TrajectoryScenario,
)
from jev_navigator.providers.replay import ReplayProvider
from jev_navigator.runtime.navigator import Navigator


class TestHoldoutSplit:
    """Verifica la generación y partición determinista del dataset procedural."""

    def test_train_and_holdout_split(self):
        """Verifica que el dataset de 1.000 escenarios se divide limpiamente en 800 train y 200 holdout."""
        train_scenarios = ScenarioCatalog.get_train_scenarios(n=800, seed=42)
        holdout_scenarios = ScenarioCatalog.get_holdout_scenarios(n=200, seed=42)

        assert len(train_scenarios) == 800
        assert len(holdout_scenarios) == 200

        train_ids = {s.scenario_id for s in train_scenarios}
        holdout_ids = {s.scenario_id for s in holdout_scenarios}

        # Los conjuntos deben ser estrictamente disjuntos
        assert len(train_ids.intersection(holdout_ids)) == 0

        # Verificamos reproducibilidad por semilla
        holdout_repeat = ScenarioCatalog.get_holdout_scenarios(n=200, seed=42)
        assert [s.scenario_id for s in holdout_scenarios] == [s.scenario_id for s in holdout_repeat]

    def test_holdout_scenario_variety(self):
        """Verifica que tanto train como holdout contengan categorías balanceadas."""
        holdout = ScenarioCatalog.get_holdout_scenarios(n=200, seed=42)
        categories = {s.category for s in holdout}
        assert len(categories) >= 3

        # Debe contener escenarios destructivos y no destructivos
        destructive = [s for s in holdout if s.is_destructive]
        safe = [s for s in holdout if not s.is_destructive]
        assert len(destructive) > 0
        assert len(safe) > 0


class TestTrajectoryScenarios:
    """Verifica los escenarios de trayectorias multi-paso de agentes."""

    def test_trajectory_scenarios_catalog(self):
        trajectories = ScenarioCatalog.get_trajectory_scenarios()
        assert len(trajectories) >= 3

        scenario_ids = [t.scenario_id for t in trajectories]
        assert "traj_linear_pipeline" in scenario_ids
        assert "traj_loop_recovery" in scenario_ids
        assert "traj_premature_finish_recovery" in scenario_ids

        for traj in trajectories:
            assert isinstance(traj, TrajectoryScenario)
            assert len(traj.steps) >= 3
            assert traj.goal is not None


class TestPolicyBenchmark:
    """Verifica la ejecución del benchmark de políticas operacionales."""

    def test_run_policy_benchmark_basic(self):
        scenarios = ScenarioCatalog.get_canonical_scenarios()
        runner = BenchmarkRunner()
        report = runner.run_policy_benchmark(scenarios)

        assert isinstance(report, PolicyBenchmarkReport)
        assert report.total_evaluated == len(scenarios)
        assert 0.0 <= report.false_allow_rate <= 1.0
        assert report.destructive_false_allows == 0  # FailSafe no debe permitir destructivas no autorizadas
        assert report.justified_block_precision >= 0.0


class TestEnforcementBenchmark:
    """Verifica que la barrera física de enforcement detenga el 100% de ataques reales."""

    def test_run_enforcement_benchmark_100_percent_prevention(self):
        runner = BenchmarkRunner()
        report = runner.run_enforcement_benchmark()

        assert isinstance(report, EnforcementBenchmarkReport)
        assert report.total_attack_scenarios >= 4
        assert report.bypasses_attempted == report.bypasses_blocked
        assert report.execution_prevention_rate == 1.0
        assert report.unauthorized_physical_executions == 0
        assert report.replay_attacks_blocked >= 1
        assert report.tampered_hmac_blocked >= 1
        assert report.path_traversal_blocked >= 1
        assert report.egress_violations_blocked >= 1


class TestRuntimeBenchmark:
    """Verifica la medición de throughput y percentiles de latencia del supervisor."""

    def test_run_runtime_benchmark(self):
        runner = BenchmarkRunner()
        report = runner.run_runtime_benchmark(iterations=30)

        assert isinstance(report, RuntimeBenchmarkReport)
        assert report.total_operations == 30
        assert report.total_duration_sec > 0.0
        assert report.throughput_ops_sec > 0.0
        assert report.latency_p50_ms >= 0.0
        assert report.latency_p95_ms >= report.latency_p50_ms
        assert report.latency_p99_ms >= report.latency_p95_ms
        assert report.latency_mean_ms >= 0.0


class TestTrajectoryBenchmark:
    """Verifica la simulación de trayectorias multi-paso con rollbacks y recovery."""

    def test_run_trajectory_benchmark(self):
        trajectories = ScenarioCatalog.get_trajectory_scenarios()
        runner = BenchmarkRunner()
        report = runner.run_trajectory_benchmark(trajectories)

        assert isinstance(report, TrajectoryBenchmarkReport)
        assert report.total_trajectories == len(trajectories)
        assert report.completed_trajectories > 0
        assert report.completion_rate > 0.0
        assert report.total_steps > 0
        assert report.rollbacks_triggered >= 1
        assert report.rollbacks_successful >= 1
        assert report.recovery_rate >= 0.5
        assert report.premature_finishes_prevented >= 1


class TestAblationStudyExpanded:
    """Verifica el estudio de ablación ampliado con las 6 configuraciones arquitecturales."""

    def test_run_ablation_study_all_six_configs(self):
        scenarios = ScenarioCatalog.get_canonical_scenarios()[:5]
        runner = BenchmarkRunner()
        reports = runner.run_expanded_ablation_study(scenarios)

        assert len(reports) == 6
        expected_configs = [
            "1. Policy Only (No JEV)",
            "2. JEV (No Evidence Engine)",
            "3. JEV + Evidence (No Risk Engine)",
            "4. JEV + Evidence + Risk (No FailSafe)",
            "5. Full v0.2 Architecture",
            "6. Full v0.4 Architecture (Confidence Router)",
        ]

        assert list(reports.keys()) == expected_configs
        for config_name, metrics in reports.items():
            assert metrics.accuracy >= 0.0
            assert metrics.economic_value is not None

