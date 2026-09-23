"""Modelo de riesgo y registro formal de herramientas para v0.2."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from jev_navigator.domain.models import RiskAssessment, RiskLevel


class ToolSpec(BaseModel):
    """Especificación declarativa de riesgo y capacidades de una herramienta."""

    name: str
    category: str
    risk_level: RiskLevel = RiskLevel.LOW
    read_only: bool = False
    reversible: bool = True
    external_side_effect: bool = False
    destructive: bool = False
    requires_confirmation: bool = False
    description: Optional[str] = None


class ToolRegistry:
    """Registro extensible de herramientas con perfiles de riesgo explícitos."""

    def __init__(self, register_defaults: bool = True):
        self._tools: Dict[str, ToolSpec] = {}
        if register_defaults:
            self._register_default_tools()

    def register_tool(self, spec: ToolSpec) -> None:
        """Registra o actualiza la especificación de una herramienta."""
        self._tools[spec.name] = spec

    def register(self, spec: ToolSpec) -> None:
        """Alias conveniente para register_tool."""
        self.register_tool(spec)

    def get_tool(self, name: str) -> Optional[ToolSpec]:
        """Obtiene la especificación de una herramienta si está registrada."""
        return self._tools.get(name)

    def is_known(self, name: str) -> bool:
        """Verifica si la herramienta está registrada."""
        return name in self._tools

    def assess_risk(self, tool_name: Optional[str]) -> RiskAssessment:
        """Calcula el RiskAssessment objetivo para una herramienta invocada."""
        if not tool_name:
            # Pensamiento o reflexión interna sin herramienta física
            return RiskAssessment(
                level=RiskLevel.LOW,
                requires_confirmation=False,
                executable=True,
                reasons=["Paso puramente cognitivo (sin efectos colaterales)."],
            )

        spec = self._tools.get(tool_name)
        if not spec:
            return RiskAssessment(
                level=RiskLevel.CRITICAL,
                requires_confirmation=True,
                executable=False,
                reasons=[f"Herramienta desconocida '{tool_name}' no registrada en ToolRegistry."],
            )

        reasons: List[str] = []
        if spec.destructive:
            reasons.append(f"Herramienta destructiva ({spec.category}).")
        if spec.external_side_effect:
            reasons.append("Produce efectos secundarios externos.")
        if spec.requires_confirmation:
            reasons.append("Requiere confirmación humana/operacional.")

        return RiskAssessment(
            level=spec.risk_level,
            requires_confirmation=spec.requires_confirmation,
            executable=not spec.destructive or not spec.requires_confirmation,
            reasons=reasons or ["Herramienta dentro de parámetros de riesgo normales."],
        )

    def _register_default_tools(self) -> None:
        defaults = [
            ToolSpec(
                name="read_file",
                category="filesystem_read",
                risk_level=RiskLevel.LOW,
                read_only=True,
                reversible=True,
            ),
            ToolSpec(
                name="view_file",
                category="filesystem_read",
                risk_level=RiskLevel.LOW,
                read_only=True,
                reversible=True,
            ),
            ToolSpec(
                name="grep_search",
                category="filesystem_read",
                risk_level=RiskLevel.LOW,
                read_only=True,
                reversible=True,
            ),
            ToolSpec(
                name="edit_file",
                category="filesystem_write",
                risk_level=RiskLevel.MEDIUM,
                read_only=False,
                reversible=True,
            ),
            ToolSpec(
                name="run_command",
                category="shell",
                risk_level=RiskLevel.HIGH,
                read_only=False,
                reversible=False,
                external_side_effect=True,
            ),
            ToolSpec(
                name="delete_file",
                category="filesystem_destructive",
                risk_level=RiskLevel.CRITICAL,
                read_only=False,
                reversible=False,
                destructive=True,
                requires_confirmation=True,
            ),
            ToolSpec(
                name="finish",
                category="lifecycle",
                risk_level=RiskLevel.LOW,
                read_only=True,
                reversible=True,
            ),
        ]
        for spec in defaults:
            self.register_tool(spec)
