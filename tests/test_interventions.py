"""Pruebas unitarias para Fase 4: Políticas de intervención y generación de directivas correctivas."""

import json
from pathlib import Path
import pytest

from jev_navigator.core.intervention_policy import InterventionPolicy
from jev_navigator.core.jev_engine import JEVEngine
from jev_navigator.core.state_graph import StateGraph
from jev_navigator.models.schema import (
    InterventionDirective,
    InterventionLevel,
    JEVScore,
    LoopReport,
    LoopType,
    Step,
    StepType,
    Trajectory,
)
from jev_navigator.models.trace import TraceParser

DATA_DIR = Path(__file__).parent.parent / "data" / "loop_traces"


def test_level_1_meta_feedback_intervention():
    """Verifica intervención Nivel 1 ante JEV negativo sin ciclo crítico."""
    graph = StateGraph()
    traj = Trajectory(session_id="s1", goal="Resolver bug", steps=[])
    graph.load_trajectory(traj)

    policy = InterventionPolicy(graph)
    jev_score = JEVScore(
        candidate_id="cand_1",
        p_progress=0.1,
        delta_u=0.0,
        loop_penalty=0.8,
        total_jev=-0.35,
    )

    directive = policy.evaluate_and_intervene(
        current_step=Step(id="s0", step_type=StepType.THOUGHT, content="Reintentar"),
        jev_score=jev_score,
        loop_report=LoopReport(loop_detected=False),
    )

    assert directive is not None
    assert directive.level == InterventionLevel.LEVEL_1_META_FEEDBACK
    assert "NIVEL 1 - META-FEEDBACK" in directive.message
    assert "<system_intervention level='1'>" in directive.context_injection


def test_level_2_forced_backtracking_on_tool_loop():
    """Verifica intervención Nivel 2 con poda forzada y prohibición de herramienta culpable."""
    graph = StateGraph()
    step_root = Step(id="s0", step_type=StepType.THOUGHT, content="Analizar los logs del sistema")
    graph.add_step(step_root)
    graph.set_step_jev("s0", 0.75)

    policy = InterventionPolicy(graph)
    loop_report = LoopReport(
        loop_detected=True,
        loop_type=LoopType.ONE_HOP_TOOL_REPEAT,
        severity=3,
        culprit_tool="run_command",
        explanation="Herramienta 'run_command' invocada 3 veces repetidamente",
    )

    directive = policy.evaluate_and_intervene(
        current_step=Step(id="s3", step_type=StepType.TOOL_CALL, tool_name="run_command"),
        loop_report=loop_report,
    )

    assert directive is not None
    assert directive.level == InterventionLevel.LEVEL_2_FORCED_BACKTRACKING
    assert directive.target_step_id == "s0"
    assert "run_command" in directive.forbidden_actions
    assert "<system_intervention level='2'" in directive.context_injection


def test_anti_hallucination_directive_generation():
    """Verifica generación de directiva específica ante alucinaciones detectadas por TypeSafe."""
    graph = StateGraph()
    policy = InterventionPolicy(graph)

    loop_report = LoopReport(
        loop_detected=True,
        loop_type=LoopType.HALLUCINATION,
        severity=4,
        explanation="Se alucinó la existencia de src/secret_config.json",
        culprit_tool="read_file",
    )

    directive = policy.evaluate_and_intervene(
        current_step=Step(id="s2", step_type=StepType.TOOL_CALL, tool_name="read_file"),
        loop_report=loop_report,
    )

    assert directive is not None
    assert directive.level == InterventionLevel.LEVEL_2_FORCED_BACKTRACKING
    assert "ANTI-ALUCINACIÓN" in directive.message
    assert "type='anti_hallucination'" in directive.context_injection


def test_level_3_abstraction_shift_on_entropic_stagnation():
    """Verifica intervención Nivel 3 con Abogado del Diablo ante estancamiento entrópico."""
    graph = StateGraph()
    policy = InterventionPolicy(graph)

    loop_report = LoopReport(
        loop_detected=True,
        loop_type=LoopType.ENTROPIC_STAGNATION,
        severity=2,
        explanation="Parálisis por análisis con pensamientos repetitivos",
    )

    directive = policy.evaluate_and_intervene(
        current_step=Step(id="s5", step_type=StepType.THOUGHT, content="Pensar más"),
        loop_report=loop_report,
    )

    assert directive is not None
    assert directive.level == InterventionLevel.LEVEL_3_ABSTRACTION_SHIFT
    assert "ABOGADO DEL DIABLO" in directive.message
    assert "devils_advocate" in directive.context_injection


def test_end_to_end_loop_interception_simulation():
    """Simulación: se diagnostica la traza y se verifica la intervención."""
    with open(DATA_DIR / "tool_loop.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    trajectory = TraceParser.from_dict(data)
    graph = StateGraph()
    graph.load_trajectory(trajectory)

    engine = JEVEngine(graph)
    # Simular diagnóstico de TypeSafe
    from unittest.mock import MagicMock
    engine.typesafe_client = MagicMock()
    engine.typesafe_client.diagnose_trajectory.return_value = LoopReport(
        loop_detected=True,
        loop_type=LoopType.ONE_HOP_TOOL_REPEAT,
        severity=3,
        culprit_tool="run_command",
        explanation="Reintento idéntico",
    )

    loop_report = engine.diagnose_trajectory(trajectory)
    assert loop_report.loop_detected is True

    policy = InterventionPolicy(graph)
    directive = policy.evaluate_and_intervene(
        current_step=trajectory.steps[-1],
        loop_report=loop_report,
    )

    assert directive is not None
    assert directive.level in (InterventionLevel.LEVEL_2_FORCED_BACKTRACKING, InterventionLevel.LEVEL_3_ABSTRACTION_SHIFT)
    assert loop_report.culprit_tool in directive.forbidden_actions
