"""Capa de Dominio de JEV Reasoning Navigator v0.2."""

from jev_navigator.domain.models import (
    Goal,
    ToolCall,
    ActionCandidate,
    Evidence,
    ProviderAssessment,
    RiskLevel,
    RiskAssessment,
    DecisionStatus,
    PolicyDecision,
    DecisionReceipt,
    compute_action_hash,
    compute_state_hash,
)
from jev_navigator.domain.interfaces import (
    ReasoningProvider,
    EvidenceProvider,
    Executor,
)

__all__ = [
    "Goal",
    "ToolCall",
    "ActionCandidate",
    "Evidence",
    "ProviderAssessment",
    "RiskLevel",
    "RiskAssessment",
    "DecisionStatus",
    "PolicyDecision",
    "DecisionReceipt",
    "compute_action_hash",
    "compute_state_hash",
    "ReasoningProvider",
    "EvidenceProvider",
    "Executor",
]
