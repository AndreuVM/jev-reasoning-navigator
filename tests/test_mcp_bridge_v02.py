"""Pruebas unitarias para la integración MCP v0.2 en MCPBridge."""

import io
import json
import sys
import pytest
from praxeon.domain import Goal
from praxeon.interceptor.mcp_bridge import MCPBridge
from praxeon.providers.replay import ReplayProvider
from praxeon.runtime import Navigator, SecureExecutor


@pytest.fixture
def test_bridge():
    """Crea una instancia de MCPBridge equipada con un Navigator determinista en dry_run."""
    provider = ReplayProvider(default_scenario="safe_read")
    executor = SecureExecutor(dry_run=True)
    nav = Navigator(provider=provider, executor=executor)
    return MCPBridge(navigator=nav)


def test_mcp_bridge_tools_list_contains_v1_and_v2(test_bridge):
    """Verifica que tools/list exponga tanto las herramientas v0.1 como las nuevas v0.2."""
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        test_bridge._handle_request({
            "jsonrpc": "2.0",
            "id": "list_1",
            "method": "tools/list",
            "params": {},
        })
        output = sys.stdout.getvalue().strip()
        data = json.loads(output)
        tools = data["result"]["tools"]
        tool_names = {t["name"] for t in tools}

        # Comprobar herramientas v0.1
        assert "jev_evaluate_next_step" in tool_names
        assert "jev_evaluate_step_chunk" in tool_names
        assert "jev_diagnose_trace" in tool_names

        # Comprobar herramientas v0.2
        assert "jev_v2_start_session" in tool_names
        assert "jev_v2_evaluate_action" in tool_names
        assert "jev_v2_step_and_execute" in tool_names
        assert "jev_v2_rollback" in tool_names
        assert "jev_v2_get_session_state" in tool_names
    finally:
        sys.stdout = old_stdout


def test_mcp_bridge_v2_session_and_evaluation_flow(test_bridge):
    """Verifica el ciclo de vida de sesión y evaluación v0.2 a través del bridge."""
    # 1. Iniciar sesión
    sess_res = test_bridge.v2_start_session(
        goal={"objective": "Test MCP", "success_criteria": ["criterio ok"]},
        session_id="mcp_test_01",
    )
    assert sess_res["session_id"] == "mcp_test_01"
    assert "state_hash" in sess_res
    assert sess_res["checkpoints_count"] == 1

    # 2. Evaluar acción candidata
    eval_res = test_bridge.v2_evaluate_action(
        action={
            "id": "act_mcp_1",
            "description": "Leer archivo",
            "tool_call": {"tool_name": "read_file", "arguments": {"path": "test.txt"}},
        }
    )
    assert eval_res["decision"]["status"] == "allow"
    assert eval_res["receipt"]["action_id"] == "act_mcp_1"

    # 3. Ejecutar acción
    step_res = test_bridge.v2_step_and_execute(
        action={
            "id": "act_mcp_1",
            "description": "Leer archivo",
            "tool_call": {"tool_name": "read_file", "arguments": {"path": "test.txt"}},
        }
    )
    assert step_res["decision"]["status"] == "allow"
    assert step_res["observation"]["success"] is True
    assert "[DRY-RUN]" in step_res["observation"]["output"]

    # 4. Consultar estado
    state_res = test_bridge.v2_get_session_state()
    assert state_res["active"] is True
    assert len(state_res["state"]["steps"]) == 1


def test_mcp_bridge_v2_rollback_flow(test_bridge):
    """Verifica la invocación de rollback a través de las herramientas MCP."""
    test_bridge.v2_start_session(goal="Prueba rollback")

    # Paso seguro
    test_bridge.v2_step_and_execute(
        action={"tool_name": "read_file", "tool_args": {"path": "safe.txt"}}
    )
    chk = test_bridge.navigator.checkpoint_manager.create_checkpoint(
        test_bridge.navigator.state, reason="Punto de prueba"
    )

    # Paso posterior
    test_bridge.v2_step_and_execute(
        action={"tool_name": "run_command", "tool_args": {"command": "dir"}}
    )
    assert len(test_bridge.navigator.state.steps) == 2

    # Invocar rollback via bridge
    rb_res = test_bridge.v2_rollback(
        checkpoint_id=chk.id,
        culprit_tool="run_command",
        reason="Fallo en comando",
    )
    assert rb_res["restored_step_count"] == 1
    assert "run_command" in rb_res["forbidden_tools"]


def test_mcp_bridge_json_rpc_tools_call_dispatch(test_bridge):
    """Verifica que el dispatcher JSON-RPC en _handle_request responda a jev_v2_*."""
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        # Iniciar sesión via JSON-RPC
        test_bridge._handle_request({
            "jsonrpc": "2.0",
            "id": "rpc_1",
            "method": "tools/call",
            "params": {
                "name": "jev_v2_start_session",
                "arguments": {"goal": "Objetivo JSON-RPC"},
            },
        })
        output = sys.stdout.getvalue().strip()
        data = json.loads(output)
        content_text = data["result"]["content"][0]["text"]
        parsed = json.loads(content_text)
        assert "session_id" in parsed
        assert "state_hash" in parsed
    finally:
        sys.stdout = old_stdout
