"""Módulo de recuperación de errores de cuota/modelo y selección interactiva de LLM."""

import os
from typing import Optional, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

AVAILABLE_MODELS = [
    ("gemini-3.6-flash", "Gemini 3.6 Flash (Sustituto oficial recomendado por Google)"),
    ("gemma-4-26b-a4b-it", "Google Gemma 4 (26B Compacto - Sin límite de 20 RPD)"),
    ("gemma-4-31b-it", "Google Gemma 4 (31B Instrucciones)"),
    ("gemini-3.8-flash", "Gemini 3.8 Flash (Versión avanzada)"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash (Aviso: descatalogado por Google para nuevos usuarios - 404)"),
]


def prompt_model_recovery_menu(
    error_message: str,
    current_model: str,
    console: Optional[Console] = None,
) -> Tuple[str, Optional[str]]:
    """Muestra un menú interactivo cuando la cuota de Gemini se ha excedido o hay error en el modelo.

    Retorna:
        Tuple[str, Optional[str]]:
            - ("change_model", model_name)
            - ("update_key", new_key)
            - ("abort", None)
    """
    con = console or Console()

    options_text = ""
    for idx, (m_id, m_desc) in enumerate(AVAILABLE_MODELS, start=1):
        active_tag = " [bold cyan](actual)[/]" if m_id == current_model else ""
        options_text += f"  [bold cyan]{idx})[/] [white]{m_id}[/] - [dim]{m_desc}[/]{active_tag}\n"

    custom_opt = len(AVAILABLE_MODELS) + 1
    key_opt = len(AVAILABLE_MODELS) + 2
    abort_opt = len(AVAILABLE_MODELS) + 3

    options_text += f"  [bold cyan]{custom_opt})[/] [white]Introducir otro modelo manualmente...[/]\n"
    options_text += f"  [bold cyan]{key_opt})[/] [white]Actualizar clave GEMINI_API_KEY (en .env)...[/]\n"
    options_text += f"  [bold red]{abort_opt})[/] [red]Cancelar y detener ejecución actual[/]"

    con.print("\n")
    con.print(Panel(
        f"[bold red]❌ Se ha producido un error o límite de cuota con el modelo actual ({current_model}):[/]\n"
        f"[yellow]{error_message}[/]\n\n"
        "[bold white]Selecciona una alternativa para continuar:[/]\n"
        f"{options_text}",
        title="⚠️ [bold yellow]Menú de Recuperación y Selección de Modelo LLM[/]",
        border_style="yellow",
        padding=(1, 2),
    ))

    valid_choices = [str(i) for i in range(1, abort_opt + 1)]
    default_choice = "1" if current_model != "gemini-2.5-flash" else "2"

    try:
        choice = Prompt.ask(
            "[bold cyan]👉 Elige una opción[/]",
            choices=valid_choices,
            default=default_choice,
            console=con,
        )
    except (KeyboardInterrupt, EOFError):
        return ("abort", None)

    choice_num = int(choice)
    if 1 <= choice_num <= len(AVAILABLE_MODELS):
        selected_model = AVAILABLE_MODELS[choice_num - 1][0]
        con.print(f"[green]✓ Cambiando modelo a:[/] [bold white]{selected_model}[/]\n")
        return ("change_model", selected_model)
    elif choice_num == custom_opt:
        try:
            custom_name = Prompt.ask("[bold cyan]Introduce el identificador del modelo (ej. gemini-2.5-flash)[/]", console=con)
        except (KeyboardInterrupt, EOFError):
            return ("abort", None)
        custom_name = (custom_name or "").strip()
        if custom_name:
            con.print(f"[green]✓ Modelo personalizado seleccionado:[/] [bold white]{custom_name}[/]\n")
            return ("change_model", custom_name)
        return ("abort", None)
    elif choice_num == key_opt:
        try:
            new_key = Prompt.ask("[bold cyan]Introduce tu nueva GEMINI_API_KEY[/]", console=con, password=True)
        except (KeyboardInterrupt, EOFError):
            return ("abort", None)
        new_key = (new_key or "").strip()
        if new_key:
            _persist_api_key_to_env(new_key)
            con.print("[green]✓ Clave GEMINI_API_KEY actualizada y guardada en .env.[/]\n")
            return ("update_key", new_key)
        return ("abort", None)
    else:
        con.print("[yellow]Ejecución cancelada por el usuario.[/]\n")
        return ("abort", None)


def _persist_api_key_to_env(new_key: str, env_path: str = ".env") -> None:
    """Actualiza la variable GEMINI_API_KEY en el archivo .env y en os.environ."""
    os.environ["GEMINI_API_KEY"] = new_key
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"GEMINI_API_KEY={new_key}\n")
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        key_found = False
        new_lines = []
        for line in lines:
            if line.strip().startswith("GEMINI_API_KEY="):
                new_lines.append(f"GEMINI_API_KEY={new_key}\n")
                key_found = True
            else:
                new_lines.append(line)

        if not key_found:
            new_lines.append(f"GEMINI_API_KEY={new_key}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception:
        pass
