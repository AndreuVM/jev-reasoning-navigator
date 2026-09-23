"""Paquete de dominio formal e inmutable para JEV Reasoning Navigator v0.2."""

from jev_navigator.domain.action import ActionCandidate, ToolCall, compute_action_hash
from jev_navigator.domain.assessment import ProviderAssessment, RiskAssessment, RiskLevel
from jev_navigator.domain.checkpoint import Checkpoint, ExecutionEnvironment
from jev_navigator.domain.decision import (
    DecisionReceipt,
    DecisionStatus,
    PolicyDecision,
    compute_state_hash,
)
from jev_navigator.domain.evidence import Claim, Evidence
from jev_navigator.domain.goal import Goal
from jev_navigator.domain.interfaces import (
    CheckpointStore,
    CompletionVerifierProtocol,
    EvidenceStore,
    Executor,
    PolicyEngineProtocol,
    ReasoningProvider,
    StateStore,
)
from jev_navigator.domain.observation import Observation, ToolObservation
from jev_navigator.domain.state import StateSnapshot, StateStepRecord, TrajectoryState

__all__ = [
    "Goal",
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
