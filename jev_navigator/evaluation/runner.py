"""Ejecutor de benchmarks y estudios de ablación (BenchmarkRunner) para v0.2.

Permite evaluar sistemáticamente la calidad, seguridad, latencia y robustez de
JEV Reasoning Navigator frente a escenarios reproducibles con ground truth.
"""

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from jev_navigator.domain.models import DecisionStatus, Goal, ProviderAssessment
from jev_navigator.evaluation.metrics import EvaluationMetrics, MetricsCalculator
from jev_navigator.evaluation.scenarios import BenchmarkScenario, ScenarioCatalog
from jev_navigator.policy.engine import PolicyEngine
from jev_navigator.policy.failsafe import FailSafePolicy
from jev_navigator.policy.risk import ToolRegistry
from jev_navigator.providers.replay import ReplayProvider
from jev_navigator.reasoning.completion import CompletionVerifier
from jev_navigator.reasoning.evidence import EvidenceEngine
from jev_navigator.reasoning.risk import RiskEngine
from jev_navigator.runtime.checkpoints import CheckpointManager
from jev_navigator.runtime.executor import SecureExecutor
from jev_navigator.runtime.navigator import Navigator
from jev_navigator.runtime.state import SessionState


class ScenarioResult(BaseModel):
    """Resultado individual de la ejecución de un escenario de benchmark."""
    model_config = ConfigDict(frozen=True)

    scenario_id: str
    category: str
    expected_status: DecisionStatus
    actual_status: DecisionStatus
    is_match: bool
    is_destructive: bool
    is_finish: bool = False
    simulated_provider_drop: bool = False
    execution_prevented: bool = True
    capability_verified: bool = True
    latency_ms: float
    reason_codes: List[str]
    description: str


class BenchmarkReport(BaseModel):
    """Informe consolidado de ejecución de un benchmark."""
    model_config = ConfigDict(frozen=True)

    suite_name: str
    timestamp: float = Field(default_factory=time.time)
    metrics: EvaluationMetrics
    results: List[ScenarioResult]


class ProviderComparisonReport(BaseModel):
    """Informe comparativo formal entre proveedores de razonamiento semántico (JEV vs LAYA vs Replay)."""
    model_config = ConfigDict(frozen=True)

    timestamp: float = Field(default_factory=time.time)
    total_scenarios: int
    agreement_count: int
    agreement_rate: float
    disagreement_count: int
    disagreement_rate: float
    provider_a_name: str
    provider_b_name: str
    provider_a_avg_latency_ms: float
    provider_b_avg_latency_ms: float
    provider_a_p95_latency_ms: float
    provider_b_p95_latency_ms: float
    disagreements: List[Dict[str, Any]] = Field(default_factory=list)


class BenchmarkRunner:
    """Ejecuta suites de escenarios contra el Navigator y realiza estudios de ablación."""

    def __init__(self, navigator: Optional[Navigator] = None):
        self.navigator = navigator

    def run_scenario(
        self,
        scenario: BenchmarkScenario,
        navigator: Optional[Navigator] = None,
    ) -> ScenarioResult:
        """Ejecuta un único escenario normativo registrando la decisión, ejecución física y latencia."""
        nav = navigator or self.navigator
        if nav is None:
            provider = ReplayProvider(default_scenario="safe_read")
            executor = SecureExecutor(dry_run=True)
            nav = Navigator(provider=provider, executor=executor)

        # 1. Configurar estado inicial del escenario
        nav.start_session(goal=scenario.goal, session_id=f"bench_{scenario.scenario_id}")
        assert nav.state is not None

        for ev in scenario.initial_evidence:
            nav.state.add_evidence(ev)
            nav.evidence_engine._evidence_pool[ev.claim.lower().strip()] = ev

        for tool in scenario.forbidden_tools:
            nav.state.forbid_tool(tool)

        # 2. Configurar la evaluación semántica simulada
        if isinstance(nav.provider, ReplayProvider):
            nav.provider.override_for_action(scenario.candidate_action.id, scenario.simulated_assessment)

        start = time.perf_counter()
        # 3. Tomar decisión formal con el Navigator
        decision, receipt = nav.decide(
            action=scenario.candidate_action,
            assessment=scenario.simulated_assessment,
        )
        latency = (time.perf_counter() - start) * 1000.0

        is_match = decision.status == scenario.expected_status

        # 4. Probar enforcement físico real y verificación de capabilities
        execution_prevented = True
        capability_verified = True
        if decision.status == DecisionStatus.ALLOW:
            try:
                obs = nav.executor.execute(
                    action=scenario.candidate_action,
                    state=nav.state,
                    receipt=receipt,
                )
                execution_prevented = False
                capability_verified = (obs is not None)
            except Exception:
                execution_prevented = True
                capability_verified = False
        else:
            execution_prevented = True

        is_finish = nav.completion_verifier.is_finish_action(scenario.candidate_action)
        is_provider_drop = bool(
            scenario.simulated_assessment is not None and not scenario.simulated_assessment.available
        )

        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            category=scenario.category,
            expected_status=scenario.expected_status,
            actual_status=decision.status,
            is_match=is_match,
            is_destructive=scenario.is_destructive,
            is_finish=is_finish,
            simulated_provider_drop=is_provider_drop,
            execution_prevented=execution_prevented,
            capability_verified=capability_verified,
            latency_ms=round(latency, 2),
            reason_codes=decision.reason_codes,
            description=scenario.description,
        )

    def run_benchmark(
        self,
        scenarios: Optional[List[BenchmarkScenario]] = None,
        navigator: Optional[Navigator] = None,
        suite_name: str = "JEV-v0.2-Full-Benchmark",
    ) -> BenchmarkReport:
        """Ejecuta una lista de escenarios y compila las métricas globales."""
        target_scenarios = scenarios or ScenarioCatalog.get_extended_scenarios()
        results: List[ScenarioResult] = []

        for sc in target_scenarios:
            res = self.run_scenario(sc, navigator=navigator)
            results.append(res)

        metrics = MetricsCalculator.calculate([r.model_dump() for r in results])
        return BenchmarkReport(
            suite_name=suite_name,
            metrics=metrics,
            results=results,
        )

    def run_ablation_study(
        self,
        scenarios: Optional[List[BenchmarkScenario]] = None,
    ) -> Dict[str, EvaluationMetrics]:
        """Ejecuta el estudio formal de ablaciones de la sección 25 del diseño.
        
        Evalúa:
        1. Policy Only (sin JEV): juicios semánticos neutrales.
        2. JEV (sin Evidence Engine): precondiciones de groundedness ignoradas.
        3. JEV + Evidence (sin Risk Engine): todas las herramientas consideradas bajo riesgo.
        4. JEV + Evidence + Risk (sin FailSafe): fallo del proveedor tratado como neutral (v0.1 fallback).
        5. Full v0.2: Arquitectura completa con todas las capas y fail-safe.
        """
        target_scenarios = scenarios or ScenarioCatalog.get_extended_scenarios()
        ablation_results: Dict[str, EvaluationMetrics] = {}

        # -------------------------------------------------------------
        # Configuración 1: Policy Only (Sin señales semánticas JEV)
        # -------------------------------------------------------------
        def eval_config_1(sc: BenchmarkScenario) -> Dict[str, Any]:
            start = time.perf_counter()
            reg = ToolRegistry(register_defaults=True)
            pol = PolicyEngine(registry=reg)
            neutral_assessment = ProviderAssessment(provider="mock", available=True, confidence=0.5)
            ev_list = list(sc.initial_evidence)
            dec, _ = pol.evaluate_action(
                action=sc.candidate_action,
                state={"goal": sc.goal.model_dump()},
                provider_assessment=neutral_assessment,
                available_evidence=ev_list,
                forbidden_tools=sc.forbidden_tools,
            )
            lat = (time.perf_counter() - start) * 1000.0
            return {
                "expected_status": sc.expected_status,
                "actual_status": dec.status,
                "is_destructive": sc.is_destructive,
                "latency_ms": lat,
            }

        res_1 = [eval_config_1(s) for s in target_scenarios]
        ablation_results["1. Policy Only (No JEV)"] = MetricsCalculator.calculate(res_1)

        # -------------------------------------------------------------
        # Configuración 2: JEV sin Evidence Engine (Groundedness ciego)
        # -------------------------------------------------------------
        def eval_config_2(sc: BenchmarkScenario) -> Dict[str, Any]:
            start = time.perf_counter()
            reg = ToolRegistry(register_defaults=True)
            pol = PolicyEngine(registry=reg)
            # Ignoramos la evidencia requerida (groundedness ciego)
            action_no_req = sc.candidate_action.model_copy(update={"requires_evidence": []})
            dec, _ = pol.evaluate_action(
                action=action_no_req,
                state={"goal": sc.goal.model_dump()},
                provider_assessment=sc.simulated_assessment,
                available_evidence=[],
                forbidden_tools=sc.forbidden_tools,
            )
            lat = (time.perf_counter() - start) * 1000.0
            return {
                "expected_status": sc.expected_status,
                "actual_status": dec.status,
                "is_destructive": sc.is_destructive,
                "latency_ms": lat,
            }

        res_2 = [eval_config_2(s) for s in target_scenarios]
        ablation_results["2. JEV (No Evidence Engine)"] = MetricsCalculator.calculate(res_2)

        # -------------------------------------------------------------
        # Configuración 3: JEV + Evidence (Sin Risk Engine / Sin Veto Shell)
        # -------------------------------------------------------------
        def eval_config_3(sc: BenchmarkScenario) -> Dict[str, Any]:
            start = time.perf_counter()
            # Registro permisivo donde todo es seguro
            reg = ToolRegistry(register_defaults=False)
            tool_name = sc.candidate_action.tool_call.tool_name if sc.candidate_action.tool_call else "default"
            from jev_navigator.policy.risk import ToolSpec, RiskLevel
            reg.register(ToolSpec(name=tool_name, category="general", risk_level=RiskLevel.LOW))
            pol = PolicyEngine(registry=reg)
            dec, _ = pol.evaluate_action(
                action=sc.candidate_action,
                state={"goal": sc.goal.model_dump()},
                provider_assessment=sc.simulated_assessment,
                available_evidence=sc.initial_evidence,
                forbidden_tools=sc.forbidden_tools,
            )
            lat = (time.perf_counter() - start) * 1000.0
            return {
                "expected_status": sc.expected_status,
                "actual_status": dec.status,
                "is_destructive": sc.is_destructive,
                "latency_ms": lat,
            }

        res_3 = [eval_config_3(s) for s in target_scenarios]
        ablation_results["3. JEV + Evidence (No Risk Engine)"] = MetricsCalculator.calculate(res_3)

        # -------------------------------------------------------------
        # Configuración 4: JEV + Evidence + Risk (Sin FailSafe - modo permisivo v0.1)
        # -------------------------------------------------------------
        def eval_config_4(sc: BenchmarkScenario) -> Dict[str, Any]:
            start = time.perf_counter()
            reg = ToolRegistry(register_defaults=True)
            # FailSafe que permite todo ante caída del proveedor
            permissive_failsafe = FailSafePolicy(
                allow_read_only_on_provider_failure=True,
                block_destructive_on_provider_failure=False,
            )
            pol = PolicyEngine(registry=reg, failsafe=permissive_failsafe)
            dec, _ = pol.evaluate_action(
                action=sc.candidate_action,
                state={"goal": sc.goal.model_dump()},
                provider_assessment=sc.simulated_assessment,
                available_evidence=sc.initial_evidence,
                forbidden_tools=sc.forbidden_tools,
            )
            lat = (time.perf_counter() - start) * 1000.0
            return {
                "expected_status": sc.expected_status,
                "actual_status": dec.status,
                "is_destructive": sc.is_destructive,
                "latency_ms": lat,
            }

        res_4 = [eval_config_4(s) for s in target_scenarios]
        ablation_results["4. JEV + Evidence + Risk (No FailSafe)"] = MetricsCalculator.calculate(res_4)

        # -------------------------------------------------------------
        # Configuración 5: Full v0.2 Architecture
        # -------------------------------------------------------------
        report_v02 = self.run_benchmark(scenarios=target_scenarios, suite_name="Full-v0.2")
        ablation_results["5. Full v0.2 Architecture"] = report_v02.metrics

        return ablation_results

    def compare_v01_vs_v02(
        self,
        scenarios: Optional[List[BenchmarkScenario]] = None,
    ) -> Dict[str, Any]:
        """Compara cuantitativamente el comportamiento de v0.1 frente a v0.2."""
        ablations = self.run_ablation_study(scenarios=scenarios)
        v01_proxy = ablations["4. JEV + Evidence + Risk (No FailSafe)"]
        v02_full = ablations["5. Full v0.2 Architecture"]

        return {
            "v0.1": v01_proxy.to_summary_dict(),
            "v0.2": v02_full.to_summary_dict(),
            "false_allow_reduction": f"{(v01_proxy.false_allow_rate - v02_full.false_allow_rate) * 100:.1f}% mejora",
            "critical_safety_gap_closed": v02_full.destructive_false_allow_count == 0,
        }

    def run_provider_comparison(
        self,
        scenarios: Optional[List[BenchmarkScenario]] = None,
        provider_a: Optional[Any] = None,
        provider_b: Optional[Any] = None,
    ) -> ProviderComparisonReport:
        """Compara empíricamente la concordancia decisional, latencia y telemetría entre dos proveedores."""
        from jev_navigator.providers.laya import LayaProvider

        target_scenarios = scenarios or ScenarioCatalog.get_extended_scenarios()
        p_a = provider_a or ReplayProvider(default_scenario="safe_read")
        p_b = provider_b or LayaProvider(backend="simulated")

        agreements = 0
        disagreements = 0
        latencies_a: List[float] = []
        latencies_b: List[float] = []
        disagreement_details: List[Dict[str, Any]] = []

        for sc in target_scenarios:
            st = SessionState(session_id=f"cmp_{sc.scenario_id}", goal=sc.goal)
            for ev in sc.initial_evidence:
                st.add_evidence(ev)

            # Provider A
            t0 = time.perf_counter()
            if isinstance(p_a, ReplayProvider):
                p_a.override_for_action(sc.candidate_action.id, sc.simulated_assessment)
            res_a = p_a.evaluate(st, [sc.candidate_action])[0]
            lat_a = (time.perf_counter() - t0) * 1000.0
            latencies_a.append(lat_a)

            # Provider B
            t0 = time.perf_counter()
            res_b = p_b.evaluate(st, [sc.candidate_action])[0]
            lat_b = (time.perf_counter() - t0) * 1000.0
            latencies_b.append(lat_b)

            loop_a = (res_a.loop_probability or 0.0) >= 0.60
            loop_b = (res_b.loop_probability or 0.0) >= 0.60
            ground_a = (res_a.grounded_probability or 1.0) <= 0.35
            ground_b = (res_b.grounded_probability or 1.0) <= 0.35

            if loop_a == loop_b and ground_a == ground_b and res_a.available == res_b.available:
                agreements += 1
            else:
                disagreements += 1
                disagreement_details.append({
                    "scenario_id": sc.scenario_id,
                    "provider_a": {"loop": res_a.loop_probability, "grounded": res_a.grounded_probability},
                    "provider_b": {"loop": res_b.loop_probability, "grounded": res_b.grounded_probability},
                })

        total = len(target_scenarios)
        sorted_a = sorted(latencies_a)
        sorted_b = sorted(latencies_b)
        idx_95 = int(total * 0.95) if total > 0 else 0

        return ProviderComparisonReport(
            total_scenarios=total,
            agreement_count=agreements,
            agreement_rate=round(agreements / max(1, total), 3),
            disagreement_count=disagreements,
            disagreement_rate=round(disagreements / max(1, total), 3),
            provider_a_name=getattr(p_a, "model_name", "ReplayProvider"),
            provider_b_name=getattr(p_b, "model_name", "LayaProvider"),
            provider_a_avg_latency_ms=round(sum(latencies_a) / max(1, total), 2),
            provider_b_avg_latency_ms=round(sum(latencies_b) / max(1, total), 2),
            provider_a_p95_latency_ms=round(sorted_a[min(idx_95, len(sorted_a) - 1)] if sorted_a else 0.0, 2),
            provider_b_p95_latency_ms=round(sorted_b[min(idx_95, len(sorted_b) - 1)] if sorted_b else 0.0, 2),
            disagreements=disagreement_details,
        )
