"""Pruebas unitarias para TypeSafeAdapter en v0.2."""

import pytest
from unittest.mock import MagicMock
from jev_navigator.domain import ActionCandidate, ToolCall
from jev_navigator.providers import TypeSafeAdapter


def test_typesafe_adapter_offline_when_no_api_key():
    """Verifica que sin API key devuelva ProviderAssessment con available=False sin lanzar excepciones."""
    adapter = TypeSafeAdapter(api_key=None)
    # Asegurar que no tome variable del entorno
    adapter.api_key = None
    adapter._client = None

    actions = [
        ActionCandidate(
            id="a1",
            description="Leer archivo",
            tool_call=ToolCall(tool_name="read_file", arguments={"path": "main.py"}),
        )
    ]

    assessments = adapter.evaluate(state={}, actions=actions)
    assert len(assessments) == 1
    assessment = assessments[0]
    assert assessment.available is False
    assert assessment.confidence == 0.0
    assert "API_KEY_MISSING" in assessment.reason_codes


def test_typesafe_adapter_decodes_successful_response():
    """Verifica que una respuesta válida del SDK de TypeSafe se traduzca correctamente a ProviderAssessment."""
    adapter = TypeSafeAdapter(api_key="mock_test_key")

    mock_client = MagicMock()
    mock_noul = MagicMock()
    mock_noul.prob = 0.08
    mock_choice = MagicMock()
    mock_choice.choice = "none"
    mock_score = MagicMock()
    mock_score.score = 8.5

    mock_client.system_one.return_value = {
        "has_divergence_or_loop": mock_noul,
        "flagged_index": mock_choice,
        "progress_score": mock_score,
    }
    adapter._client = mock_client

    actions = [
        ActionCandidate(
            id="act_ok",
            description="Compilar proyecto",
            tool_call=ToolCall(tool_name="run_command", arguments={"command": "cargo check"}),
        )
    ]

    assessments = adapter.evaluate(state={"goal": "compilar"}, actions=actions)
    assert len(assessments) == 1
    assessment = assessments[0]

    assert assessment.available is True
    assert assessment.loop_probability == 0.08
    assert assessment.grounded_probability == 0.92
    assert assessment.progress_probability == 0.85
    assert "GROUNDED_PROGRESS" in assessment.reason_codes


def test_typesafe_adapter_handles_timeout_gracefully():
    """Verifica que un timeout de conexión resulte en available=False con reason_code=TIMEOUT."""
    adapter = TypeSafeAdapter(api_key="mock_test_key", max_retries=0)

    mock_client = MagicMock()
    mock_client.system_one.side_effect = TimeoutError("Gateway timeout 504")
    adapter._client = mock_client

    actions = [
        ActionCandidate(id="a_timeout", description="Acción con fallo de red")
    ]

    assessments = adapter.evaluate(state={}, actions=actions)
    assert len(assessments) == 1
    assessment = assessments[0]

    assert assessment.available is False
    assert "TIMEOUT" in assessment.reason_codes
    assert "Gateway timeout" in str(assessment.failure_reason)


def test_typesafe_adapter_flags_divergent_step():
    """Verifica que si TypeSafe señala un paso específico, se marque loop y alucinación."""
    adapter = TypeSafeAdapter(api_key="mock_test_key")

    mock_client = MagicMock()
    mock_noul = MagicMock()
    mock_noul.prob = 0.89
    mock_choice = MagicMock()
    mock_choice.choice = "step_0"
    mock_score = MagicMock()
    mock_score.score = 2.0

    mock_client.system_one.return_value = {
        "has_divergence_or_loop": mock_noul,
        "flagged_index": mock_choice,
        "progress_score": mock_score,
    }
    adapter._client = mock_client

    actions = [
        ActionCandidate(
            id="act_bad",
            description="Acción en bucle",
            tool_call=ToolCall(tool_name="read_file", arguments={"path": "invented.py"}),
        )
    ]

    assessments = adapter.evaluate(state={}, actions=actions)
    assert len(assessments) == 1
    assessment = assessments[0]

    assert assessment.available is True
    assert assessment.loop_probability >= 0.80
    assert assessment.grounded_probability <= 0.30
    assert "FLAGGED_BY_TYPESAFE_SYSTEM_ONE" in assessment.reason_codes
