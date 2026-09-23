"""Protocolos e interfaces abstractas del dominio para JEV Reasoning Navigator v0.2.

Garantiza el desacoplamiento total respecto a SDKs específicos como typesafe-sdk.
"""

from typing import Any, List, Protocol, runtime_checkable
from jev_navigator.domain.models import ActionCandidate, Evidence, ProviderAssessment


@runtime_checkable
class ReasoningProvider(Protocol):
    """Protocolo abstracto para proveedores de evaluación semántica (TypeSafe AI, Replay, etc.)."""

    def evaluate(
        self,
        state: Any,
        actions: List[ActionCandidate],
    ) -> List[ProviderAssessment]:
        """Evalúa semánticamente una lista de acciones candidatas bajo el estado actual."""
        ...


@runtime_checkable
class EvidenceProvider(Protocol):
    """Protocolo abstracto para consultar o verificar evidencia empírica."""

    def assess(
        self,
        state: Any,
        action: ActionCandidate,
    ) -> List[Evidence]:
        """Recupera la evidencia empírica que respalda una acción candidata."""
        ...


@runtime_checkable
class Executor(Protocol):
    """Protocolo abstracto para la ejecución física autorizada de herramientas."""

    def execute(
        self,
        action: ActionCandidate,
        state: Any,
    ) -> Any:
        """Ejecuta físicamente la herramienta autorizada y captura la observación resultante."""
        ...
