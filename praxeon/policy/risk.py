"""Modelo de riesgo y registro de herramientas (mantenido por compatibilidad).

Re-exporta ToolSpec, ToolRegistry, RiskLevel y RiskAssessment.
"""

from praxeon.domain.models import RiskAssessment, RiskLevel
from praxeon.policy.registry import ToolRegistry, ToolSpec

__all__ = ["ToolSpec", "ToolRegistry", "RiskLevel", "RiskAssessment"]
