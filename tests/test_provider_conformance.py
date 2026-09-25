"""Pruebas de conformidad formal y evaluación multi-proveedor (JEV, LAYA, Replay).

Verifica el cumplimiento de los contratos estipulados en la Fase 1:
1. ProviderContextBuilder: Presupuesto de tokens, truncado de historial y serialización.
2. LayaProvider: Evaluación mediante primitivas (choice, score, noul), metadatos de reproducibilidad y fail-safe.
3. Conformidad Multi-Provider: Invariantes comunes entre TypeSafeAdapter, LayaProvider y ReplayProvider.
4. Gating de Confianza (JEV-as-a-Judge): Escalado automático a ABSTAIN ante juicios de baja confianza.
"""

import pytest
from datetime import datetime
from typing import List

from praxeon.domain.action import ActionCandidate, ToolCall
from praxeon.domain.assessment import ProviderAssessment
from praxeon.domain.decision import DecisionStatus, PolicyDecision
from praxeon.domain.evidence import Evidence
from praxeon.domain.goal import Goal
from praxeon.policy.engine import PolicyEngine
from praxeon.providers.context import ProviderContext, ProviderContextBuilder
from praxeon.providers.laya import LayaProvider
from praxeon.providers.replay import ReplayProvider
from praxeon.providers.typesafe import TypeSafeAdapter
from praxeon.runtime.state import SessionState


@pytest.fixture
def sample_session_state() -> SessionState:
    goal = Goal(
        objective="Optimizar base de datos y migrar esquema",
        success_criteria=["índices creados", "migración completada"],
    )
    state = SessionState(session_id="test_provider_session", goal=goal)
    state.add_evidence(
        Evidence(id="ev_1", claim="esquema_actual_inspeccionado", content_hash="h1")
    )
    return state


@pytest.fixture
def sample_action() -> ActionCandidate:
    return ActionCandidate(
        id="act_migrate",
        description="Crear índice de búsqueda en users",
        tool_call=ToolCall(tool_name="run_command", arguments={"cmd": "CREATE INDEX idx_users ON users(id)"}),
        requires_evidence=["esquema_actual_inspeccionado"],
    )


# =========================================================================
# 1. Pruebas de ProviderContextBuilder
# =========================================================================

def test_context_builder_preserves_core_context(sample_session_state, sample_action):
    """Verifica que ProviderContextBuilder preserve la meta, evidencias y candidato de acción."""
    builder = ProviderContextBuilder(default_max_tokens=2048, max_history_steps=5)
    ctx = builder.build(sample_session_state, sample_action)

    assert isinstance(ctx, ProviderContext)
    assert "Optimizar base de datos" in ctx.goal
    assert "índices creados" in ctx.success_criteria
    assert "esquema_actual_inspeccionado" in ctx.active_evidence
    assert ctx.candidate_action["id"] == "act_migrate"
    assert ctx.candidate_action["tool_name"] == "run_command"
    assert ctx.token_estimate > 0
    assert ctx.truncated is False

    # Probar serialización para backends LAYA y TypeSafe
    laya_payload = ctx.to_laya_payload()
    assert "candidate" in laya_payload
    assert "evidence" in laya_payload

    typesafe_payload = ctx.to_typesafe_payload()
    assert typesafe_payload["session_id"] == "test_provider_session"


def test_context_builder_truncation_detection(sample_session_state, sample_action):
    """Verifica que se detecte el truncado cuando el historial supera los límites de presupuesto."""
    # Añadir 15 pasos con observaciones largas
    for i in range(15):
        sample_session_state.add_step(
            action=ActionCandidate(
                id=f"step_{i}",
                description=f"Paso previo {i}",
                tool_call=ToolCall(tool_name="read_file", arguments={"path": f"file_{i}.txt"}),
            ),
            decision=PolicyDecision(status=DecisionStatus.ALLOW),
            observation="Observación detallada " * 30,  # Texto extenso
        )

    # Builder con ventana pequeña de historial y presupuesto estricto
    builder = ProviderContextBuilder(default_max_tokens=200, max_history_steps=3, max_obs_chars=50)
    ctx = builder.build(sample_session_state, sample_action, max_tokens=200)

    assert ctx.truncated is True
    assert len(ctx.history_window) <= 3
    assert ctx.token_estimate <= 200 + 50  # En el margen del presupuesto


# =========================================================================
# 2. Pruebas de LayaProvider (Choice, Score, Noul, Metadatos)
# =========================================================================

def test_laya_provider_primitives_and_metadata(sample_session_state, sample_action):
    """Verifica que LayaProvider genere las 3 primitivas y reporte metadatos completos."""
    provider = LayaProvider(backend="simulated", model_name="laya-v1-test")
    assert provider.is_available() is True
    assert provider.warmup() is True

    assessment = provider.evaluate_action(sample_session_state, sample_action)

    # Invariantes de evaluación
    assert assessment.provider == "laya"
    assert assessment.available is True
    assert 0.0 <= assessment.confidence <= 1.0
    assert 0.0 <= assessment.progress_probability <= 1.0
    assert 0.0 <= assessment.loop_probability <= 1.0
    assert 0.0 <= assessment.grounded_probability <= 1.0
    assert assessment.analytical_jev is not None

    # Metadatos de reproducibilidad
    meta = assessment.metadata
    assert meta["provider"] == "laya"
    assert meta["backend"] == "simulated"
    assert "latency_ms" in meta
    assert "context_tokens" in meta
    assert "choice" in meta
    assert "score" in meta
    assert "noul" in meta
    assert meta["choice"]["label"] in ("ALLOW", "REPLAN", "BLOCK", "ABSTAIN")


def test_laya_provider_detects_loop(sample_session_state):
    """Verifica que LAYA detecte estancamiento por herramientas reiteradas y emita REPLAN."""
    provider = LayaProvider(backend="simulated")

    # Simulamos repeticiones consecutivas de la misma herramienta sin progreso
    for i in range(4):
        sample_session_state.add_step(
            action=ActionCandidate(
                id=f"step_{i}",
                description="Reintentar lectura",
                tool_call=ToolCall(tool_name="read_file", arguments={"path": "same.txt"}),
            ),
            decision=PolicyDecision(status=DecisionStatus.ALLOW),
            observation="mismo contenido",
        )

    repeated_action = ActionCandidate(
        id="act_repeat",
        description="Reintentar lectura del mismo archivo por quinta vez",
        tool_call=ToolCall(tool_name="read_file", arguments={"path": "same.txt"}),
    )

    assessment = provider.evaluate_action(sample_session_state, repeated_action)
    assert assessment.loop_probability >= 0.70
    assert assessment.metadata["choice"]["label"] == "REPLAN"
    assert "LAYA_LOOP_PREVENTED" in assessment.reason_codes


def test_laya_provider_detects_missing_grounding(sample_session_state):
    """Verifica que LAYA detecte premisas no fundamentadas y reduzca grounded_probability."""
    provider = LayaProvider(backend="simulated")

    ungrounded_action = ActionCandidate(
        id="act_ungrounded",
        description="Modificar tabla con premisas alucinadas",
        tool_call=ToolCall(tool_name="edit_file", arguments={"path": "ghost.sql"}),
        requires_evidence=["tabla_fantasma_verificada"],
    )

    assessment = provider.evaluate_action(sample_session_state, ungrounded_action)
    assert assessment.grounded_probability <= 0.30
    assert assessment.metadata["choice"]["label"] == "REPLAN"
    assert "LAYA_UNGROUNDED_EVIDENCE" in assessment.reason_codes


# =========================================================================
# 3. Conformidad Multi-Provider (TypeSafe, LAYA, Replay)
# =========================================================================

@pytest.mark.parametrize(
    "provider",
    [
        TypeSafeAdapter(api_key=None),  # Offline test mode
        LayaProvider(backend="simulated"),
        ReplayProvider(default_scenario="safe_read"),
    ],
)
def test_all_providers_satisfy_reasoning_provider_contract(provider, sample_session_state, sample_action):
    """Verifica que todos los proveedores cumplan estrictamente el contrato de ProviderAssessment."""
    assessments = provider.evaluate(sample_session_state, [sample_action])
    assert isinstance(assessments, list)
    assert len(assessments) == 1

    ass = assessments[0]
    assert isinstance(ass, ProviderAssessment)
    assert isinstance(ass.available, bool)
    assert 0.0 <= ass.confidence <= 1.0

    if ass.available:
        if ass.progress_probability is not None:
            assert 0.0 <= ass.progress_probability <= 1.0
        if ass.loop_probability is not None:
            assert 0.0 <= ass.loop_probability <= 1.0
        if ass.grounded_probability is not None:
            assert 0.0 <= ass.grounded_probability <= 1.0


# =========================================================================
# 4. Gating de Confianza (JEV-as-a-Judge: Accept When Confident, Escalate When Unsure)
# =========================================================================

def test_policy_engine_escalates_on_low_confidence(sample_action):
    """Verifica que PolicyEngine escale a ABSTAIN si el provider reporta confianza por debajo del umbral."""
    policy = PolicyEngine(min_confidence_threshold=0.50)

    # Provider reporta un juicio con baja confianza (0.35 < 0.50)
    uncertain_assessment = ProviderAssessment(
        provider="laya",
        available=True,
        confidence=0.35,
        progress_probability=0.50,
        loop_probability=0.20,
        grounded_probability=0.80,
    )

    decision, receipt = policy.evaluate_action(
        action=sample_action,
        state={},
        available_evidence=[Evidence(id="ev_1", claim="esquema_actual_inspeccionado", content_hash="h1")],
        provider_assessment=uncertain_assessment,
    )

    # Debe escalar obligatoriamente a ABSTAIN
    assert decision.status == DecisionStatus.ABSTAIN
    assert any("LOW_PROVIDER_CONFIDENCE_ESCALATE" in r for r in decision.reason_codes)
    assert receipt.decision_status == DecisionStatus.ABSTAIN
