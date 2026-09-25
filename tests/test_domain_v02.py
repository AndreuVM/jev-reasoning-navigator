"""Pruebas unitarias para la capa de dominio de JEV Reasoning Navigator v0.2."""

import pytest
from datetime import datetime
from praxeon.domain import (
    Goal,
    ToolCall,
    ActionCandidate,
    Evidence,
    ProviderAssessment,
    RiskLevel,
    RiskAssessment,
    DecisionStatus,
    PolicyDecision,
    DecisionReceipt,
    compute_action_hash,
    compute_state_hash,
)


def test_goal_creation_and_immutability():
    """Verifica que el modelo Goal sea inmutable y admita criterios de éxito."""
    goal = Goal(
        objective="Resolver issue #42",
        success_criteria=["todos los tests pasan", "cobertura > 90%"],
        constraints=["no modificar API pública"],
    )
    assert goal.objective == "Resolver issue #42"
    assert len(goal.success_criteria) == 2

    # Inmutabilidad (frozen)
    with pytest.raises(Exception):
        goal.objective = "Cambiar objetivo"  # type: ignore


def test_action_candidate_and_deterministic_hash():
    """Verifica que ActionCandidate genere un hash criptográfico determinista."""
    action1 = ActionCandidate(
        id="act_1",
        description="Leer archivo de configuración",
        tool_call=ToolCall(tool_name="read_file", arguments={"path": "pyproject.toml"}),
        requires_evidence=["file_exists"],
    )
    action2 = ActionCandidate(
        id="act_1",
        description="Leer archivo de configuración",
        tool_call=ToolCall(tool_name="read_file", arguments={"path": "pyproject.toml"}),
        requires_evidence=["file_exists"],
    )
    action_different = ActionCandidate(
        id="act_2",
        description="Editar configuración",
        tool_call=ToolCall(tool_name="edit_file", arguments={"path": "pyproject.toml"}),
    )

    hash1 = compute_action_hash(action1)
    hash2 = compute_action_hash(action2)
    hash_diff = compute_action_hash(action_different)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256
    assert hash1 != hash_diff


def test_state_hash_deterministic():
    """Verifica que compute_state_hash sea determinista con ordenamiento canónico de claves."""
    state_a = {"step": 3, "goal": "test", "files": ["a.py", "b.py"]}
    state_b = {"files": ["a.py", "b.py"], "step": 3, "goal": "test"}

    assert compute_state_hash(state_a) == compute_state_hash(state_b)


def test_provider_assessment_availability_field():
    """Verifica que ProviderAssessment distinga disponibilidad explícita."""
    online = ProviderAssessment(
        provider="typesafe",
        available=True,
        confidence=0.95,
        progress_probability=0.88,
    )
    assert online.available is True
    assert online.failure_reason is None

    offline = ProviderAssessment(
        provider="typesafe",
        available=False,
        failure_reason="Timeout 504",
        reason_codes=["TIMEOUT"],
    )
    assert offline.available is False
    assert offline.failure_reason == "Timeout 504"


def test_decision_receipt_creation():
    """Verifica la creación del recibo auditable DecisionReceipt."""
    receipt = DecisionReceipt(
        decision_id="dec_123",
        session_id="sess_abc",
        action_id="act_1",
        decision=DecisionStatus.ALLOW,
        state_hash="a" * 64,
        action_hash="b" * 64,
        latency_ms=12.5,
    )
    assert receipt.decision == DecisionStatus.ALLOW
    assert receipt.latency_ms == 12.5
    assert isinstance(receipt.timestamp, datetime)
