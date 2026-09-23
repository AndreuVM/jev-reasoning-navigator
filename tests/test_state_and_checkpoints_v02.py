"""Pruebas unitarias para SessionState, CheckpointManager y Rollback en v0.2."""

import pytest
from jev_navigator.domain import (
    ActionCandidate,
    DecisionStatus,
    Evidence,
    Goal,
    PolicyDecision,
    ToolCall,
)
from jev_navigator.runtime import CheckpointManager, SessionState


def test_session_state_creation_and_step_recording():
    """Verifica la creación de SessionState y el registro secuencial de pasos."""
    goal = Goal(objective="Refactorizar módulo auth", success_criteria=["tests pasan"])
    state = SessionState(session_id="sess_001", goal=goal)

    assert state.session_id == "sess_001"
    assert len(state.steps) == 0
    assert len(state.evidence) == 0
    assert len(state.forbidden_tools) == 0

    action = ActionCandidate(
        id="act_1",
        description="Leer auth.py",
        tool_call=ToolCall(tool_name="read_file", arguments={"path": "auth.py"}),
    )
    decision = PolicyDecision(status=DecisionStatus.ALLOW, reason_codes=["SAFE"])

    record = state.add_step(action=action, decision=decision, observation="def login(): pass")

    assert len(state.steps) == 1
    assert record.id == "step_0"
    assert record.index == 0
    assert record.action == action
    assert record.decision == decision
    assert record.observation == "def login(): pass"


def test_session_state_hash_determinism_and_mutation():
    """Verifica que el hash canónico del estado sea determinista y cambie ante mutaciones."""
    goal = Goal(objective="Test hash")
    state = SessionState(session_id="sess_hash", goal=goal)

    h1 = state.compute_hash()
    assert isinstance(h1, str)
    assert len(h1) == 64  # SHA-256 hex string

    # Mismo contenido debe dar idéntico hash
    assert state.compute_hash() == h1

    # Mutar pasos modifica el hash
    action = ActionCandidate(
        id="a1",
        description="test",
        tool_call=ToolCall(tool_name="read_file", arguments={}),
    )
    state.add_step(action, PolicyDecision(status=DecisionStatus.ALLOW))
    h2 = state.compute_hash()
    assert h2 != h1

    # Mutar forbidden_tools modifica el hash
    state.forbid_tool("dangerous_tool")
    h3 = state.compute_hash()
    assert h3 != h2


def test_session_state_evidence_deduplication():
    """Verifica que la evidencia con el mismo content_hash se deduplique en el estado."""
    state = SessionState(session_id="sess_ev", goal=Goal(objective="test"))

    ev1 = Evidence(
        id="ev_1",
        claim="Archivo config.yaml existe",
        content_hash="hash_abc123",
        source_type="tool_observation",
    )
    ev2 = Evidence(
        id="ev_2",
        claim="Archivo config.yaml existe (duplicado)",
        content_hash="hash_abc123",
        source_type="tool_observation",
    )

    state.add_evidence(ev1)
    assert len(state.evidence) == 1

    # Intentar añadir idéntico content_hash
    state.add_evidence(ev2)
    assert len(state.evidence) == 1


def test_session_state_snapshot_roundtrip():
    """Verifica serialización y deserialización fidedigna mediante snapshot."""
    state = SessionState(session_id="sess_snap", goal=Goal(objective="Snapshot test"))
    state.forbid_tool("rmdir")
    state.add_step(
        action=ActionCandidate(
            id="act_s",
            description="test step",
            tool_call=ToolCall(tool_name="list_dir", arguments={"path": "."}),
        ),
        decision=PolicyDecision(status=DecisionStatus.ALLOW),
        observation="file1.txt",
    )

    snapshot = state.to_snapshot()
    restored = SessionState.from_snapshot(snapshot)

    assert restored.session_id == state.session_id
    assert restored.goal.objective == state.goal.objective
    assert len(restored.steps) == 1
    assert restored.steps[0].action.tool_call.tool_name == "list_dir"
    assert "rmdir" in restored.forbidden_tools
    assert restored.compute_hash() == state.compute_hash()


def test_checkpoint_manager_create_and_retrieve():
    """Verifica la creación y obtención de checkpoints."""
    mgr = CheckpointManager()
    state = SessionState(session_id="sess_chk", goal=Goal(objective="Test chk"))

    chk1 = mgr.create_checkpoint(state, reason="Inicio de tarea")
    assert chk1.id.startswith("chk_")
    assert chk1.step_index == 0
    assert chk1.reason == "Inicio de tarea"
    assert chk1.id in state.checkpoint_ids

    assert mgr.get_checkpoint(chk1.id) == chk1
    assert mgr.get_latest_checkpoint() == chk1
    assert len(mgr.list_checkpoints()) == 1


def test_checkpoint_manager_rollback_workflow():
    """Verifica el flujo formal de rollback:
    restore_checkpoint -> invalidate_descendants -> forbid_failed_transition.
    """
    mgr = CheckpointManager()
    state = SessionState(session_id="sess_rb", goal=Goal(objective="Test rollback"))

    # Paso 1: Acción válida y checkpoint seguro
    state.add_step(
        action=ActionCandidate(
            id="step1",
            description="Paso 1 seguro",
            tool_call=ToolCall(tool_name="read_file", arguments={"path": "a.txt"}),
        ),
        decision=PolicyDecision(status=DecisionStatus.ALLOW),
    )
    safe_checkpoint = mgr.create_checkpoint(state, reason="Estado seguro tras paso 1")

    # Paso 2 y 3: Se adentra en un bucle repetitivo o acción errónea
    state.add_step(
        action=ActionCandidate(
            id="step2",
            description="Paso 2 repetido",
            tool_call=ToolCall(tool_name="grep_search", arguments={"query": "foo"}),
        ),
        decision=PolicyDecision(status=DecisionStatus.ALLOW),
    )
    state.add_step(
        action=ActionCandidate(
            id="step3",
            description="Paso 3 repetido",
            tool_call=ToolCall(tool_name="grep_search", arguments={"query": "foo"}),
        ),
        decision=PolicyDecision(status=DecisionStatus.ALLOW),
    )

    assert len(state.steps) == 3

    # Ejecutar rollback hacia el checkpoint seguro penalizando la herramienta causante
    restored_state = mgr.rollback(
        checkpoint_id=safe_checkpoint.id,
        current_state=state,
        culprit_tool="grep_search",
        reason="Bucle semántico detectado",
    )

    # 1. Los pasos degenerativos posteriores al checkpoint han sido descartados
    assert len(restored_state.steps) == 1
    assert restored_state.steps[0].id == "step_0"

    # 2. La herramienta culpable ha sido prohibida en el nuevo estado
    assert "grep_search" in restored_state.forbidden_tools

    # 3. Auditoría del rollback registrada
    assert len(mgr.rollback_history) == 1
    entry = mgr.rollback_history[0]
    assert entry["checkpoint_id"] == safe_checkpoint.id
    assert entry["discarded_steps_count"] == 2
    assert entry["culprit_tool"] == "grep_search"
    assert entry["reason"] == "Bucle semántico detectado"


def test_checkpoint_manager_rollback_nonexistent_raises():
    """Verifica que solicitar rollback a un checkpoint inexistente lance KeyError."""
    mgr = CheckpointManager()
    state = SessionState(session_id="sess_err", goal=Goal(objective="Err"))

    with pytest.raises(KeyError) as exc_info:
        mgr.rollback("chk_invalid_id", current_state=state)

    assert "no encontrado" in str(exc_info.value)
