"""Políticas de contingencia y fail-safe ante fallos o incertidumbre del supervisor."""

from pydantic import BaseModel, ConfigDict
from jev_navigator.domain.models import DecisionStatus, RiskAssessment, RiskLevel


class FailSafePolicy(BaseModel):
    """Configuración formal de comportamiento fail-safe.

    Principio operativo central:
    La caída o indisponibilidad de JEV/TypeSafe NUNCA debe convertirse
    accidentalmente en una señal favorable (ALLOW).
    """
    model_config = ConfigDict(frozen=True)

    allow_read_only_on_provider_failure: bool = False
    allow_low_risk_on_abstain: bool = False
    block_destructive_on_provider_failure: bool = True
    require_confirmation_external_side_effects: bool = True

    def resolve_provider_failure(self, risk: RiskAssessment, is_read_only: bool) -> DecisionStatus:
        """Determina la decisión ante indisponibilidad del proveedor."""
        # 1. Si la acción es destructiva o de riesgo crítico, bloqueo incondicional
        if self.block_destructive_on_provider_failure and (
            risk.level == RiskLevel.CRITICAL or not risk.executable
        ):
            return DecisionStatus.BLOCK

        # 2. Si la acción es de solo lectura y está habilitado el modo tolerante a fallos
        if self.allow_read_only_on_provider_failure and is_read_only and risk.level == RiskLevel.LOW:
            return DecisionStatus.ALLOW

        # 3. Por defecto ante caída del supervisor: abstención segura
        return DecisionStatus.ABSTAIN

    def resolve_uncertainty(self, risk: RiskAssessment) -> DecisionStatus:
        """Determina la decisión ante incertidumbre alta del proveedor."""
        if self.allow_low_risk_on_abstain and risk.level == RiskLevel.LOW and risk.executable:
            return DecisionStatus.ALLOW
        return DecisionStatus.ABSTAIN
