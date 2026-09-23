"""Motor de políticas operacionales (PolicyEngine) para JEV Reasoning Navigator v0.2.

Aplica la separación estricta:
Semantic Judgment (JEV) != Operational Policy (PolicyEngine) != Physical Execution (Executor)
"""

import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
from jev_navigator.domain.models import (
    ActionCandidate,
    DecisionReceipt,
    DecisionStatus,
    Evidence,
    PolicyDecision,
    ProviderAssessment,
    RiskAssessment,
    RiskLevel,
    compute_action_hash,
    compute_state_hash,
)
from jev_navigator.policy.failsafe import FailSafePolicy
from jev_navigator.policy.risk import ToolRegistry


class PolicyEngine:
    """Combina señales semánticas, evidencia empírica, riesgo y fail-safe para emitir decisiones operacionales."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        failsafe: Optional[FailSafePolicy] = None,
        loop_threshold: float = 0.65,
        min_grounded_threshold: float = 0.35,
    ):
        self.registry = registry or ToolRegistry(register_defaults=True)
        self.failsafe = failsafe or FailSafePolicy()
        self.loop_threshold = loop_threshold
        self.min_grounded_threshold = min_grounded_threshold

    def evaluate_action(
        self,
        action: ActionCandidate,
        state: Dict[str, Any],
        provider_assessment: Optional[ProviderAssessment] = None,
        available_evidence: Optional[List[Evidence]] = None,
        forbidden_tools: Optional[Set[str]] = None,
        completion_assessment: Optional[Any] = None,
        session_id: str = "default_session",
    ) -> Tuple[PolicyDecision, DecisionReceipt]:
        """Evalúa una acción candidata emitiendo una decisión formal y su recibo auditable."""
        start_time = time.perf_counter()
        forbidden_tools = forbidden_tools or set()
        available_evidence = available_evidence or []
        evidence_claims = {ev.claim.lower().strip() for ev in available_evidence}

        tool_name = action.tool_call.tool_name if action.tool_call else None
        risk: RiskAssessment = self.registry.assess_risk(tool_name)
        spec = self.registry.get_tool(tool_name) if tool_name else None
        is_read_only = bool(spec.read_only) if spec else True

        reason_codes: List[str] = []
        status: Optional[DecisionStatus] = None

        # 1. Enforcement de herramientas prohibidas en el estado actual (Poda / Backtracking)
        if tool_name and tool_name in forbidden_tools:
            status = DecisionStatus.BLOCK
            reason_codes.append("TOOL_FORBIDDEN_BY_SUPERVISOR")

        # 2. Enforcement de herramientas desconocidas no registradas
        elif tool_name and not self.registry.is_known(tool_name):
            status = DecisionStatus.BLOCK
            reason_codes.append("UNKNOWN_TOOL_NOT_REGISTERED")

        # 3. Verificación formal de evidencia requerida (Groundedness estricto)
        elif action.requires_evidence:
            missing_evidence = [
                req for req in action.requires_evidence
                if req.lower().strip() not in evidence_claims
            ]
            if missing_evidence:
                status = DecisionStatus.REPLAN
                reason_codes.append(f"MISSING_REQUIRED_EVIDENCE: {', '.join(missing_evidence)}")

        # 3.5. Verificación formal de completitud ante intentos de finish
        elif completion_assessment is not None and not getattr(completion_assessment, "is_complete", True):
            status = DecisionStatus.REPLAN
            reasons = (
                getattr(completion_assessment, "missing_criteria", [])
                or getattr(completion_assessment, "unverified_claims", [])
                or [getattr(completion_assessment, "rationale", "")]
            )
            reason_codes.append(f"UNVERIFIED_COMPLETION: {', '.join(reasons)}")

        # 4. Evaluación de disponibilidad del proveedor (Fail-safe explícito)
        elif provider_assessment is not None and not provider_assessment.available:
            status = self.failsafe.resolve_provider_failure(risk, is_read_only)
            if status == DecisionStatus.BLOCK:
                reason_codes.append("PROVIDER_UNAVAILABLE_DESTRUCTIVE_BLOCK")
            else:
                reason_codes.append("PROVIDER_UNAVAILABLE_FAILSAFE_ABSTAIN")

        # 5. Evaluación semántica probabilística de JEV (si está disponible)
        elif provider_assessment is not None:
            # Detección de bucle o degradación cíclica
            if (
                provider_assessment.loop_probability is not None
                and provider_assessment.loop_probability >= self.loop_threshold
            ):
                status = DecisionStatus.REPLAN
                reason_codes.append(
                    f"HIGH_LOOP_PROBABILITY ({provider_assessment.loop_probability:.2f} >= {self.loop_threshold})"
                )

            # Detección de premisa no fundamentada o alucinación semántica
            elif (
                provider_assessment.grounded_probability is not None
                and provider_assessment.grounded_probability < self.min_grounded_threshold
            ):
                status = DecisionStatus.REPLAN
                reason_codes.append(
                    f"LOW_GROUNDED_PROBABILITY ({provider_assessment.grounded_probability:.2f} < {self.min_grounded_threshold})"
                )

        # 6. Evaluación de riesgo operacional
        if status is None:
            if risk.level == RiskLevel.CRITICAL:
                status = DecisionStatus.BLOCK
                reason_codes.append("CRITICAL_OPERATIONAL_RISK")
            elif risk.requires_confirmation:
                status = DecisionStatus.ABSTAIN
                reason_codes.append("HUMAN_CONFIRMATION_REQUIRED")

        # 7. Acción autorizada (ALLOW)
        if status is None:
            status = DecisionStatus.ALLOW
            reason_codes.append("GROUNDED_LOW_RISK_AUTHORIZED")

        confidence = provider_assessment.confidence if provider_assessment else 1.0
        grounding = provider_assessment.grounded_probability if provider_assessment else 1.0

        decision = PolicyDecision(
            status=status,
            reason_codes=reason_codes,
            confidence=confidence,
            forbidden_tools=list(forbidden_tools),
            requires_confirmation=risk.requires_confirmation,
            provider=provider_assessment,
            grounding=grounding,
            risk=risk,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        receipt = DecisionReceipt(
            decision_id=f"dec_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            action_id=action.id,
            decision=status,
            state_hash=compute_state_hash(state),
            action_hash=compute_action_hash(action),
            latency_ms=round(latency_ms, 2),
        )

        return decision, receipt
