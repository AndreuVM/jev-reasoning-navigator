"""Reglas de permisos, confirmaciones y gobierno de ejecución (policy/permissions.py)."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field
from jev_navigator.domain.models import ActionCandidate, DecisionStatus, PolicyDecision, RiskAssessment, RiskLevel
from jev_navigator.policy.registry import ToolRegistry, ToolSpec


class HumanApprovalTicket(BaseModel):
    """Ticket formal y auditable de autorización humana para acciones de riesgo."""
    model_config = ConfigDict(frozen=True)

    action_id: str
    action_hash: str
    approver_id: str = "operator"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    reason: Optional[str] = None
    signature: Optional[str] = None

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Comprueba si el ticket ha superado su ventana temporal de validez."""
        if self.expires_at is None:
            return False
        current_time = now or datetime.utcnow()
        return current_time > self.expires_at


class PermissionManager:
    """Gestiona la autorización operacional de acciones según riesgo y confirmación del operador."""

    def __init__(self, registry: Optional[ToolRegistry] = None, require_confirmation_for_high_risk: bool = True):
        self.registry = registry or ToolRegistry(register_defaults=True)
        self.require_confirmation_for_high_risk = require_confirmation_for_high_risk
        self._confirmed_actions: Set[str] = set()
        self._tickets: Dict[str, HumanApprovalTicket] = {}

    def grant_approval(self, ticket: HumanApprovalTicket) -> None:
        """Registra un ticket formal de aprobación emitido por un operador."""
        self._tickets[ticket.action_id] = ticket
        self._confirmed_actions.add(ticket.action_id)

    def confirm_action(
        self,
        action_id: str,
        action_hash: Optional[str] = None,
        approver_id: str = "operator",
        ttl_seconds: Optional[float] = 300.0,
        reason: Optional[str] = None,
    ) -> HumanApprovalTicket:
        """Marca una acción como confirmada explícitamente emitiendo un ticket auditable."""
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds) if ttl_seconds else None
        ticket = HumanApprovalTicket(
            action_id=action_id,
            action_hash=action_hash or "*",
            approver_id=approver_id,
            expires_at=expires_at,
            reason=reason,
        )
        self.grant_approval(ticket)
        return ticket

    def get_approval_ticket(self, action_id: str) -> Optional[HumanApprovalTicket]:
        """Recupera el ticket de aprobación asociado a una acción."""
        return self._tickets.get(action_id)

    def is_action_confirmed(self, action_id: str, action_hash: Optional[str] = None) -> bool:
        """Verifica si la acción cuenta con confirmación vigente y coincidente en hash."""
        ticket = self._tickets.get(action_id)
        if not ticket:
            return action_id in self._confirmed_actions
        if ticket.is_expired():
            return False
        if action_hash and ticket.action_hash != "*" and ticket.action_hash != action_hash:
            return False
        return True

    def check_permissions(
        self,
        action: ActionCandidate,
        risk: RiskAssessment,
        forbidden_tools: Optional[List[str]] = None,
    ) -> PolicyDecision:
        """Determina la autorización operacional de la herramienta candidata."""
        forbidden = forbidden_tools or []
        tool_name = action.tool_call.tool_name if action.tool_call else None

        # 1. Herramienta explícitamente prohibida en el estado
        if tool_name and tool_name in forbidden:
            return PolicyDecision(
                status=DecisionStatus.BLOCK,
                reason_codes=["FORBIDDEN_TOOL_RESTRAINT"],
                confidence=1.0,
                risk=risk,
            )

        # 2. Herramienta desconocida no registrada
        if tool_name and not self.registry.is_known(tool_name):
            return PolicyDecision(
                status=DecisionStatus.BLOCK,
                reason_codes=["UNKNOWN_TOOL_UNAUTHORIZED"],
                confidence=1.0,
                risk=risk,
            )

        # 3. Acción destructiva o crítica que requiere confirmación y aún no fue confirmada
        if risk.requires_confirmation and not self.is_action_confirmed(action.id):
            return PolicyDecision(
                status=DecisionStatus.ABSTAIN,
                reason_codes=["CONFIRMATION_REQUIRED"],
                confidence=1.0,
                requires_confirmation=True,
                risk=risk,
            )

        return PolicyDecision(
            status=DecisionStatus.ALLOW,
            reason_codes=["PERMISSIONS_CLEARED"],
            confidence=1.0,
            risk=risk,
        )
