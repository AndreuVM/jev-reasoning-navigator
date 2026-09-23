"""Clase base abstracta para proveedores de razonamiento semántico en v0.2."""

from abc import ABC, abstractmethod
from typing import Any, List
from jev_navigator.domain.models import ActionCandidate, ProviderAssessment


class BaseReasoningProvider(ABC):
    """Clase base para adaptadores de proveedores semánticos."""

    @abstractmethod
    def evaluate(
        self,
        state: Any,
        actions: List[ActionCandidate],
    ) -> List[ProviderAssessment]:
        """Evalúa semánticamente las acciones candidatas bajo el estado provisto."""
        pass
