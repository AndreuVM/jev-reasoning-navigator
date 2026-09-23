"""Modelos de dominio tipados para JEV Reasoning Navigator v0.2.

Define las entidades inmutables de objetivos, acciones, evidencia, evaluación de proveedores,
riesgo, decisiones de política y recibos de auditoría.
"""

from datetime import datetime
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class Goal(BaseModel):
    """Objetivo formal del agente con criterios de éxito verificables."""
    model_config = ConfigDict(frozen=True)

    objective: str
    success_criteria: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    forbidden_outcomes: List[str] = Field(default_factory=list)
    budget: Optional[float] = None
    deadline: Optional[datetime] = None


class ToolCall(BaseModel):
    """Llamada a herramienta física propuesta."""
    model_config = ConfigDict(frozen=True)

    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ActionCandidate(BaseModel):
    """Acción candidata propuesta por el agente sujeta a autorización."""
    model_config = ConfigDict(frozen=True)

    id: str
    description: str
    tool_call: Optional[ToolCall] = None
    rationale: Optional[str] = None
    requires_evidence: List[str] = Field(default_factory=list)
    estimated_cost: float = 0.0


class Evidence(BaseModel):
    """Pieza de evidencia observada en el entorno o suministrada por el usuario."""
    model_config = ConfigDict(frozen=True)

    id: str
    source_step_id: Optional[str] = None
    source_type: Literal["tool_observation", "user_input", "system", "external_source"] = "tool_observation"
    claim: str
    content_hash: str
    confidence: float = 1.0


class ProviderAssessment(BaseModel):
    """Juicio semántico puro emitido por un ReasoningProvider (ej. TypeSafe AI o Replay)."""
    model_config = ConfigDict(frozen=True)

    provider: str
    model: Optional[str] = None
    available: bool
    confidence: float = 0.0
    loop_probability: Optional[float] = None
    grounded_probability: Optional[float] = None
    progress_probability: Optional[float] = None
    novelty_probability: Optional[float] = None
    failure_reason: Optional[str] = None
    reason_codes: List[str] = Field(default_factory=list)


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
    reasons: List[str] = Field(default_factory=list)


class DecisionStatus(str, Enum):
    """Estados canónicos de decisión formal del supervisor."""
    ALLOW = "allow"      # La acción satisface las condiciones y está autorizada
    BLOCK = "block"      # Razón conocida o imperativo de seguridad para prohibir la acción
    REPLAN = "replan"    # La acción no es adecuada; se exige al agente replantear trayectoria
    ABSTAIN = "abstain"  # Incertidumbre del proveedor o falta de confirmación para autorizar


class PolicyDecision(BaseModel):
    """Decisión final consolidada por la PolicyEngine."""
    model_config = ConfigDict(frozen=True)

    status: DecisionStatus
    reason_codes: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    target_checkpoint: Optional[str] = None
    forbidden_tools: List[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    provider: Optional[ProviderAssessment] = None
    grounding: Optional[float] = None
    risk: Optional[RiskAssessment] = None


class DecisionReceipt(BaseModel):
    """Recibo criptográficamente auditable de una decisión de supervisión."""
    model_config = ConfigDict(frozen=True)

    decision_id: str
    session_id: str
    action_id: str
    decision: DecisionStatus
    state_hash: str
    action_hash: str
    latency_ms: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


def compute_action_hash(action: ActionCandidate) -> str:
    """Calcula un hash SHA-256 determinista para una acción candidata."""
    payload = {
        "id": action.id,
        "description": action.description,
        "tool_call": action.tool_call.model_dump() if action.tool_call else None,
        "requires_evidence": sorted(action.requires_evidence),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_state_hash(state_dict: Dict[str, Any]) -> str:
    """Calcula un hash SHA-256 determinista para el estado canónico."""
    canonical = json.dumps(state_dict, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
