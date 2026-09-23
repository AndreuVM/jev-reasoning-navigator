"""Modelo de riesgo y registro de herramientas (mantenido por compatibilidad).

Re-exporta ToolSpec, ToolRegistry, RiskLevel y RiskAssessment.
"""

from jev_navigator.domain.models import RiskAssessment, RiskLevel
from jev_navigator.policy.registry import ToolRegistry, ToolSpec

__all__ = ["ToolSpec", "ToolRegistry", "RiskLevel", "RiskAssessment"]
