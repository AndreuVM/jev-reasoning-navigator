"""Pruebas unitarias para RiskEngine en v0.2."""

from jev_navigator.domain import ActionCandidate, RiskLevel, ToolCall
from jev_navigator.reasoning import RiskEngine


def test_risk_engine_pure_cognitive_step():
    """Verifica que un paso puramente reflexivo sea clasificado con riesgo LOW."""
    engine = RiskEngine()
    action = ActionCandidate(
        id="act_thought",
        description="Analizar arquitectura mentalmente",
        tool_call=None,
    )
    assessment = engine.assess_action_risk(action)
    assert assessment.level == RiskLevel.LOW
    assert assessment.executable is True
    assert assessment.requires_confirmation is False


def test_risk_engine_safe_shell_commands():
    """Verifica que comandos de inspección conocidos (dir, git status, pytest) se evalúen como LOW risk."""
    engine = RiskEngine()

    safe_commands = ["dir", "git status", "pytest -v", "python --version"]
    for cmd in safe_commands:
        action = ActionCandidate(
            id="act_safe",
            description=f"Ejecutar {cmd}",
            tool_call=ToolCall(tool_name="run_command", arguments={"command": cmd}),
        )
        assessment = engine.assess_action_risk(action)
        assert assessment.level == RiskLevel.LOW
        assert assessment.executable is True


def test_risk_engine_flags_destructive_shell_patterns():
    """Verifica que comandos destructivos (rm -rf, del /f /s, drop table) se clasifiquen como CRITICAL."""
    engine = RiskEngine()

    destructive_commands = [
        "rm -rf /var/data",
        "del /f /q /s C:\\Windows\\temp",
        "rmdir /s /q test_dir",
        "DROP DATABASE production;",
        "chmod -R 777 /app",
    ]

    for cmd in destructive_commands:
        action = ActionCandidate(
            id="act_destruct",
            description=f"Ejecutar comando peligroso: {cmd}",
            tool_call=ToolCall(tool_name="run_command", arguments={"command": cmd}),
        )
        assessment = engine.assess_action_risk(action)
        assert assessment.level == RiskLevel.CRITICAL
        assert assessment.executable is False
        assert assessment.requires_confirmation is True
        assert any("destructivo" in r.lower() for r in assessment.reasons)


def test_risk_engine_protects_sensitive_files():
    """Verifica que intentar mutar o leer archivos protegidos (.env, .git) eleve severamente el riesgo."""
    engine = RiskEngine()

    # Intentar editar .env
    action_edit_env = ActionCandidate(
        id="act_env",
        description="Modificar variables de entorno",
        tool_call=ToolCall(tool_name="edit_file", arguments={"path": ".env"}),
    )
    assessment_edit = engine.assess_action_risk(action_edit_env)
    assert assessment_edit.level == RiskLevel.CRITICAL
    assert assessment_edit.requires_confirmation is True
    assert assessment_edit.executable is False

    # Intentar leer .env (se eleva de LOW a HIGH)
    action_read_env = ActionCandidate(
        id="act_read_env",
        description="Leer variables secretas",
        tool_call=ToolCall(tool_name="read_file", arguments={"path": ".env"}),
    )
    assessment_read = engine.assess_action_risk(action_read_env)
    assert assessment_read.level == RiskLevel.HIGH
