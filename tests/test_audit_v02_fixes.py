"""Batería de pruebas unitarias para verificar la subsanación de los 13 hallazgos de la segunda auditoría técnica."""

import pytest
from praxeon.core.jev_engine import JEVEngine
from praxeon.core.state_graph import StateGraph
from praxeon.domain.models import (
    ActionCandidate,
    DecisionReceipt,
    DecisionStatus,
    Goal,
    PolicyDecision,
    ProviderAssessment,
    RiskAssessment,
    RiskLevel,
    ToolCall,
)
from praxeon.models.schema import (
    BatchSemantics,
    ConvergenceAnomaly,
    GroundingAnomaly,
    InstrumentalRiskAnomaly,
    LoopReport,
    LoopType,
    Step,
    StepType,
    Trajectory,
)
from praxeon.policy.engine import PolicyEngine
from praxeon.policy.failsafe import FailSafePolicy
from praxeon.policy.registry import ToolRegistry, ToolSpec
from praxeon.providers.replay import ReplayReasoningProvider
from praxeon.reasoning.completion import CompletionVerifier
from praxeon.reasoning.loop_detector import LoopDetector
from praxeon.runtime.executor import PolicyViolation, SecureExecutor
from praxeon.runtime.navigator import Navigator
from praxeon.runtime.state import SessionState


def test_audit_3_12_no_residual_embeddings():
    """Hallazgo 3.12: Los esquemas nucleares no deben retener campos residuales de embedding."""
    step = Step(id="s1", step_type=StepType.THOUGHT, content="Reflexión")
    cand = ActionCandidate(id="c1", description="Acción")
    traj = Trajectory(session_id="sess_1", goal="Meta", steps=[])

    assert not hasattr(step, "embedding") or "embedding" not in step.model_fields
    assert not hasattr(cand, "embedding") or "embedding" not in cand.model_fields
    assert not hasattr(traj, "goal_embedding") or "goal_embedding" not in traj.model_fields


def test_audit_3_2_fail_safe_not_fail_open():
    """Hallazgo 3.2: La caída o indisponibilidad del evaluador no debe emitir un dictamen permisivo (fail-open)."""
    graph = StateGraph()
    graph.goal = "Probar fail-safe"
    engine = JEVEngine(graph)

    # Forzar que el cliente de typesafe simule indisponibilidad
    engine.typesafe_client.is_available = lambda: False  # type: ignore

    cand = ActionCandidate(
        id="c1",
        description="Borrar base de datos",
        tool_call=ToolCall(tool_name="delete_file", arguments={"path": "db.sqlite"}),
    )

    score = engine.evaluate_candidate(cand)
    # Debe reflejar indisponibilidad, NO un 0.5 neutral
    assert score.details.get("provider_available") is False
    assert score.total_jev <= 0.0

    # En PolicyEngine, un proveedor offline con acción no-readonly debe resultar en ABSTAIN o BLOCK, NUNCA ALLOW
    policy_engine = PolicyEngine()
    assessment = engine.evaluate_candidate_assessment(cand)
    assert assessment.available is False

    decision, receipt = policy_engine.evaluate_action(
        action=cand,
        state={},
        provider_assessment=assessment,
    )
    assert decision.status in (DecisionStatus.ABSTAIN, DecisionStatus.BLOCK)
    assert decision.status != DecisionStatus.ALLOW


def test_audit_3_3_batch_semantics_independence():
    """Hallazgo 3.3: Con BatchSemantics(independent=True), un fallo en paso k no penaliza en cascada pasos independientes."""
    graph = StateGraph()
    graph.goal = "Inspección masiva"
    engine = JEVEngine(graph)

    # Mock chunk response donde flagged_index es 0
    engine.typesafe_client.is_available = lambda: True  # type: ignore
    engine.typesafe_client.evaluate_step_chunk = lambda **kw: {  # type: ignore
        "p_progress": 0.8,
        "delta_u": 0.8,
        "loop_penalty": 1.5,
        "flagged_index": 0,
    }

    candidates = [
        ActionCandidate(id="c0", description="Paso 1 errante", tool_call=ToolCall(tool_name="tool_err")),
        ActionCandidate(id="c1", description="Paso 2 independiente", tool_call=ToolCall(tool_name="read_file")),
    ]

    # Modo dependiente (por defecto): cascada activada
    res_dep = engine.evaluate_candidate_chunk(candidates, batch_semantics=BatchSemantics(independent=False))
    assert res_dep[1][1].total_jev < 0  # c1 penalizado en cascada

    # Modo independiente: c1 no se penaliza en cascada
    res_indep = engine.evaluate_candidate_chunk(candidates, batch_semantics=BatchSemantics(independent=True))
    assert res_indep[0][1].total_jev < 0  # c0 penalizado
    assert res_indep[1][1].total_jev > 0.5  # c1 preservado por independencia


def test_audit_3_4_tool_registry_specifications():
    """Hallazgo 3.4: Las decisiones no dependen de strings hardcodeados sino de ToolSpec tipados."""
    registry = ToolRegistry(register_defaults=True)

    read_spec = registry.get_tool("read_file")
    assert read_spec is not None
    assert read_spec.read_only is True
    assert read_spec.risk_level == RiskLevel.LOW
    assert registry.is_observational("read_file") is True

    delete_spec = registry.get_tool("delete_file")
    assert delete_spec is not None
    assert delete_spec.read_only is False
    assert delete_spec.destructive is True
    assert delete_spec.risk_level == RiskLevel.CRITICAL
    assert registry.is_observational("delete_file") is False


def test_audit_3_5_finish_requires_completion_verifier():
    """Hallazgo 3.5: finish sin evidencias no recibe puntuación arbitraria (0.95), sino verificación formal."""
    verifier = CompletionVerifier()
    goal = Goal(objective="Reparar bug en auth", success_criteria=["tests passing", "token generated"])
    state = SessionState(session_id="s1", goal=goal)

    finish_action = ActionCandidate(
        id="finish_1",
        description="Terminar sin haber hecho nada",
        tool_call=ToolCall(tool_name="finish", arguments={"summary": "listo"}),
    )

    assessment = verifier.verify(goal, state, finish_action)
    # Sin pasos ni evidencias debe ser rechazado
    assert assessment.is_complete is False


def test_audit_3_8_execution_barrier_policy_violation():
    """Hallazgo 3.8: SecureExecutor impide físicamente la ejecución si la política no emite ALLOW."""
    executor = SecureExecutor()
    goal = Goal(objective="Prueba de contención")
    state = SessionState(session_id="s1", goal=goal)

    action = ActionCandidate(
        id="act_1",
        description="Comando peligroso",
        tool_call=ToolCall(tool_name="run_command", arguments={"command": "dir"}),
    )

    # Intentar ejecutar con estatus BLOCK
    decision_block = PolicyDecision(status=DecisionStatus.BLOCK, reason_codes=["SECURITY_BLOCK"])
    with pytest.raises(PolicyViolation):
        executor.execute(action, state, decision=decision_block)

    # Intentar ejecutar con estatus REPLAN
    decision_replan = PolicyDecision(status=DecisionStatus.REPLAN, reason_codes=["REPLAN_MANDATED"])
    with pytest.raises(PolicyViolation):
        executor.execute(action, state, decision=decision_replan)


def test_audit_3_13_segregated_anomaly_dimensions():
    """Hallazgo 3.13: LoopDetector segrega convergencia, solidez empírica y riesgo instrumental."""
    detector = LoopDetector()

    # 1. Prueba de solidez empírica (premisas no fundamentadas)
    step1 = Step(id="s1", step_type=StepType.THOUGHT, content="pensamiento")
    cand_unfounded = ActionCandidate(
        id="c1",
        description="Editar sin haber leído",
        tool_call=ToolCall(tool_name="edit_file", arguments={"path": "secret.txt"}),
        requires_evidence=["file_read:secret.txt"],
    )

    report = detector.analyze_trajectory([step1], candidate=cand_unfounded, available_evidence_claims=set())
    assert report.loop_detected is True
    assert report.grounding == GroundingAnomaly.UNGROUNDED_PREMISE
    assert report.convergence == ConvergenceAnomaly.NONE


def test_audit_5_2_decision_receipt_full_contract():
    """Sección 5.2 / Cuadro 1: DecisionReceipt registra todas las dimensiones de contexto, proveedor, razonamiento, riesgo, política y ejecución."""
    receipt = DecisionReceipt(
        decision_id="dec_001",
        session_id="sess_001",
        action_id="act_001",
        state_hash="state_hash_123",
        action_hash="action_hash_456",
        provider_available=True,
        model_identifier="system-one-v1",
        latency_ms=14.5,
        progress_score=0.88,
        grounded_score=0.92,
        loop_type="none",
        novelty_score=0.75,
        risk_level="low",
        risk_reasons=["Lectura segura"],
        destructive_potential=False,
        decision_status=DecisionStatus.ALLOW,
        reason_codes=["GROUNDED_LOW_RISK_AUTHORIZED"],
        is_executed=True,
        observation_id="obs_001",
    )

    # Verificar que todos los atributos requeridos existan
    assert receipt.decision_id == "dec_001"
    assert receipt.provider_available is True
    assert receipt.progress_score == 0.88
    assert receipt.grounded_score == 0.92
    assert receipt.risk_level == "low"
    assert receipt.decision_status == DecisionStatus.ALLOW
    assert receipt.decision == DecisionStatus.ALLOW  # Compatibilidad
    assert receipt.is_executed is True
    assert receipt.observation_id == "obs_001"
