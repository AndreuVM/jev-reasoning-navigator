"""Reglas de permisos, confirmaciones y gobierno de ejecución (policy/permissions.py)."""

from typing import List, Optional, Set
from jev_navigator.domain.models import ActionCandidate, DecisionStatus, PolicyDecision, RiskAssessment, RiskLevel
from jev_navigator.policy.registry import ToolRegistry, ToolSpec


class PermissionManager:
    """Gestiona la autorización operacional de acciones según riesgo y confirmación del operador."""

    def __init__(self, registry: Optional[ToolRegistry] = None, require_confirmation_for_high_risk: bool = True):
        self.registry = registry or ToolRegistry(register_defaults=True)
        self.require_confirmation_for_high_risk = require_confirmation_for_high_risk
        self._confirmed_actions: Set[str] = set()

    def confirm_action(self, action_id: str) -> None:
        """Marca una acción como confirmada explícitamente por el operador humano."""
        self._confirmed_actions.add(action_id)

    def is_action_confirmed(self, action_id: str) -> bool:
        """Verifica si la acción cuenta con confirmación del operador."""
        return action_id in self._confirmed_actions

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
