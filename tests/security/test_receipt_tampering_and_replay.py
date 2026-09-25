"""Pruebas de seguridad contra manipulación de recibos y replay attacks (tests/security/test_receipt_tampering_and_replay.py)."""

from datetime import datetime, timedelta
import tempfile
import pytest
from praxeon.domain.action import compute_action_hash
from praxeon.domain.decision import (
    compute_state_hash,
    DecisionReceipt,
    DecisionStatus,
    PolicyDecision,
    sign_receipt,
)
from praxeon.domain.models import ActionCandidate, Goal, RiskAssessment, RiskLevel, ToolCall
from praxeon.runtime.executor import PolicyViolation, SecureExecutor
from praxeon.runtime.nonce_store import InMemoryNonceStore, SqliteNonceStore
from praxeon.runtime.state import SessionState


@pytest.fixture
def base_setup():
    goal = Goal(objective="Test security")
    state = SessionState(session_id="sec_sess_1", goal=goal)
    action = ActionCandidate(
        id="act_1",
        description="Safe test read",
        tool_call=ToolCall(tool_name="read_file", arguments={"path": "test.txt"}),
    )
    secret_key = "top-secret-signing-key-for-test"
    executor = SecureExecutor(dry_run=True, secret_key=secret_key)
    return goal, state, action, secret_key, executor


def test_missing_receipt_raises_policy_violation(base_setup):
    """Verifica que ejecutar sin capability/receipt sea rechazado inmediatamente."""
    _, state, action, _, executor = base_setup
    with pytest.raises(PolicyViolation) as exc_info:
        executor.execute(action=action, state=state, receipt=None)
    assert "Se requiere un capability/DecisionReceipt" in str(exc_info.value)


def test_block_or_replan_receipt_rejected(base_setup):
    """Verifica que un recibo emitido con status BLOCK o REPLAN no sea ejecutable."""
    _, state, action, secret_key, executor = base_setup
    a_hash = compute_action_hash(action)
    s_hash = compute_state_hash(state)
    receipt = DecisionReceipt(
        decision_id="dec_block",
        action_id=action.id,
        action_hash=a_hash,
        state_hash=s_hash,
        session_id=state.session_id,
        decision_status=DecisionStatus.BLOCK,
    )
    receipt = sign_receipt(receipt, secret_key)

    with pytest.raises(PolicyViolation) as exc_info:
        executor.execute(action=action, state=state, receipt=receipt)
    assert "estatus no autorizado" in str(exc_info.value)


def test_tampered_action_hash_rejected(base_setup):
    """Verifica que modificar los argumentos de la acción invalide el recibo."""
    _, state, action, secret_key, executor = base_setup
    s_hash = compute_state_hash(state)
    receipt = DecisionReceipt(
        decision_id="dec_tampered_action",
        action_id=action.id,
        action_hash="forged_action_hash_value",
        state_hash=s_hash,
        session_id=state.session_id,
        decision_status=DecisionStatus.ALLOW,
    )
    receipt = sign_receipt(receipt, secret_key)

    with pytest.raises(PolicyViolation) as exc_info:
        executor.execute(action=action, state=state, receipt=receipt)
    assert "no coincide con el capability" in str(exc_info.value)


def test_tampered_state_hash_rejected(base_setup):
    """Verifica que un cambio no autorizado en el estado invalide el recibo."""
    _, state, action, secret_key, executor = base_setup
    a_hash = compute_action_hash(action)
    receipt = DecisionReceipt(
        decision_id="dec_tampered_state",
        action_id=action.id,
        action_hash=a_hash,
        state_hash="forged_state_hash_value",
        session_id=state.session_id,
        decision_status=DecisionStatus.ALLOW,
    )
    receipt = sign_receipt(receipt, secret_key)

    with pytest.raises(PolicyViolation) as exc_info:
        executor.execute(action=action, state=state, receipt=receipt)
    assert "desfasado" in str(exc_info.value)


def test_invalid_hmac_signature_rejected(base_setup):
    """Verifica que un recibo firmado con una clave distinta o manipulado sea rechazado."""
    _, state, action, _, executor = base_setup
    a_hash = compute_action_hash(action)
    s_hash = compute_state_hash(state)
    receipt = DecisionReceipt(
        decision_id="dec_bad_hmac",
        action_id=action.id,
        action_hash=a_hash,
        state_hash=s_hash,
        session_id=state.session_id,
        decision_status=DecisionStatus.ALLOW,
        signature="invalid_hmac_sha256_hex_digest",
    )

    with pytest.raises(PolicyViolation) as exc_info:
        executor.execute(action=action, state=state, receipt=receipt)
    assert "firma HMAC del capability es inválida" in str(exc_info.value)


def test_expired_receipt_rejected(base_setup):
    """Verifica que un recibo caducado en el tiempo sea rechazado."""
    _, state, action, secret_key, executor = base_setup
    a_hash = compute_action_hash(action)
    s_hash = compute_state_hash(state)
    past_time = datetime.utcnow() - timedelta(seconds=10)
    receipt = DecisionReceipt(
        decision_id="dec_expired",
        action_id=action.id,
        action_hash=a_hash,
        state_hash=s_hash,
        session_id=state.session_id,
        decision_status=DecisionStatus.ALLOW,
        expires_at=past_time,
    )
    receipt = sign_receipt(receipt, secret_key)

    with pytest.raises(PolicyViolation) as exc_info:
        executor.execute(action=action, state=state, receipt=receipt)
    assert "ha expirado" in str(exc_info.value)


def test_cross_session_receipt_reuse_rejected(base_setup):
    """Verifica que un recibo generado para la sesión A no pueda usarse en la sesión B."""
    goal, state_a, action, secret_key, executor = base_setup
    state_b = SessionState(session_id="sec_sess_2", goal=goal)

    a_hash = compute_action_hash(action)
    s_hash_a = compute_state_hash(state_a)
    receipt = DecisionReceipt(
        decision_id="dec_cross_session",
        action_id=action.id,
        action_hash=a_hash,
        state_hash=s_hash_a,
        session_id=state_a.session_id,
        decision_status=DecisionStatus.ALLOW,
    )
    receipt = sign_receipt(receipt, secret_key)

    with pytest.raises(PolicyViolation) as exc_info:
        executor.execute(action=action, state=state_b, receipt=receipt)
    assert "desfasado" in str(exc_info.value) or "no coincide" in str(exc_info.value)


def test_replay_attack_prevention_memory(base_setup):
    """Verifica que reutilizar un recibo en memoria falle de inmediato."""
    _, state, action, secret_key, executor = base_setup
    a_hash = compute_action_hash(action)
    s_hash = compute_state_hash(state)
    receipt = DecisionReceipt(
        decision_id="dec_replay_1",
        action_id=action.id,
        action_hash=a_hash,
        state_hash=s_hash,
        session_id=state.session_id,
        decision_status=DecisionStatus.ALLOW,
        nonce="nonce_unique_12345",
    )
    receipt = sign_receipt(receipt, secret_key)

    # Primera ejecución: autorizada
    obs = executor.execute(action=action, state=state, receipt=receipt)
    assert obs.success is True

    # Replay: segundo intento con el mismo capability
    with pytest.raises(PolicyViolation) as exc_info:
        executor.execute(action=action, state=state, receipt=receipt)
    assert "Replay attack prevention" in str(exc_info.value) or "ya ha sido consumido" in str(exc_info.value)


def test_replay_attack_prevention_sqlite_durable():
    """Verifica que SqliteNonceStore prevenga replay attacks persistiendo a través de reinicios."""
    import os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    tf.close()

    try:
        store1 = SqliteNonceStore(db_path=db_path)
        goal = Goal(objective="Durable replay test")
        state = SessionState(session_id="sess_sqlite", goal=goal)
        action = ActionCandidate(
            id="act_durable",
            description="Read file",
            tool_call=ToolCall(tool_name="read_file", arguments={"path": "hello.txt"}),
        )
        secret_key = "sqlite-secret"
        executor1 = SecureExecutor(dry_run=True, secret_key=secret_key, nonce_store=store1)

        a_hash = compute_action_hash(action)
        s_hash = compute_state_hash(state)
        receipt = DecisionReceipt(
            decision_id="dec_durable_replay",
            action_id=action.id,
            action_hash=a_hash,
            state_hash=s_hash,
            session_id=state.session_id,
            decision_status=DecisionStatus.ALLOW,
            nonce="nonce_durable_999",
        )
        receipt = sign_receipt(receipt, secret_key)

        # Ejecución en proceso 1
        obs = executor1.execute(action=action, state=state, receipt=receipt)
        assert obs.success is True

        # Simular reinicio creando una nueva instancia del store apuntando a la misma base de datos
        store2 = SqliteNonceStore(db_path=db_path)
        executor2 = SecureExecutor(dry_run=True, secret_key=secret_key, nonce_store=store2)

        # Intento de replay tras reinicio
        with pytest.raises(PolicyViolation) as exc_info:
            executor2.execute(action=action, state=state, receipt=receipt)
        assert "Replay attack prevention" in str(exc_info.value) or "ya ha sido consumido" in str(exc_info.value)
    finally:
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
        except Exception:
            pass

