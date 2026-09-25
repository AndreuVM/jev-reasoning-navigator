"""Pruebas unitarias para Fase 1: Esquemas, Parsers y StateGraph en NetworkX."""

import pytest
from praxeon.models.schema import Step, StepType, ActionCandidate, Trajectory
from praxeon.models.trace import TraceParser
from praxeon.core.state_graph import StateGraph


def test_step_schema_and_hashing():
    """Verifica la creación del paso y su hash semántico."""
    step1 = Step(
        id="step_1",
        step_type=StepType.TOOL_CALL,
        content="Consultar estado de la base de datos",
        tool_name="run_sql",
        tool_args={"query": "SELECT * FROM users;"},
    )
    assert step1.id == "step_1"
    assert step1.step_type == StepType.TOOL_CALL
    assert step1.semantic_hash is not None

    # Mismo contenido debe generar idéntico hash semántico
    step2 = Step(
        id="step_2",
        step_type=StepType.TOOL_CALL,
        content="Consultar estado de la base de datos",
        tool_name="run_sql",
        tool_args={"query": "SELECT * FROM users;"},
    )
    assert step1.semantic_hash == step2.semantic_hash


def test_trace_parser_from_scratchpad():
    """Verifica el parseo de un scratchpad tradicional en formato ReAct."""
    scratchpad = """
    Thought: Necesito revisar los archivos del repositorio para ubicar el bug.
    Action: list_directory
    Action Input: {"path": "./src"}
    Observation: main.py, utils.py, config.py
    Thought: Revisaré utils.py para ver la función de autenticación.
    Action: read_file
    Action Input: {"file": "./src/utils.py"}
    """
    trajectory = TraceParser.from_scratchpad(scratchpad, goal="Encontrar y corregir bug en autenticación")
    assert len(trajectory.steps) == 5
    assert trajectory.steps[0].step_type == StepType.THOUGHT
    assert trajectory.steps[1].step_type == StepType.TOOL_CALL
    assert trajectory.steps[1].tool_name == "list_directory"
    assert trajectory.steps[2].step_type == StepType.OBSERVATION
    assert trajectory.steps[3].step_type == StepType.THOUGHT
    assert trajectory.steps[4].step_type == StepType.TOOL_CALL
    assert trajectory.steps[4].tool_name == "read_file"


def test_trace_parser_from_openai_messages():
    """Verifica el parser para formato de mensajes de OpenAI."""
    messages = [
        {"role": "user", "content": "Compila el código en Rust y dime si hay errores."},
        {
            "role": "assistant",
            "content": "Voy a ejecutar cargo check.",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "run_command",
                        "arguments": '{"command": "cargo check"}',
                    },
                }
            ],
        },
        {"role": "tool", "content": "error[E0425]: cannot find value `x` in this scope"},
    ]
    trajectory = TraceParser.from_openai_messages(messages)
    assert trajectory.goal == "Compila el código en Rust y dime si hay errores."
    assert len(trajectory.steps) >= 3
    # Comprobar llamada a tool
    tool_steps = [s for s in trajectory.steps if s.step_type == StepType.TOOL_CALL]
    assert len(tool_steps) == 1
    assert tool_steps[0].tool_name == "run_command"
    assert tool_steps[0].tool_args == {"command": "cargo check"}


def test_state_graph_construction_and_topology():
    """Verifica que StateGraph construye el DAG con NetworkX y enlaza nodos cronológicamente."""
    graph = StateGraph()

    step0 = Step(id="s0", step_type=StepType.THOUGHT, content="Analizar el problema de conexión a la API")
    step1 = Step(id="s1", step_type=StepType.TOOL_CALL, content="", tool_name="curl", tool_args={"url": "https://api.test"})
    step2 = Step(id="s2", step_type=StepType.OBSERVATION, content="HTTP 500 Internal Server Error")

    trajectory = Trajectory(
        session_id="test_sess",
        goal="Solucionar fallo de conexión a API externa",
        steps=[step0, step1, step2],
    )

    graph.load_trajectory(trajectory)

    # Verificación de nodos en NetworkX
    assert graph.nodes_count == 3
    assert graph.edges_count >= 2  # Las 2 aristas temporales s0->s1 y s1->s2
    assert graph.get_chronological_nodes() == ["s0", "s1", "s2"]

    # Verificación de recuperación de pasos
    assert graph.get_step("s0").content == "Analizar el problema de conexión a la API"
    assert len(graph.get_recent_steps(2)) == 2


def test_state_graph_rollback_and_removal():
    """Verifica que remove_step elimina limpiamente el nodo y su orden cronológico."""
    graph = StateGraph()
    traj = Trajectory(
        session_id="rollback_test",
        goal="Reparar script",
        steps=[
            Step(id="s1", step_type=StepType.THOUGHT, content="Inicio"),
            Step(id="s2", step_type=StepType.TOOL_CALL, content="Paso a podar", tool_name="bad_tool"),
        ],
    )
    graph.load_trajectory(traj)
    assert graph.nodes_count == 2
    assert "s2" in graph.get_chronological_nodes()

    graph.remove_step("s2")
    assert graph.nodes_count == 1
    assert "s2" not in graph.get_chronological_nodes()
    assert graph.get_step("s2") is None
