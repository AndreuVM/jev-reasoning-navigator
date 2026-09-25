"""Pruebas de seguridad para precedencia estricta de políticas y verificación de finish (tests/security/test_policy_precedence_and_finish.py)."""

import pytest
from praxeon.domain.assessment import ProviderAssessment
from praxeon.domain.goal import CriterionType, Goal, SuccessCriterion
from praxeon.domain.models import ActionCandidate, DecisionStatus, RiskAssessment, RiskLevel, ToolCall
from praxeon.policy.engine import PolicyEngine
from praxeon.reasoning.completion import CompletionVerifier, CriterionStatus
from praxeon.runtime.state import SessionState


def test_critical_risk_precedence_over_high_provider_jev():
    """Verifica que un score semántico perfecto (JEV 1.0) NUNCA autorice un comando destructivo."""
    engine = PolicyEngine()
    goal = Goal(objective="Optimize server")
    state = SessionState(session_id="prec_sess_1", goal=goal)

    action = ActionCandidate(
        id="act_high_jev_destructive",
        description="Clear disk space with rm -rf /",
        tool_call=ToolCall(tool_name="run_command", arguments={"command": "rm -rf /"}),
        requires_evidence=[],
    )

    # Evaluación entusiasta alucinada del proveedor (System-1 o LLM)
    high_jev_assessment = ProviderAssessment(
        provider="overenthusiastic-model",
        available=True,
        confidence=0.99,
        loop_probability=0.01,
        progress_score=0.99,
        reasoning="This will instantly free up 100% of disk space!",
    )

    decision, receipt = engine.evaluate_action(
        action=action,
        state=state.to_snapshot(),
        provider_assessment=high_jev_assessment,
        risk_assessment=RiskAssessment(level=RiskLevel.CRITICAL, score=1.0, factors=["destructive"]),
    )

    # PRECEDENCIA ABSOLUTA: RiskEngine / PolicyEngine bloquea
    assert decision.status == DecisionStatus.BLOCK
    assert "CRITICAL_OPERATIONAL_RISK" in decision.reason_codes
    assert receipt.decision_status == DecisionStatus.BLOCK


def test_missing_evidence_precedence_over_provider_allow():
    """Verifica que precondiciones de evidencia no satisfechas tengan precedencia sobre veredicto del proveedor."""
    engine = PolicyEngine()
    goal = Goal(objective="Update database")
    state = SessionState(session_id="prec_sess_2", goal=goal)

    action = ActionCandidate(
        id="act_missing_ev",
        description="Migrate database schema",
        tool_call=ToolCall(tool_name="edit_file", arguments={"path": "schema.sql", "content": "..."}),
        requires_evidence=["database backup confirmed verified"],
    )

    provider_assessment = ProviderAssessment(
        provider="test-provider",
        available=True,
        confidence=0.90,
        loop_probability=0.05,
        progress_score=0.90,
    )

    decision, _ = engine.evaluate_action(
        action=action,
        state=state.to_snapshot(),
        provider_assessment=provider_assessment,
        available_evidence=[],  # Sin evidencia del backup
    )

    assert decision.status == DecisionStatus.REPLAN
    assert any("MISSING_REQUIRED_EVIDENCE" in code for code in decision.reason_codes)


def test_premature_finish_rejected_when_criteria_unverified():
    """Verifica que la acción finish sea rechazada con REPLAN si los criterios obligatorios no están VERIFIED."""
    engine = PolicyEngine()
    goal = Goal(
        objective="Implement feature",
        success_criteria=["Tests unitarios pasando"],
    )
    state = SessionState(session_id="finish_sess", goal=goal)
    verifier = CompletionVerifier()

    finish_action = ActionCandidate(
        id="act_finish",
        description="Task completed successfully",
        tool_call=ToolCall(tool_name="finish", arguments={"summary": "Done!"}),
    )

    comp_assessment = verifier.verify(goal, state, finish_action)
    assert comp_assessment.is_complete is False

    decision, _ = engine.evaluate_action(
        action=finish_action,
        state=state.to_snapshot(),
        completion_assessment=comp_assessment,
    )

    assert decision.status == DecisionStatus.REPLAN
    assert any("UNVERIFIED_COMPLETION" in c for c in decision.reason_codes)
