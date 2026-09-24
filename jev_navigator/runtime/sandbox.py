"""Adaptadores de aislamiento y ejecución en sandbox (SandboxAdapter) para v0.2.1.

Separa formalmente la arquitectura:
Policy decision -> Capability -> Sandbox / Tool Adapter -> Host / Isolated Execution

Garantiza:
1. Contención de directorio de trabajo (jail path / workspace boundaries).
2. Sanitización y depuración de variables de entorno (eliminación de API keys y secretos del proceso hijo).
3. Ejecución tokenizada segura sin shell=True arbitrario.
4. Límite estricto de timeout y control de errores.
"""

from abc import ABC, abstractmethod
import os
import shlex
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field


class SandboxViolation(Exception):
    """Excepción lanzada ante un intento de evasión de sandbox o violación de límites."""
    pass


class SandboxExecutionResult(BaseModel):
    """Resultado estructurado de una invocación dentro del sandbox."""
    model_config = ConfigDict(frozen=True)

    output: str
    success: bool
    is_error: bool
    exit_code: int = 0
    execution_time_ms: float = 0.0
    sandboxed: bool = True


class SandboxAdapter(ABC):
    """Interfaz base para adaptadores de sandbox y aislamiento operacional."""

    @abstractmethod
    def execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 15.0,
    ) -> SandboxExecutionResult:
        """Ejecuta un comando en un proceso aislado y devuelve el resultado estructurado."""
        pass

    @abstractmethod
    def read_file(self, path: str, max_bytes: int = 50_000) -> SandboxExecutionResult:
        """Lee un archivo comprobando contención de ruta (path containment)."""
        pass

    @abstractmethod
    def edit_file(self, path: str, content: str) -> SandboxExecutionResult:
        """Modifica un archivo comprobando contención de ruta."""
        pass


class LocalProcessSandbox(SandboxAdapter):
    """Sandbox de proceso local con depuración de entorno y contención de rutas."""

    BLOCKED_ENV_VARS: Set[str] = {
        "TYPESAFE_API_KEY",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "SECRET_KEY",
        "API_KEY",
        "PASSWORD",
        "SSH_AUTH_SOCK",
    }

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        allow_external_cwd: bool = False,
        extra_blocked_vars: Optional[Set[str]] = None,
    ):
        self.workspace_root = os.path.abspath(workspace_root or os.getcwd())
        self.allow_external_cwd = allow_external_cwd
        self.blocked_vars = self.BLOCKED_ENV_VARS.union(extra_blocked_vars or set())

    def _sanitize_environment(self, custom_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Limpia las variables de entorno para que el proceso hijo no tenga acceso a claves privadas ni tokens."""
        clean_env = dict(os.environ)
        # Purgar variables sensibles
        for var in list(clean_env.keys()):
            upper_var = var.upper()
            if any(blocked in upper_var for blocked in self.blocked_vars):
                clean_env.pop(var, None)

        # Inyectar indicador de ejecución en sandbox
        clean_env["JEV_SANDBOX_ACTIVE"] = "1"
        clean_env["PYTHONUNBUFFERED"] = "1"

        if custom_env:
            for k, v in custom_env.items():
                if not any(blocked in k.upper() for blocked in self.blocked_vars):
                    clean_env[k] = v

        return clean_env

    def _validate_path_containment(self, path: str) -> str:
        """Valida que una ruta esté estrictamente contenida dentro del workspace_root delimitado."""
        if not path:
            raise SandboxViolation("Ruta de archivo vacía.")

        abs_path = os.path.abspath(os.path.join(self.workspace_root, path) if not os.path.isabs(path) else path)
        if not self.allow_external_cwd:
            # Comprobar contención real
            common = os.path.commonpath([self.workspace_root, abs_path])
            if common != self.workspace_root:
                raise SandboxViolation(
                    f"Evasión de ruta detectada: '{path}' resuelve en '{abs_path}', "
                    f"fuera del workspace delimitado '{self.workspace_root}'."
                )
        return abs_path

    def execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 15.0,
    ) -> SandboxExecutionResult:
        """Ejecuta un comando en un proceso hijo sanitizado y con timeout forzado."""
        cmd_str = (command or "").strip()
        if not cmd_str:
            return SandboxExecutionResult(
                output="Comando vacío.",
                success=False,
                is_error=True,
                exit_code=1,
            )

        target_cwd = self._validate_path_containment(cwd) if cwd else self.workspace_root
        clean_env = self._sanitize_environment(env)

        start_t = time.perf_counter()
        try:
            if sys.platform == "win32":
                # En Windows se aísla con PowerShell sin perfiles de usuario ni scripts globales
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd_str],
                    cwd=target_cwd,
                    env=clean_env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                    shell=False,
                )
            else:
                # En Unix se ejecuta tokenizado o en subshell sin variables heredadas sensibles
                args = shlex.split(cmd_str)
                proc = subprocess.run(
                    args,
                    cwd=target_cwd,
                    env=clean_env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                    shell=False,
                )

            elapsed = (time.perf_counter() - start_t) * 1000.0
            out = (proc.stdout or proc.stderr or "Comando ejecutado sin salida").strip()
            success = (proc.returncode == 0)
            return SandboxExecutionResult(
                output=out[:20000],
                success=success,
                is_error=not success,
                exit_code=proc.returncode,
                execution_time_ms=round(elapsed, 2),
                sandboxed=True,
            )
        except subprocess.TimeoutExpired:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return SandboxExecutionResult(
                output=f"Timeout superado ({timeout}s) durante la ejecución de: {cmd_str[:100]}",
                success=False,
                is_error=True,
                exit_code=124,
                execution_time_ms=round(elapsed, 2),
                sandboxed=True,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return SandboxExecutionResult(
                output=f"Error en sandbox ejecutando comando: {e}",
                success=False,
                is_error=True,
                exit_code=1,
                execution_time_ms=round(elapsed, 2),
                sandboxed=True,
            )

    def read_file(self, path: str, max_bytes: int = 50_000) -> SandboxExecutionResult:
        """Lee un archivo garantizando contención de ruta."""
        start_t = time.perf_counter()
        try:
            safe_path = self._validate_path_containment(path)
            if not os.path.exists(safe_path):
                return SandboxExecutionResult(
                    output=f"Archivo '{path}' no existe en workspace.",
                    success=False,
                    is_error=True,
                    exit_code=1,
                )
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_bytes)
                if len(content) >= max_bytes:
                    content += f"\n\n[... Truncado a {max_bytes} bytes por política de sandbox ...]"
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return SandboxExecutionResult(
                output=f"Contenido de '{path}':\n{content}",
                success=True,
                is_error=False,
                exit_code=0,
                execution_time_ms=round(elapsed, 2),
                sandboxed=True,
            )
        except SandboxViolation as sv:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return SandboxExecutionResult(
                output=str(sv),
                success=False,
                is_error=True,
                exit_code=1,
                execution_time_ms=round(elapsed, 2),
                sandboxed=True,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return SandboxExecutionResult(
                output=f"Error leyendo '{path}': {e}",
                success=False,
                is_error=True,
                exit_code=1,
                execution_time_ms=round(elapsed, 2),
                sandboxed=True,
            )

    def edit_file(self, path: str, content: str) -> SandboxExecutionResult:
        """Modifica un archivo verificando que se mantenga dentro del workspace."""
        start_t = time.perf_counter()
        try:
            safe_path = self._validate_path_containment(path)
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(content)
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return SandboxExecutionResult(
                output=f"Archivo '{path}' modificado satisfactoriamente dentro del sandbox.",
                success=True,
                is_error=False,
                exit_code=0,
                execution_time_ms=round(elapsed, 2),
                sandboxed=True,
            )
        except SandboxViolation as sv:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return SandboxExecutionResult(
                output=str(sv),
                success=False,
                is_error=True,
                exit_code=1,
                execution_time_ms=round(elapsed, 2),
                sandboxed=True,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return SandboxExecutionResult(
                output=f"Error escribiendo en '{path}': {e}",
                success=False,
                is_error=True,
                exit_code=1,
                execution_time_ms=round(elapsed, 2),
                sandboxed=True,
            )


class DryRunSandbox(SandboxAdapter):
    """Sandbox simulado para pruebas, benchmarks y modo seguro sin efectos en disco o SO."""

    def execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 15.0,
    ) -> SandboxExecutionResult:
        return SandboxExecutionResult(
            output=f"[DRY-RUN] [SANDBOX] Comando '{command}' validado y ejecutado en modo simulación.",
            success=True,
            is_error=False,
            exit_code=0,
            execution_time_ms=0.1,
            sandboxed=True,
        )

    def read_file(self, path: str, max_bytes: int = 50_000) -> SandboxExecutionResult:
        return SandboxExecutionResult(
            output=f"[DRY-RUN] [SANDBOX] Lectura simulada de '{path}'.",
            success=True,
            is_error=False,
            exit_code=0,
            execution_time_ms=0.1,
            sandboxed=True,
        )

    def edit_file(self, path: str, content: str) -> SandboxExecutionResult:
        return SandboxExecutionResult(
            output=f"[DRY-RUN] [SANDBOX] Edición simulada de '{path}'.",
            success=True,
            is_error=False,
            exit_code=0,
            execution_time_ms=0.1,
            sandboxed=True,
        )
