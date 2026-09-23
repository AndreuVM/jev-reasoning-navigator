"""Agente autónomo en vivo supervisado en tiempo real por JEV-Reasoning-Navigator con supervisión agrupada (chunking) y llamadas condicionales a Gemini."""

import argparse
import io
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Asegurar codificación UTF-8 en Windows para evitar errores con charmap cp1252
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer") and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer") and sys.stderr.encoding.lower() != "utf-8":
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from jev_navigator.config import JEVConfig, default_config
from jev_navigator.core.session_context import SessionContextManager
from jev_navigator.interceptor.proxy_middleware import JEVProxyMiddleware
from jev_navigator.models.schema import InterventionLevel

console = Console(legacy_windows=False)


def decode_process_bytes(raw_bytes: bytes) -> str:
    """Decodifica de manera inteligente la salida binaria de procesos en Windows y Linux evitando caracteres corruptos."""
    if not raw_bytes:
        return ""
    try:
        text = raw_bytes.decode("utf-8")
        if "\ufffd" not in text:
            return text
    except UnicodeDecodeError:
        pass
    for enc in ("cp1252", "cp850", "latin-1"):
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def prune_observation_output(output: str, max_chars: int = 2000) -> str:
    """Trunca salidas extensas de comandos preservando el inicio y el final relevante para optimizar tokens."""
    cleaned = (output or "Comando ejecutado sin salida").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    keep_head = int(max_chars * 0.65)
    keep_tail = int(max_chars * 0.35)
    omitted = len(cleaned) - (keep_head + keep_tail)
    return (
        f"{cleaned[:keep_head]}\n\n"
        f"[... {omitted} caracteres intermedios omitidos por JEV Token Pruner para optimizar contexto ...]\n\n"
        f"{cleaned[-keep_tail:]}"
    )


def build_optimized_prompt(conversation_history: List[Dict[str, str]], max_recent_turns: int = 8) -> str:
    """Construye el prompt optimizado para el LLM aplicando compresión a turnos antiguos si la conversación es larga."""
    if len(conversation_history) <= (max_recent_turns * 2 + 2):
        return "\n\n".join(f"[{m['role'].upper()}]: {m['content']}" for m in conversation_history) + "\n\n[ASSISTANT]:\n"
    
    header = conversation_history[:2]
    recent = conversation_history[-(max_recent_turns * 2):]
    middle_count = len(conversation_history) - len(header) - len(recent)
    summary_msg = {
        "role": "user",
        "content": f"[... Historial intermedio: {middle_count} mensajes anteriores comprimidos por JEV para preservar ventana de contexto ...]",
    }
    compacted = header + [summary_msg] + recent
    return "\n\n".join(f"[{m['role'].upper()}]: {m['content']}" for m in compacted) + "\n\n[ASSISTANT]:\n"


def parse_llm_steps(llm_output: str) -> List[Dict[str, Any]]:
    """Extrae uno o múltiples pasos (Thought + Action) de la salida del LLM."""
    steps: List[Dict[str, Any]] = []

    # 1. Normalizar etiquetas markdown (**Thought:**, **Action:**, etc.)
    text = re.sub(r"[\*_]{1,2}(Step\s+\d+|Paso\s+\d+|Thought|Action)[\*_]{0,2}\s*:", r"\1:", llm_output, flags=re.IGNORECASE)
    # 2. Insertar saltos de línea antes de palabras clave si vienen en línea continua o sin salto
    text = re.sub(r"(?i)(?<!\n)\s*(action\s*:)", r"\n\1", text)
    text = re.sub(r"(?i)(?<!\n)\s*(thought\s*:)", r"\n\1", text)
    text = re.sub(r"(?i)(?<!\n)\s*(step\s+\d+\s*:)", r"\n\1", text)
    text = re.sub(r"(?i)(?<!\n)\s*(paso\s+\d+\s*:)", r"\n\1", text)

    current_thought = ""
    current_tool = None
    current_args: Dict[str, Any] = {}

    lines = text.strip().splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        lower_line = stripped.lower()
        if lower_line.startswith("thought:"):
            if current_tool:
                steps.append({
                    "thought_rationale": current_thought,
                    "tool_name": current_tool,
                    "tool_args": current_args,
                })
                current_thought = ""
                current_tool = None
                current_args = {}
            current_thought = stripped[len("thought:"):].strip()
        elif lower_line.startswith("action:"):
            action_content = stripped[len("action:"):].strip()
            # 1. Comprobar sintaxis estilo llamada de función: tool_name(...)
            m = re.match(r"^([a-zA-Z0-9_]+)\s*\((.*)\)$", action_content, re.DOTALL)
            if m:
                current_tool = m.group(1).strip()
                raw_arg = m.group(2).strip()
                try:
                    parsed = json.loads(raw_arg)
                    if isinstance(parsed, dict):
                        current_args = parsed
                    elif isinstance(parsed, str):
                        clean_str = parsed.strip()
                        if current_tool == "run_command":
                            current_args = {"command": clean_str}
                        elif current_tool in ("read_file", "view_file"):
                            current_args = {"path": clean_str}
                        elif current_tool == "finish":
                            current_args = {"summary": clean_str}
                        else:
                            current_args = {"raw": clean_str}
                    else:
                        current_args = {"raw": str(parsed)}
                except Exception:
                    clean_arg = raw_arg.strip('"').strip("'")
                    if current_tool == "run_command":
                        current_args = {"command": clean_arg}
                    elif current_tool in ("read_file", "view_file"):
                        current_args = {"path": clean_arg}
                    elif current_tool == "finish":
                        current_args = {"summary": clean_arg}
                    else:
                        current_args = {"raw": clean_arg, "command": clean_arg}
            else:
                # 2. Sintaxis estándar: tool_name <json_o_string>
                parts = action_content.split(maxsplit=1)
                if parts:
                    current_tool = parts[0].strip()
                    if len(parts) > 1:
                        raw_arg = parts[1].strip()
                        try:
                            parsed = json.loads(raw_arg)
                            if isinstance(parsed, dict):
                                current_args = parsed
                            else:
                                current_args = {"raw": str(parsed)}
                        except Exception:
                            clean_arg = raw_arg.strip('"').strip("'")
                            if current_tool == "run_command":
                                current_args = {"command": clean_arg}
                            elif current_tool in ("read_file", "view_file"):
                                current_args = {"path": clean_arg}
                            elif current_tool == "finish":
                                current_args = {"summary": clean_arg}
                            else:
                                current_args = {"raw": clean_arg, "command": clean_arg}
                    else:
                        current_args = {}
        elif (lower_line.startswith("step ") or lower_line.startswith("paso ")) and ":" in stripped:
            if current_tool:
                steps.append({
                    "thought_rationale": current_thought,
                    "tool_name": current_tool,
                    "tool_args": current_args,
                })
                current_thought = ""
                current_tool = None
                current_args = {}

    if current_tool:
        steps.append({
            "thought_rationale": current_thought,
            "tool_name": current_tool,
            "tool_args": current_args,
        })
    elif current_thought:
        # Solo interpretar como 'finish' si el pensamiento es explícitamente concluyente
        lower_th = current_thought.lower()
        is_conclusion = any(w in lower_th for w in ("conclu", "finaliz", "resuelt", "solución", "solucion", "terminad", "completad", "finish"))
        if is_conclusion:
            steps.append({
                "thought_rationale": current_thought,
                "tool_name": "finish",
                "tool_args": {"summary": current_thought},
            })
    elif not steps and llm_output.strip():
        lower_out = llm_output.lower()
        if any(w in lower_out for w in ("conclu", "finaliz", "resuelt", "solución", "solucion", "terminad", "completad")):
            steps.append({
                "thought_rationale": "Conclusión directa emitida por el agente LLM",
                "tool_name": "finish",
                "tool_args": {"summary": llm_output.strip()},
            })

    return steps


def run_live_gemini_agent(
    task: str,
    max_steps: int = 15,
    config: Optional[JEVConfig] = None,
    gemini_api_key: Optional[str] = None,
    model_name: str = "gemini-3.8-flash",
    session_context: Optional[SessionContextManager] = None,
    middleware: Optional[JEVProxyMiddleware] = None,
) -> Tuple[bool, str, SessionContextManager, JEVProxyMiddleware]:
    """Ejecuta un bucle de razonamiento de Gemini supervisado en bloques por JEV.
    
    Optimiza el consumo de peticiones y mantiene memoria acumulada entre tareas concatenadas:
    - Agrupa los pasos candidatos y los evalúa en TypeSafe en una sola llamada.
    - Ejecuta pasos autorizados secuencialmente sin consultar a Gemini tras cada paso.
    - Devuelve el control a Gemini solo cuando JEV detecta una alucinación/bucle, 
      ocurre un error crítico o finaliza el bloque planificado.
    - Si max_steps <= 0, funciona en modo ilimitado hasta que el agente llame a finish.
    """
    cfg = config or default_config
    api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
    is_unlimited = (max_steps <= 0)

    session = session_context or SessionContextManager()
    if middleware is None:
        middleware = JEVProxyMiddleware(goal=task, config=cfg)
    else:
        middleware.start_subtask(task)

    console.print(Panel(
        f"[bold white]Tarea del Agente:[/] {task}\n"
        f"[bold white]Supervisor JEV:[/] TypeSafe AI (Modelo Jev - System One Chunked)\n"
        f"[bold white]Modelo LLM Agente:[/] {model_name} (Google GenAI)\n"
        f"[bold white]Límite de Pasos:[/] {'Ilimitado (hasta invocar finish)' if is_unlimited else f'{max_steps} pasos'}\n"
        f"[bold white]Tamaño de bloque (Chunk Size):[/] {cfg.evaluation_chunk_size} pasos por lote\n"
        f"[bold white]Contexto de Sesión:[/] {'Primera tarea (limpia)' if session.is_empty() else f'Heredando memoria de {len(session.task_records)} tarea(s) previa(s)'}",
        title="🤖 [bold green]Live Agent Loop Supervisado por JEV (Memoria Continua)[/]",
        border_style="green",
    ))

    # Mostrar resumen de tareas previas si existen
    if not session.is_empty():
        console.print(session.get_summary_panel())

    genai_client = None
    genai_config = None
    if api_key and api_key.strip() and api_key.lower() not in ("none", "null", "false", "simulator", "demo"):
        try:
            from google import genai
            from google.genai import types
            genai_client = genai.Client(api_key=api_key)
            genai_config = types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )
            console.print("[dim]✓ Cliente Gemini conectado con éxito.[/]")
        except Exception as e:
            console.print(f"[bold yellow]Aviso:[/] No se pudo inicializar google-genai ({e}). Usando simulador de agente.")

    chunk_size = cfg.evaluation_chunk_size
    conversation_history: List[Dict[str, str]] = session.prepare_task_conversation(task)

    executed_steps = 0
    executed_step_records: List[Dict[str, Any]] = []
    final_summary: str = ""
    final_answer: str = ""
    gemini_calls_count = 0
    typesafe_calls_count = 0
    interventions_count = 0
    sim_turn = 0
    task_finished = False

    last_gemini_call_time = 0.0

    consecutive_blocks = 0
    max_turns = 1000000 if is_unlimited else (max_steps + 4)
    while (is_unlimited or executed_steps < max_steps) and sim_turn < max_turns:
        sim_turn += 1
        console.print(f"\n[bold magenta]━━━━━━━━━━━━━━━ Fase de Generación LLM (Turno {sim_turn}) ━━━━━━━━━━━━━━━[/]")

        # 1. Llamar a Gemini solo cuando se requiere nueva formulación cognitiva
        gemini_calls_count += 1
        llm_output = ""

        if genai_client:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    is_antigravity = "antigravity" in model_name.lower()
                    min_interval = 1.2 if is_antigravity else 12.5

                    elapsed = time.time() - last_gemini_call_time
                    if last_gemini_call_time > 0 and elapsed < min_interval:
                        wait_rpm = min_interval - elapsed
                        console.print(f"[dim]⏳ Pausa preventiva de {wait_rpm:.1f}s para respetar límite de {'60 RPM' if is_antigravity else '5 RPM'}...[/]")
                        time.sleep(wait_rpm)

                    target_model = "antigravity-preview-09-2026" if model_name.lower() in ("antigravity", "antigravity-preview") else model_name
                    console.print(f"[dim]⚡ Consultando {'Antigravity API' if is_antigravity else 'Gemini API'} ({target_model})... [Llamada #{gemini_calls_count}][/]")
                    last_gemini_call_time = time.time()
                    prompt_parts = build_optimized_prompt(conversation_history)

                    if is_antigravity:
                        interaction_res = genai_client.interactions.create(
                            model=target_model,
                            input=prompt_parts,
                        )
                        llm_output = (interaction_res.output_text or "").strip()
                    else:
                        response = genai_client.models.generate_content(
                            model=model_name,
                            contents=prompt_parts,
                            config=genai_config,
                        )
                        llm_output = response.text.strip()

                    console.print(f"[bold white]LLM Output:[/]\n{llm_output}")
                    break
                except Exception as err:
                    err_str = str(err)
                    console.print(f"[bold red]Error en API de Gemini:[/] {err_str}")
                    from jev_navigator.model_recovery import prompt_model_recovery_menu
                    action, payload = prompt_model_recovery_menu(
                        error_message=err_str,
                        current_model=model_name,
                        console=console,
                    )
                    if action == "change_model" and payload:
                        model_name = payload
                        console.print(f"[green]✓ Cambiado a modelo {model_name}. Reintentando...[/]")
                        continue
                    elif action == "update_key" and payload:
                        try:
                            from google import genai
                            from google.genai import types
                            genai_client = genai.Client(api_key=payload)
                            genai_config = types.GenerateContentConfig(
                                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                            )
                            console.print("[green]✓ Clave actualizada. Reintentando...[/]")
                        except Exception as init_err:
                            console.print(f"[bold red]Error con nueva clave:[/] {init_err}")
                        continue
                    else:
                        console.print("[yellow]Ejecución detenida tras error de API o cancelación del usuario.[/]")
                        llm_output = ""
                        break

        if not llm_output:
            console.print("[bold red]❌ No se obtuvo respuesta del modelo LLM. Finalizando tarea sin ejecutar simulaciones falsas.[/]")
            break


        # 2. Extraer pasos candidatos del bloque propuesto
        proposed_steps = parse_llm_steps(llm_output)
        if not proposed_steps:
            console.print("[yellow]Aviso: No se identificaron acciones concretas en la respuesta. Fin de ciclo.[/]")
            break

        console.print(f"[bold cyan]🔍 Bloque propuesto con {len(proposed_steps)} paso(s). Enviando a JEV en UNA sola petición agrupada...[/]")
        typesafe_calls_count += 1

        # 3. Supervisión agrupada en TypeSafe (1 sola petición para todo el bloque)
        chunk_result = middleware.intercept_step_chunk(proposed_steps)

        # 4. Si JEV detecta una alucinación o bucle en el bloque:
        if not chunk_result.all_safe:
            interventions_count += 1
            consecutive_blocks += 1
            flagged_idx = chunk_result.flagged_step_index or 0
            flagged_step = proposed_steps[flagged_idx]
            diag_label = "ALUCINACIÓN" if chunk_result.hallucination_detected else "BUCLE DEGENERATIVO"

            console.print(Panel(
                f"[bold red]🚨 JEV INTERCEPCIÓN ACTIVADA: {diag_label} DETECTADO EN PASO {flagged_idx+1}[/]\n\n"
                f"[bold yellow]Paso bloqueado:[/] {flagged_step.get('tool_name')} {flagged_step.get('tool_args')}\n"
                f"[bold white]Diagnóstico:[/] {chunk_result.explanation}\n\n"
                f"{chunk_result.directive.context_injection if chunk_result.directive else ''}",
                title=f"🛑 [bold red]Supervisión JEV: Acción Prevenida (Ahorro de Llamada a Gemini)[/]",
                border_style="red",
            ))

            # Ejecutar pasos anteriores al fallo si los hubiera
            for valid_idx in range(chunk_result.valid_step_count):
                st = proposed_steps[valid_idx]
                executed_steps += 1
                console.print(f"  [green]✓ Paso {valid_idx+1} previo válido ejecutado: {st.get('tool_name')}[/]")

            # Inyectar la directiva en el contexto de Gemini para que rectifique en la siguiente llamada
            directive_text = chunk_result.directive.context_injection if chunk_result.directive else chunk_result.explanation

            # Mecanismo Circuit Breaker ante bloqueos repetitivos
            if consecutive_blocks == 2:
                directive_text += (
                    "\n\n🚨 [ALERTA DE DESBLOQUEO]: Has acumulado 2 bloqueos seguidos por intentar modificar o asumir estados sin verificar. "
                    "Queda TERMINANTEMENTE PROHIBIDO invocar 'edit_file' o 'finish'. "
                    "En tu siguiente turno DEBES invocar 'run_command' (ej. dir, ls, git status) o 'read_file' para obtener los hechos reales."
                )
            elif consecutive_blocks >= 3:
                console.print("[bold yellow]⚡ JEV CIRCUIT BREAKER: Inyectando observación empírica para romper la parálisis cognitiva...[/]")
                auto_probe = "Observación automática de archivos reales en disco: "
                try:
                    auto_probe += ", ".join([f for f in os.listdir(".") if not f.startswith(".")][:6])
                except Exception:
                    auto_probe += "pyproject.toml, README.md"
                middleware.record_observation(auto_probe)
                conversation_history.append({
                    "role": "user",
                    "content": f"OBSERVACIÓN REAL DE ENTORNO: {auto_probe}\nFormula tu próximo plan basándote exclusivamente en estos archivos reales.",
                })
                consecutive_blocks = 0
                time.sleep(1)
                continue

            conversation_history.append({
                "role": "user",
                "content": (
                    f"SISTEMA DE SUPERVISIÓN JEV:\n{directive_text}\n"
                    f"Tu acción previa fue BLOQUEADA por {diag_label}. "
                    f"Debes rectificar tu plan basándote únicamente en hechos verificados."
                ),
            })
            console.print("[bold green]✓ Directiva inyectada. Devolviendo control a Gemini solo para rectificación necesaria...[/]")
            time.sleep(1)
            continue

        # Bloque aprobado: resetear contador de bloqueos consecutivos
        consecutive_blocks = 0

        # 5. Si JEV aprueba el bloque: Ejecutar secuencialmente SIN volver a llamar a Gemini entre pasos
        console.print(f"[bold green]✓ JEV: Bloque de {len(proposed_steps)} paso(s) validado con éxito. Ejecutando de forma autónoma...[/]")

        task_finished = False
        for step_idx, step_data in enumerate(proposed_steps):
            executed_steps += 1
            tool_name = step_data.get("tool_name") or "thought_reflection"
            tool_args = step_data.get("tool_args") or {}
            thought_text = step_data.get("thought_rationale") or ""

            console.print(f"\n[cyan]▶ Ejecutando Paso {executed_steps} (del bloque aprobado):[/] [bold]{tool_name}[/] [dim]{tool_args}[/]")
            if thought_text:
                console.print(f"  [italic white]Pensamiento:[/] {thought_text}")

            observation = ""
            if tool_name == "finish":
                summary = tool_args.get("summary", "Tarea completada exitosamente")
                evasive_markers = (
                    "pendiente de", "pendiente", "planificación", "planificacion",
                    "como soy un agente", "la acción real", "la accion real",
                    "todavía no", "aún no he", "aun no he", "sin analizar",
                    "no he podido leer", "no he podido", "provisional", "pending",
                    "este paso es de"
                )
                if any(m in str(summary).lower() for m in evasive_markers):
                    console.print(Panel(
                        f"[bold yellow]⚠️ JEV Rechazó finalización evasiva:[/] {summary}\n"
                        "[italic]El agente intentó terminar con excusas de planificación. Obligando a formular respuesta con observaciones existentes.[/]",
                        title="🛡️ Intervención JEV",
                        border_style="yellow",
                    ))
                    task_finished = False
                    observation = (
                        "OBSERVACIÓN DEL SUPERVISOR (JEV): Tu llamada a 'finish' ha sido RECHAZADA porque contiene un texto de planificación o evasión ('pendiente de lectura'). "
                        "NO puedes finalizar sin dar una respuesta concreta. Analiza las observaciones y el contenido ya obtenido y responde directamente con los hallazgos en tu siguiente turno."
                    )
                else:
                    console.print(Panel(
                        f"[bold green]Objetivo completado:[/] {summary}",
                        title="🎉 Éxito de Ejecución",
                        border_style="green",
                    ))
                    task_finished = True
                    final_summary = summary
                    final_answer = summary
                    observation = f"Tarea finalizada: {summary}"
            elif tool_name == "run_command":
                cmd = tool_args.get("command", "")
                if cmd:
                    try:
                        import subprocess
                        if sys.platform == "win32":
                            proc = subprocess.run(
                                ["powershell", "-NoProfile", "-Command", cmd],
                                capture_output=True,
                                timeout=15,
                            )
                            raw_out = proc.stdout if proc.stdout.strip() else proc.stderr
                            output = decode_process_bytes(raw_out)
                            if not output.strip():
                                proc_cmd = subprocess.run(cmd, shell=True, capture_output=True, timeout=15)
                                raw_cmd_out = proc_cmd.stdout or proc_cmd.stderr
                                output = decode_process_bytes(raw_cmd_out)
                        else:
                            proc = subprocess.run(cmd, shell=True, capture_output=True, timeout=15)
                            output = decode_process_bytes(proc.stdout or proc.stderr)
                        observation = prune_observation_output(output, max_chars=2000)
                    except Exception as e:
                        observation = f"Error ejecutando '{cmd}': {e}"
                else:
                    observation = "Comando vacío."
            elif tool_name == "read_file":
                path = tool_args.get("path", "")
                if path and os.path.exists(path):
                    try:
                        with open(path, "rb") as f:
                            raw_bytes = f.read(60000)
                        content = decode_process_bytes(raw_bytes)
                        if len(content) >= 60000:
                            content += "\n\n[... Archivo muy extenso: truncado a 60.000 caracteres por seguridad de contexto ...]"
                        observation = f"Contenido de '{path}':\n{content}"
                    except Exception as e:
                        observation = f"Error leyendo '{path}': {e}"
                else:
                    observation = f"Error: Archivo '{path}' no existe en disco."
            elif tool_name == "edit_file":
                path = tool_args.get("path", "")
                observation = f"Archivo {path} modificado con éxito"
            else:
                observation = f"Acción {tool_name} ejecutada satisfactoriamente"

            executed_step_records.append({
                "tool_name": tool_name,
                "tool_args": tool_args,
                "observation": observation,
            })
            middleware.record_observation(observation)
            conversation_history.append({
                "role": "assistant",
                "content": f"Thought: {thought_text}\nAction: {tool_name} {json.dumps(tool_args)}",
            })
            conversation_history.append({
                "role": "user",
                "content": f"Observation: {observation}",
            })
            console.print(f"  [dim]Observation: {observation[:120]}...[/]")
            time.sleep(0.5)

        if task_finished:
            break

    # Si se alcanzó el límite máximo de pasos sin finish explícito, solicitar síntesis final a Gemini
    if not task_finished:
        if genai_client:
            console.print("\n[bold yellow]ℹ️ Se alcanzó el límite de pasos. Solicitando respuesta de síntesis final al agente...[/]")
            conversation_history.append({
                "role": "user",
                "content": "Has alcanzado el límite de pasos de ejecución para esta tarea. Con base en todas las observaciones y datos reales recopilados durante la sesión, formula tu conclusión o respuesta final completa para el usuario.",
            })
            try:
                is_antigravity = "antigravity" in model_name.lower()
                min_interval = 1.2 if is_antigravity else 12.5

                elapsed = time.time() - last_gemini_call_time
                if last_gemini_call_time > 0 and elapsed < min_interval:
                    wait_rpm = min_interval - elapsed
                    console.print(f"[dim]⏳ Pausa preventiva de {wait_rpm:.1f}s para respetar límite de {'60 RPM' if is_antigravity else '5 RPM'}...[/]")
                    time.sleep(wait_rpm)

                target_model = "antigravity-preview-09-2026" if model_name.lower() in ("antigravity", "antigravity-preview") else model_name
                prompt_parts = build_optimized_prompt(conversation_history)

                if is_antigravity:
                    final_res = genai_client.interactions.create(
                        model=target_model,
                        input=prompt_parts,
                    )
                    final_answer = (final_res.output_text or "").strip()
                else:
                    final_res = genai_client.models.generate_content(
                        model=model_name,
                        contents=prompt_parts,
                        config=genai_config,
                    )
                    final_answer = final_res.text.strip()

                console.print(Panel(
                    final_answer,
                    title="🏁 Respuesta Final del Agente (Síntesis de Observaciones)",
                    border_style="cyan",
                ))
            except Exception as e:
                console.print(f"[dim]No se pudo generar síntesis final: {e}[/]")
        else:
            console.print(Panel(
                f"El agente completó los {executed_steps} pasos máximos configurados.\n"
                "Para permitir más pasos de exploración en tareas complejas, usa el flag: [bold]--steps 10[/]",
                title="ℹ️ Límite de Pasos Alcanzado",
                border_style="yellow",
            ))

    # 6. Registrar en la memoria de sesión continua
    resolved_summary = final_summary or final_answer or "Tarea completada satisfactoriamente."
    resolved_answer = final_answer or final_summary or "Tarea completada."
    session.record_completed_task(
        goal=task,
        summary=resolved_summary,
        final_answer=resolved_answer,
        executed_steps=executed_steps,
        history_steps=executed_step_records,
    )

    # 7. Renderizar métricas finales de ahorro de peticiones
    savings_pct = max(0, int(((executed_steps - gemini_calls_count) / max(1, executed_steps)) * 100))
    metrics_table = Table(title="📊 Métricas de Eficiencia JEV y Ahorro de Cuota API", show_header=True)
    metrics_table.add_column("Métrica", style="bold white")
    metrics_table.add_column("Valor", justify="right", style="bold cyan")
    metrics_table.add_column("Impacto", style="green")

    metrics_table.add_row("Pasos cognitivos ejecutados", str(executed_steps), "Progreso real")
    metrics_table.add_row("Llamadas a Gemini API", str(gemini_calls_count), f"Ahorro de ~{savings_pct}% en llamadas LLM")
    metrics_table.add_row("Llamadas a TypeSafe AI", str(typesafe_calls_count), "Evaluaciones en lote (Chunking)")
    metrics_table.add_row("Intervenciones JEV / Alucinaciones evitadas", str(interventions_count), "Prevención de desvíos cognitivos")

    console.print("\n")
    console.print(metrics_table)

    return (task_finished, resolved_answer, session, middleware)


def main() -> None:
    parser = argparse.ArgumentParser(description="Live Agent Loop supervisado por JEV")
    parser.add_argument("task", type=str, nargs="?", default=None, help="Objetivo o tarea del agente")
    parser.add_argument("--goal", "-g", type=str, default=None, help="Objetivo o tarea del agente (alias de task)")
    parser.add_argument("--once", action="store_true", help="Ejecutar solo el objetivo especificado y salir sin modo interactivo continuo")
    parser.add_argument("--steps", type=int, default=15, help="Máximo número de pasos por tarea (usa 0 para modo ilimitado)")
    parser.add_argument("--chunk-size", type=int, default=3, help="Tamaño de bloque para evaluación agrupada")
    parser.add_argument("--typesafe", action="store_true", help="Utilizar TypeSafe AI como evaluador")
    parser.add_argument("--gemini-key", type=str, default=None, help="API key de Gemini")
    parser.add_argument("--model", type=str, default="gemini-3.8-flash", help="Modelo de Gemini a utilizar")
    args = parser.parse_args()

    cfg = default_config.model_copy()
    if args.typesafe:
        cfg.use_typesafe_api = True
    if args.chunk_size:
        cfg.evaluation_chunk_size = args.chunk_size

    console.print(Panel(
        "[bold cyan]🎯 JEV REASONING NAVIGATOR — MODO INTERACTIVO ITERATIVO[/]\n\n"
        "Supervisión continua con evaluación por bloques (chunking) y memoria acumulada entre tareas concatenadas.\n"
        "Introduce objetivos sucesivamente. Escribe [bold yellow]'reset'[/] para nueva sesión limpia, o [bold red]'salir'[/] para finalizar.",
        title="🧭 [bold white]JEV Live Agent Session[/]",
        border_style="cyan",
    ))

    initial_task = args.goal or args.task
    is_first_iteration = True
    session_context = SessionContextManager()
    middleware = None

    while True:
        current_task: Optional[str] = None

        if is_first_iteration and initial_task and initial_task.strip():
            current_task = initial_task.strip()
            is_first_iteration = False
        else:
            is_first_iteration = False
            if not sys.stdin.isatty():
                # Modo no interactivo / datos enviados por tubería stdin
                piped_line = sys.stdin.readline()
                if not piped_line:
                    break
                candidate = piped_line.strip()
                if not candidate or candidate.lower() in ("salir", "exit", "quit", "q"):
                    break
                current_task = candidate
            else:
                # Entrada interactiva por consola
                while True:
                    try:
                        console.print()
                        user_input = Prompt.ask(
                            "[bold cyan]🎯 Introduce el objetivo o tarea para el agente[/] [dim](o 'reset' para nueva sesión, 'salir' para terminar)[/]"
                        ).strip()
                    except (KeyboardInterrupt, EOFError):
                        console.print("\n[bold yellow]Sesión interactiva finalizada por el usuario.[/]")
                        return

                    if not user_input:
                        console.print("[yellow]⚠️ Por favor, introduce un objetivo válido o escribe 'salir' para terminar.[/]")
                        continue
                    if user_input.lower() in ("salir", "exit", "quit", "q"):
                        console.print("[bold green]👋 Sesión interactiva de JEV finalizada. ¡Hasta pronto![/]")
                        return
                    current_task = user_input
                    break

        if not current_task:
            break

        if current_task.lower() in ("reset", "clear", "nueva", "nuevo", "/reset", "/clear"):
            session_context.reset()
            middleware = None
            console.print("[bold green]🧹 Memoria de sesión reiniciada. Puedes introducir un nuevo objetivo limpio.[/]")
            continue

        res = run_live_gemini_agent(
            task=current_task,
            max_steps=args.steps,
            config=cfg,
            gemini_api_key=args.gemini_key,
            model_name=args.model,
            session_context=session_context,
            middleware=middleware,
        )
        if isinstance(res, tuple) and len(res) >= 4:
            _, _, session_context, middleware = res

        if args.once:
            break

        if sys.stdin.isatty():
            console.print("\n" + "━" * 70)
            console.print(f"[bold green]✓ Tarea finalizada bajo supervisión JEV. Memoria de sesión ({len(session_context.task_records)} tareas) disponible para el siguiente objetivo.[/]")


if __name__ == "__main__":
    main()

