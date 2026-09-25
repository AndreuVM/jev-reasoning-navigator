"""Entidades de evaluación semántica de proveedores y análisis de riesgo operacional."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ProviderAssessment(BaseModel):
    """Juicio semántico multidimensional emitido por un ReasoningProvider (TypeSafe AI, LAYA o Replay)."""
    model_config = ConfigDict(frozen=True)

    provider: str
    model: Optional[str] = None
    available: bool = True
    confidence: float = 0.0
    loop_probability: Optional[float] = None
    grounded_probability: Optional[float] = None
    progress_probability: Optional[float] = None
    novelty_probability: Optional[float] = None
    analytical_jev: Optional[float] = None
    failure_reason: Optional[str] = None
    reason_codes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RiskLevel(str, Enum):
    """Nivel de severidad operacional de una acción."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskAssessment(BaseModel):
    """Evaluación objetiva del riesgo operacional de una herramienta."""
    model_config = ConfigDict(frozen=True)

    level: RiskLevel
    requires_confirmation: bool = False
    executable: bool = True
    destructive_potential: bool = False
    reasons: List[str] = Field(default_factory=list)
