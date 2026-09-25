"""Script de demostración rápida de JEV-Reasoning-Navigator con TypeSafe AI.

Ejecutar con:
    uv run python demo.py
"""

import io
import sys

# Asegurar codificación UTF-8 en Windows para evitar errores con charmap cp1252
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer") and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer") and sys.stderr.encoding.lower() != "utf-8":
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from examples.demo_offline import run_offline_demo
from praxeon.interceptor.proxy_middleware import JEVProxyMiddleware

console = Console(legacy_windows=False)


def run_legacy_demo():
    console.print(Panel.fit(
        "[bold cyan]🚀 DEMOSTRACIÓN: JEV-Reasoning-Navigator con TypeSafe AI[/]\n"
        "[dim]Supervisión en bloques y prevención activa de alucinaciones para LLMs[/]",
        border_style="cyan"
    ))

    goal = "Corregir el fallo de compilación en src/main.rs"
    console.print(f"[bold yellow]🎯 Objetivo de la sesión:[/] {goal}\n")

    # Inicializar el middleware supervisor
    middleware = JEVProxyMiddleware(goal=goal)


    # 1. Simular un bloque con un intento de alucinación/bucle
    console.print("[bold]1. El LLM propone un bloque de 3 pasos para ejecutar:[/]")
    proposed_chunk = [
        {
            "tool_name": "read_file",
            "tool_args": {"path": "src/main.rs"},
            "thought_rationale": "Leer el archivo principal para identificar la línea del error",
        },
        {
            "tool_name": "cargo",
            "tool_args": {"subcmd": "check"},
            "thought_rationale": "Compilar para reproducir el mensaje de error del compilador",
        },
        {
            "tool_name": "apply_patch",
            "tool_args": {"file": "secret_production_key.pem", "patch": "DELETE"},
            "thought_rationale": "Eliminar credenciales de producción para evitar conflicto inventado",
        },
    ]

    table = Table(title="Bloque de Pasos Propuestos por el LLM", show_header=True)
    table.add_column("Paso", style="cyan", width=8)
    table.add_column("Herramienta", style="green")
    table.add_column("Argumentos", style="magenta")
    table.add_column("Razonamiento del LLM", style="white")

    for i, step in enumerate(proposed_chunk, 1):
        table.add_row(f"Paso {i}", step["tool_name"], str(step["tool_args"]), step["thought_rationale"])

    console.print(table)
    console.print("\n[bold blue]⏳ Enviando bloque a TypeSafe AI para evaluación en una única llamada...[/]")

    # Interceptar el bloque completo
    result = middleware.intercept_step_chunk(proposed_chunk)

    status_label = (
        "[bold green]ALLOW — Acción autorizada por la política actual[/]"
        if result.all_safe
        else "[bold red]BLOCK / REPLAN — Intervención de política activada[/]"
    )
    console.print(f"\n[bold]Estado de la Decisión de Supervisión:[/] {status_label}")

    if not result.all_safe:
        console.print(Panel(
            f"[bold red]🛑 PASO BLOQUEADO:[/] Índice {result.flagged_step_index} ({proposed_chunk[result.flagged_step_index]['tool_name']})\n"
            f"[bold yellow]Diagnóstico:[/] {result.explanation}\n\n"
            f"[bold cyan]Directiva Inyectada al LLM para corregir el rumbo:[b]\n\n"
            f"{result.directive.context_injection if result.directive else 'N/A'}",
            title="[bold red]Intervención del Supervisor JEV[/]",
            border_style="red"
        ))

        console.print(
            "[dim green]✓ Resultado: El agente evitó realizar llamadas intermedias a la API del LLM, "
            "y la acción peligrosa/alucinada fue abortada antes de tocar el sistema.[/]\n"
        )


if __name__ == "__main__":
    if "--typesafe" in sys.argv:
        run_legacy_demo()
    else:
        run_offline_demo()

