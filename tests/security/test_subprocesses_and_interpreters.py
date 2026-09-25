"""Pruebas de seguridad para ejecución de subprocesos, intérpretes y contención de herramientas (tests/security/test_subprocesses_and_interpreters.py)."""

import pytest
from praxeon.domain.models import ActionCandidate, DecisionStatus, Goal, RiskAssessment, RiskLevel, ToolCall
from praxeon.policy.permissions import PermissionManager
from praxeon.policy.registry import ToolRegistry
from praxeon.runtime.sandbox import LocalProcessSandbox, SandboxExecutionResult


def test_unregistered_tool_blocked_by_permission_manager():
    """Verifica que una herramienta no declarada en el catálogo formal sea bloqueada."""
    manager = PermissionManager(ToolRegistry(register_defaults=True))
    action = ActionCandidate(
        id="act_unknown",
        description="Try unregistered tool",
        tool_call=ToolCall(tool_name="spawn_reverse_shell", arguments={"ip": "1.2.3.4"}),
    )
    risk = RiskAssessment(
        level=RiskLevel.CRITICAL,
        score=1.0,
        factors=["unregistered"],
    )
    decision = manager.check_permissions(action, risk)
    assert decision.status == DecisionStatus.BLOCK
    assert "UNKNOWN_TOOL_UNAUTHORIZED" in decision.reason_codes


def test_sandbox_timeout_enforcement():
    """Verifica que un subproceso que exceda el tiempo límite sea terminado forzosamente."""
    import sys
    sandbox = LocalProcessSandbox()
    
    # Comando de espera larga según el sistema operativo
    if sys.platform == "win32":
        cmd = "Start-Sleep -Seconds 10"
    else:
        cmd = "sleep 10"

    res = sandbox.execute_command(cmd, timeout=0.5)
    assert res.success is False
    assert res.is_error is True
    assert res.exit_code == 124
    assert "Timeout superado" in res.output


def test_empty_command_handled_safely():
    """Verifica que un comando vacío no lance excepciones ni ejecute nada."""
    sandbox = LocalProcessSandbox()
    res = sandbox.execute_command("")
    assert res.success is False
    assert res.is_error is True
    assert "Comando vacío" in res.output
