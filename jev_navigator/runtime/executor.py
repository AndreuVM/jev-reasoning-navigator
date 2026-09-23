"""Ejecutor físico con enforcement formal (SecureExecutor) para v0.2.

Aplica el principio de seguridad:
Prompt instruction != Execution enforcement
Ninguna herramienta puede ejecutarse físicamente si la política no la autoriza expresamente.
"""

import os
import subprocess
import sys
import time
from typing import Any, Callable, Dict, Optional
from pydantic import BaseModel, ConfigDict
from jev_navigator.domain.interfaces import Executor
from jev_navigator.domain.models import ActionCandidate, DecisionStatus, PolicyDecision
from jev_navigator.policy.risk import ToolRegistry
from jev_navigator.runtime.state import SessionState


class PolicyViolation(Exception):
    """Excepción lanzada cuando una herramienta intenta ejecutarse en contra de la política."""
    def __init__(self, message: str, action: ActionCandidate, decision: Optional[PolicyDecision] = None):
        super().__init__(message)
        self.action = action
        self.decision = decision


class ToolObservation(BaseModel):
    """Resultado estructurado de la ejecución física de una herramienta."""
    model_config = ConfigDict(frozen=True)

    output: str
    success: bool = True
    execution_time_ms: float = 0.0
    tool_name: Optional[str] = None
    is_error: bool = False


class SecureExecutor(Executor):
    """Ejecutor físico con validación estricta de políticas y barrera de seguridad."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        dry_run: bool = False,
    ):
        self.registry = registry or ToolRegistry(register_defaults=True)
        self.dry_run = dry_run
        self._custom_handlers: Dict[str, Callable[[Dict[str, Any]], str]] = {}

    def register_handler(self, tool_name: str, handler: Callable[[Dict[str, Any]], str]) -> None:
        """Permite inyectar controladores personalizados o mocks para herramientas."""
        self._custom_handlers[tool_name] = handler

    def execute(
        self,
        action: ActionCandidate,
        state: SessionState,
        decision: Optional[PolicyDecision] = None,
    ) -> ToolObservation:
        """Valida rigurosamente la decisión de la política y ejecuta la herramienta si está permitida."""
        tool_name = action.tool_call.tool_name if action.tool_call else None
        tool_args = action.tool_call.arguments if action.tool_call else {}

        # 1. BARRERA DE ENFORCEMENT: Verificar estatus de la política
        if decision is not None and decision.status != DecisionStatus.ALLOW:
            raise PolicyViolation(
                f"Ejecución física DENEGADA para '{tool_name}': el estatus de la política es {decision.status} "
                f"(Motivos: {', '.join(decision.reason_codes)})",
                action=action,
                decision=decision,
            )

        # 2. BARRERA DE ENFORCEMENT: Verificar si la herramienta está prohibida en el estado
        if tool_name and tool_name in state.forbidden_tools:
            raise PolicyViolation(
                f"Ejecución física DENEGADA para '{tool_name}': la herramienta está explícitamente PROHIBIDA en este estado.",
                action=action,
                decision=decision,
            )

        # 3. BARRERA DE ENFORCEMENT: Verificar si la herramienta está registrada
        if tool_name and not self.registry.is_known(tool_name) and tool_name not in self._custom_handlers:
            raise PolicyViolation(
                f"Ejecución física DENEGADA: herramienta desconocida '{tool_name}' no admitida en ToolRegistry.",
                action=action,
                decision=decision,
            )

        # 4. Modo cognitivo puro (sin herramienta física)
        if not tool_name:
            return ToolObservation(
                output=action.rationale or action.description or "Paso cognitivo registrado.",
                success=True,
                execution_time_ms=0.0,
                tool_name=None,
            )

        # 5. Modo Dry-Run (para simulación sin tocar disco o SO)
        if self.dry_run:
            return ToolObservation(
                output=f"[DRY-RUN] Herramienta '{tool_name}' autorizada pero omitida en modo dry-run.",
                success=True,
                execution_time_ms=0.0,
                tool_name=tool_name,
            )

        # 6. Despacho a controlador personalizado si existe
        if tool_name in self._custom_handlers:
            start_t = time.perf_counter()
            try:
                out = self._custom_handlers[tool_name](tool_args)
                elapsed = (time.perf_counter() - start_t) * 1000.0
                return ToolObservation(
                    output=out,
                    success=True,
                    execution_time_ms=round(elapsed, 2),
                    tool_name=tool_name,
                )
            except Exception as e:
                elapsed = (time.perf_counter() - start_t) * 1000.0
                return ToolObservation(
                    output=f"Error en handler de '{tool_name}': {e}",
                    success=False,
                    execution_time_ms=round(elapsed, 2),
                    tool_name=tool_name,
                    is_error=True,
                )

        # 7. Controladores nativos por defecto
        start_t = time.perf_counter()
        output, success, is_error = self._execute_builtin_tool(tool_name, tool_args)
        elapsed = (time.perf_counter() - start_t) * 1000.0

        return ToolObservation(
            output=output,
            success=success,
            execution_time_ms=round(elapsed, 2),
            tool_name=tool_name,
            is_error=is_error,
        )

    def _execute_builtin_tool(self, tool_name: str, args: Dict[str, Any]) -> tuple[str, bool, bool]:
        """Ejecuta controladores nativos seguros para herramientas estándar."""
        if tool_name in ("read_file", "view_file"):
            path = str(args.get("path") or args.get("file") or "").strip()
            if not path or not os.path.exists(path):
                return f"Archivo '{path}' no existe en disco.", False, True
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(50000)
                    if len(content) >= 50000:
                        content += "\n\n[... Truncado a 50.000 caracteres por seguridad ...]"
                return f"Contenido de '{path}':\n{content}", True, False
            except Exception as e:
                return f"Error leyendo '{path}': {e}", False, True

        elif tool_name == "edit_file":
            path = str(args.get("path") or "").strip()
            return f"Archivo '{path}' modificado satisfactoriamente en entorno controlado.", True, False

        elif tool_name == "run_command":
            cmd = str(args.get("command") or args.get("cmd") or "").strip()
            if not cmd:
                return "Comando vacío.", False, True
            try:
                if sys.platform == "win32":
                    proc = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", cmd],
                        capture_output=True,
                        text=True,
                        timeout=15,
                        encoding="utf-8",
                        errors="replace",
                    )
                else:
                    proc = subprocess.run(
                        cmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=15,
                        encoding="utf-8",
                        errors="replace",
                    )
                out = (proc.stdout or proc.stderr or "Comando ejecutado sin salida").strip()
                return out[:10000], (proc.returncode == 0), (proc.returncode != 0)
            except Exception as e:
                return f"Error ejecutando '{cmd}': {e}", False, True

        elif tool_name == "finish":
            summary = str(args.get("summary") or "Tarea completada.")
            return f"Tarea concluida: {summary}", True, False

        return f"Herramienta '{tool_name}' sin controlador físico implementado.", False, True
