"""Registro tipado de herramientas (ToolRegistry) y descriptores intrínsecos (ToolSpec) para v0.2.

Sustituye heurísticas hardcodeadas de strings por inspección de descriptores:
- Categoría (inspection, mutation, system, network)
- Nivel de riesgo (LOW, MEDIUM, HIGH, CRITICAL)
- Reversibilidad
- Efectos colaterales externos
- Permisos de lectura exclusiva (read_only)
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from praxeon.domain.models import RiskAssessment, RiskLevel


class ToolSpec(BaseModel):
    """Especificación declarativa de riesgo y capacidades intrínsecas de una herramienta."""

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

    def is_observational(self, name: str, tool_args: Optional[Dict[str, Any]] = None) -> bool:
        """Determina si la herramienta o comando es puramente observacional / de lectura."""
        if name in ("read_file", "view_file", "list_dir", "grep_search", "search_web"):
            return True
        if name == "run_command" and tool_args:
            cmd = str(tool_args.get("command") or "").strip().lower()
            read_only_prefixes = (
                "ls", "dir", "type ", "cat ", "head ", "tail ", "get-content",
                "git status", "git log", "git diff", "git show", "git branch", "git tag",
                "find ", "findstr ", "grep ", "pwd", "echo ", "where ", "which ",
                "python --version", "python -v"
            )
            if any(cmd == p.strip() or cmd.startswith(p) for p in read_only_prefixes):
                return True
        spec = self._tools.get(name)
        if not spec:
            return False
        return spec.read_only and not spec.external_side_effect

    def assess_risk(self, tool_name: Optional[str]) -> RiskAssessment:
        """Calcula el RiskAssessment objetivo para una herramienta invocada."""
        if not tool_name:
            # Paso puramente cognitivo (pensamiento interno)
            return RiskAssessment(
                level=RiskLevel.LOW,
                requires_confirmation=False,
                executable=True,
                destructive_potential=False,
                reasons=["Paso puramente cognitivo (sin efectos colaterales)."],
            )

        spec = self._tools.get(tool_name)
        if not spec:
            return RiskAssessment(
                level=RiskLevel.CRITICAL,
                requires_confirmation=True,
                executable=False,
                destructive_potential=True,
                reasons=[f"Herramienta no registrada ni autorizada: '{tool_name}'."],
            )

        reasons = [f"Herramienta registrada en categoría '{spec.category}' con nivel '{spec.risk_level.value}'."]
        if spec.destructive:
            reasons.append("La herramienta tiene potencial destructivo sobre datos o archivos.")
        if spec.external_side_effect:
            reasons.append("La herramienta genera efectos colaterales externos no reversibles.")

        return RiskAssessment(
            level=spec.risk_level,
            requires_confirmation=spec.requires_confirmation or (spec.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)),
            executable=not spec.destructive or spec.requires_confirmation,
            destructive_potential=spec.destructive,
            reasons=reasons,
        )

    def _register_default_tools(self) -> None:
        """Registra las herramientas estándar del ecosistema con sus descriptores de seguridad."""
        defaults = [
            # Lectura e inspección segura (read-only, reversible, low risk)
            ToolSpec(
                name="read_file",
                category="inspection",
                risk_level=RiskLevel.LOW,
                read_only=True,
                reversible=True,
                external_side_effect=False,
                description="Lee el contenido de un archivo en disco.",
            ),
            ToolSpec(
                name="view_file",
                category="inspection",
                risk_level=RiskLevel.LOW,
                read_only=True,
                reversible=True,
                external_side_effect=False,
                description="Visualiza el contenido de un archivo local.",
            ),
            ToolSpec(
                name="list_dir",
                category="inspection",
                risk_level=RiskLevel.LOW,
                read_only=True,
                reversible=True,
                external_side_effect=False,
                description="Lista los archivos en un directorio.",
            ),
            ToolSpec(
                name="grep_search",
                category="inspection",
                risk_level=RiskLevel.LOW,
                read_only=True,
                reversible=True,
                external_side_effect=False,
                description="Búsqueda de patrones en archivos.",
            ),
            ToolSpec(
                name="search_web",
                category="inspection",
                risk_level=RiskLevel.LOW,
                read_only=True,
                reversible=True,
                external_side_effect=False,
                description="Búsqueda informativa en la web.",
            ),
            # Finalización de tarea (supervisada por CompletionVerifier)
            ToolSpec(
                name="finish",
                category="lifecycle",
                risk_level=RiskLevel.LOW,
                read_only=True,
                reversible=True,
                external_side_effect=False,
                description="Declara la culminación de la tarea del agente.",
            ),
            # Mutaciones moderadas (edición/creación de archivos)
            ToolSpec(
                name="write_to_file",
                category="mutation",
                risk_level=RiskLevel.MEDIUM,
                read_only=False,
                reversible=True,
                external_side_effect=False,
                description="Crea o sobrescribe un archivo.",
            ),
            ToolSpec(
                name="replace_file_content",
                category="mutation",
                risk_level=RiskLevel.MEDIUM,
                read_only=False,
                reversible=True,
                external_side_effect=False,
                description="Reemplaza un fragmento de texto en un archivo.",
            ),
            ToolSpec(
                name="edit_file",
                category="mutation",
                risk_level=RiskLevel.MEDIUM,
                read_only=False,
                reversible=True,
                external_side_effect=False,
                description="Edita contenido de un archivo.",
            ),
            # Comandos del sistema (alto riesgo o crítico según contenido)
            ToolSpec(
                name="run_command",
                category="system",
                risk_level=RiskLevel.HIGH,
                read_only=False,
                reversible=False,
                external_side_effect=True,
                description="Ejecuta comandos de shell en el sistema operativo.",
            ),
            # Destructivas críticas
            ToolSpec(
                name="delete_file",
                category="mutation",
                risk_level=RiskLevel.CRITICAL,
                read_only=False,
                reversible=False,
                external_side_effect=True,
                destructive=True,
                requires_confirmation=True,
                description="Elimina de forma irreversible un archivo.",
            ),
        ]
        for spec in defaults:
            self._tools[spec.name] = spec
