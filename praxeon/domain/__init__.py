"""Paquete de dominio formal e inmutable para JEV Reasoning Navigator v0.2."""

from praxeon.domain.action import ActionCandidate, ToolCall, compute_action_hash
from praxeon.domain.assessment import ProviderAssessment, RiskAssessment, RiskLevel
from praxeon.domain.checkpoint import Checkpoint, ExecutionEnvironment
from praxeon.domain.decision import (
    DecisionReceipt,
    DecisionStatus,
    PolicyDecision,
    compute_receipt_signature,
    compute_state_hash,
    verify_receipt_signature,
)
from praxeon.domain.evidence import Claim, Evidence
from praxeon.domain.goal import CriterionType, Goal, SuccessCriterion
from praxeon.domain.interfaces import (
    CheckpointStore,
    CompletionVerifierProtocol,
    EvidenceStore,
    Executor,
    PolicyEngineProtocol,
    ReasoningProvider,
    StateStore,
)
from praxeon.domain.observation import Observation, ToolObservation
from praxeon.domain.state import StateSnapshot, StateStepRecord, TrajectoryState

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
    "ReasoningProvider",
    "Executor",
    "EvidenceStore",
    "CheckpointStore",
    "StateStore",
    "PolicyEngineProtocol",
    "CompletionVerifierProtocol",
]
