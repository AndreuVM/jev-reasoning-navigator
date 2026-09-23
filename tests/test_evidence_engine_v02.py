"""Pruebas unitarias para EvidenceEngine en v0.2."""

from jev_navigator.domain import ActionCandidate, ToolCall
from jev_navigator.reasoning import EvidenceEngine


def test_evidence_ingestion_and_requirement_checking():
    """Verifica la ingestión de evidencia y la comprobación de precondiciones."""
    engine = EvidenceEngine()

    engine.ingest(claim="git_repo_clean", confidence=0.99)
    engine.ingest(claim="tests_passing", confidence=1.0)

    assert engine.has_evidence("git_repo_clean")
    assert engine.has_evidence("tests_passing")
    assert not engine.has_evidence("unrelated_claim")

    # Comprobación de requisitos satisfechos
    ok, missing = engine.check_requirements(["git_repo_clean", "tests_passing"])
    assert ok is True
    assert len(missing) == 0

    # Comprobación de requisitos con faltantes
    ok2, missing2 = engine.check_requirements(["git_repo_clean", "deployed_to_prod"])
    assert ok2 is False
    assert missing2 == ["deployed_to_prod"]


def test_evidence_ingest_from_read_file_observation():
    """Verifica que una lectura exitosa registre la existencia y lectura del archivo."""
    engine = EvidenceEngine()

    evidences = engine.ingest_from_observation(
        tool_name="read_file",
        tool_args={"path": "config.json"},
        observation='{"version": 1}',
        step_id="step_1",
    )

    assert len(evidences) == 2
    assert engine.has_evidence("file_exists:config.json")
    assert engine.has_evidence("file_read:config.json")


def test_evidence_invalidation_on_mutation():
    """Verifica que una mutación o borrado invalide automáticamente evidencias previas."""
    engine = EvidenceEngine()

    # 1. Leer archivo
    engine.ingest_from_observation(
        tool_name="read_file",
        tool_args={"path": "auth.py"},
        observation="def login(): pass",
    )
    assert engine.has_evidence("file_exists:auth.py")
    assert engine.has_evidence("file_read:auth.py")

    # 2. Borrar archivo
    invalidated = engine.ingest_from_observation(
        tool_name="delete_file",
        tool_args={"path": "auth.py"},
        observation="Archivo auth.py eliminado",
    )

    # El claim de que existía debe haber sido invalidado
    assert not engine.has_evidence("file_exists:auth.py")
    assert not engine.has_evidence("file_read:auth.py")
    assert engine.has_evidence("file_deleted:auth.py")
    assert len(engine.invalidation_history) > 0


def test_evidence_engine_implements_evidence_provider_protocol():
    """Verifica que EvidenceEngine cumpla el protocolo EvidenceProvider recuperando evidencias para una acción."""
    engine = EvidenceEngine()
    engine.ingest(claim="server_ready")

    action = ActionCandidate(
        id="act_deploy",
        description="Desplegar",
        requires_evidence=["server_ready", "nonexistent"],
    )

    ev_list = engine.assess(state={}, action=action)
    assert len(ev_list) == 1
    assert ev_list[0].claim == "server_ready"
