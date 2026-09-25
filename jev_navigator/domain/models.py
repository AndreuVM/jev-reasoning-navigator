"""Modelos de dominio tipados para JEV Reasoning Navigator v0.2.

Re-exporta todas las entidades puras e inmutables organizadas modularmente en el paquete domain.
"""

from jev_navigator.domain.action import ActionCandidate, ToolCall, compute_action_hash
from jev_navigator.domain.assessment import ProviderAssessment, RiskAssessment, RiskLevel
from jev_navigator.domain.checkpoint import Checkpoint, ExecutionEnvironment
from jev_navigator.domain.decision import (
    DecisionReceipt,
    DecisionStatus,
    PolicyDecision,
    compute_receipt_signature,
    compute_state_hash,
    verify_receipt_signature,
)
from jev_navigator.domain.evidence import Claim, Evidence
from jev_navigator.domain.goal import CriterionType, Goal, SuccessCriterion
from jev_navigator.domain.observation import Observation, ToolObservation
from jev_navigator.domain.state import StateSnapshot, StateStepRecord, TrajectoryState

__all__ = [
    "Goal",
    "CriterionType",
    "SuccessCriterion",
    "ToolCall",
    "ActionCandidate",
    "compute_action_hash",
    "Observation",
    "ToolObservation",
    "Evidence",
    "Claim",
    "ProviderAssessment",
    "RiskLevel",
    "RiskAssessment",
    "DecisionStatus",
    "PolicyDecision",
    "DecisionReceipt",
    "compute_receipt_signature",
    "verify_receipt_signature",
    "compute_state_hash",
    "Checkpoint",
    "ExecutionEnvironment",
    "StateSnapshot",
    "StateStepRecord",
    "TrajectoryState",
]
