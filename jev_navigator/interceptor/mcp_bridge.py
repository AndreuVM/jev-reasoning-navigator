"""Servidor y Bridge Model Context Protocol (MCP) para conectar con agentes en tiempo real."""

import json
import sys
from typing import Any, Dict, List, Optional

from jev_navigator.config import JEVConfig, default_config
from jev_navigator.core.intervention_policy import InterventionPolicy
from jev_navigator.core.jev_engine import JEVEngine
from jev_navigator.core.state_graph import StateGraph
from jev_navigator.models.schema import ActionCandidate, LoopReport, LoopType, Step, StepType, Trajectory
from jev_navigator.models.trace import TraceParser


class MCPBridge:
    """Implementación de herramientas MCP para supervisión de razonamiento LLM."""

    def __init__(self, config: Optional[JEVConfig] = None):
        self.config = config or default_config

    def evaluate_next_step(
        self,
        goal: str,
        history: List[Dict[str, Any]],
        proposed_step: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evalúa un siguiente paso propuesto frente al historial y meta del agente mediante TypeSafe AI."""
        trajectory = Trajectory(
            session_id="mcp_session",
            goal=goal,
            steps=[]
        )
        for idx, h in enumerate(history):
            s_type = StepType(h.get("step_type", "thought"))
            step = Step(
                id=h.get("id", f"hist_{idx}"),
                step_type=s_type,
                content=h.get("content", ""),
                tool_name=h.get("tool_name"),
                tool_args=h.get("tool_args"),
            )
            trajectory.add_step(step)

        graph = StateGraph(self.config)
        graph.load_trajectory(trajectory)

        engine = JEVEngine(graph, self.config)
        policy = InterventionPolicy(graph, self.config)

        # Evaluar candidato
        cand_type = StepType(proposed_step.get("step_type", "thought"))
        cand_step = Step(
            id="proposed_candidate",
            step_type=cand_type,
            content=proposed_step.get("content", ""),
            tool_name=proposed_step.get("tool_name"),
            tool_args=proposed_step.get("tool_args"),
        )
        score = engine.evaluate_step(cand_step)

        ts_eval = score.details.get("typesafe_eval") or {}
        is_loop = bool(ts_eval.get("is_loop", False) or score.total_jev < self.config.critical_jev_threshold)
        loop_type = ts_eval.get("loop_type", LoopType.ONE_HOP_TOOL_REPEAT if is_loop else LoopType.NONE)

        loop_rep = LoopReport(
            loop_detected=is_loop,
            loop_type=loop_type,
            severity=3 if is_loop else 0,
            explanation=f"Evaluación TypeSafe: {'bucle o estancamiento detectado' if is_loop else 'acción constructiva'}",
            culprit_tool=cand_step.tool_name,
        )

        directive = policy.evaluate_and_intervene(
            current_step=cand_step,
            jev_score=score,
            loop_report=loop_rep,
        )

        is_safe = not is_loop and (score.total_jev >= self.config.critical_jev_threshold)

        return {
            "safe": is_safe,
            "total_jev": score.total_jev,
            "p_progress": score.p_progress,
            "delta_u": score.delta_u,
            "loop_penalty": score.loop_penalty,
            "loop_detected": loop_rep.loop_detected,
            "loop_type": loop_rep.loop_type.value,
            "severity": loop_rep.severity,
            "explanation": loop_rep.explanation,
            "directive": directive.model_dump() if directive else None,
        }

    def diagnose_trace(self, trace_data: Dict[str, Any]) -> Dict[str, Any]:
        """Diagnostica una traza completa usando TypeSafe AI y retorna el informe global."""
        trajectory = TraceParser.from_dict(trace_data)
        graph = StateGraph(self.config)
        graph.load_trajectory(trajectory)

        engine = JEVEngine(graph, self.config)
        policy = InterventionPolicy(graph, self.config)

        loop_rep = engine.diagnose_trajectory(trajectory)
        step_scores = []
        for step in trajectory.steps:
            sc = engine.evaluate_step(step)
            step_scores.append({
                "step_id": step.id,
                "type": step.step_type.value,
                "jev": sc.total_jev,
            })

        directive = policy.evaluate_and_intervene(
            current_step=trajectory.steps[-1] if trajectory.steps else None,
            loop_report=loop_rep,
        )

        return {
            "session_id": trajectory.session_id,
            "total_steps": len(trajectory.steps),
            "loop_detected": loop_rep.loop_detected,
            "loop_type": loop_rep.loop_type.value,
            "severity": loop_rep.severity,
            "culprit_tool": loop_rep.culprit_tool,
            "explanation": loop_rep.explanation,
            "step_scores": step_scores,
            "directive": directive.model_dump() if directive else None,
        }

    def evaluate_step_chunk(
        self,
        goal: str,
        history: List[Dict[str, Any]],
        proposed_steps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Evalúa un bloque agrupado de pasos candidatos para supervisión eficiente y ahorro de RPM/RPD."""
        from jev_navigator.interceptor.proxy_middleware import JEVProxyMiddleware

        middleware = JEVProxyMiddleware(goal=goal, config=self.config)
        for h in history:
            s_type = StepType(h.get("step_type", "thought"))
            if s_type == StepType.OBSERVATION:
                middleware.record_observation(h.get("content", ""))
            elif s_type == StepType.THOUGHT:
                middleware.record_thought(h.get("content", ""))
            else:
                middleware.graph.add_step(Step(
                    id=h.get("id", f"hist_{len(middleware.graph.get_chronological_nodes())}"),
                    step_type=s_type,
                    content=h.get("content", ""),
                    tool_name=h.get("tool_name"),
                    tool_args=h.get("tool_args"),
                ))

        res = middleware.intercept_step_chunk(proposed_steps)
        return {
            "all_safe": res.all_safe,
            "valid_step_count": res.valid_step_count,
            "flagged_step_index": res.flagged_step_index,
            "hallucination_detected": res.hallucination_detected,
            "hallucination_type": res.hallucination_type,
            "explanation": res.explanation,
            "directive": res.directive.model_dump() if res.directive else None,
            "step_scores": [s.model_dump() for s in res.step_scores],
        }

    def _handle_request(self, req: Dict[str, Any]) -> None:
        """Procesa una solicitud JSON-RPC individual y escribe la respuesta en stdout."""
        try:
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "initialize":
                out = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "jev-navigator",
                            "version": "0.1.0"
                        }
                    }
                }
            elif method == "ping":
                out = {"jsonrpc": "2.0", "id": req_id, "result": {}}
            elif method and method.startswith("notifications/"):
                # Las notificaciones en JSON-RPC no requieren respuesta
                return
            elif method == "tools/list":
                res = {
                    "tools": [
                        {
                            "name": "jev_evaluate_next_step",
                            "description": "Evalúa mediante JEV si la siguiente acción de razonamiento o llamada a herramienta es convergente o degenerativa (bucle).",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "goal": {"type": "string"},
                                    "history": {"type": "array", "items": {"type": "object"}},
                                    "proposed_step": {"type": "object"},
                                },
                                "required": ["goal", "proposed_step"],
                            },
                        },
                        {
                            "name": "jev_evaluate_step_chunk",
                            "description": "Evalúa en lote un bloque (chunk) de pasos candidatos para supervisión eficiente, prevención de alucinaciones y ahorro de peticiones.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "goal": {"type": "string"},
                                    "history": {"type": "array", "items": {"type": "object"}},
                                    "proposed_steps": {"type": "array", "items": {"type": "object"}},
                                },
                                "required": ["goal", "proposed_steps"],
                            },
                        },
                        {
                            "name": "jev_diagnose_trace",
                            "description": "Diagnostica una traza completa de razonamiento en busca de bucles y estancamiento.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "trace_data": {"type": "object"},
                                },
                                "required": ["trace_data"],
                            },
                        },
                    ]
                }
                out = {"jsonrpc": "2.0", "id": req_id, "result": res}
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                if tool_name == "jev_evaluate_next_step":
                    result = self.evaluate_next_step(
                        goal=arguments.get("goal", ""),
                        history=arguments.get("history", []),
                        proposed_step=arguments.get("proposed_step", {}),
                    )
                    out = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}}
                elif tool_name == "jev_evaluate_step_chunk":
                    result = self.evaluate_step_chunk(
                        goal=arguments.get("goal", ""),
                        history=arguments.get("history", []),
                        proposed_steps=arguments.get("proposed_steps", []),
                    )
                    out = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}}
                elif tool_name == "jev_diagnose_trace":
                    result = self.diagnose_trace(arguments.get("trace_data", {}))
                    out = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}}
                else:
                    out = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}
            else:
                out = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method {method} not handled"}}

            sys.stdout.write(json.dumps(out) + "\n")

            sys.stdout.flush()
        except Exception as e:
            err_resp = {"jsonrpc": "2.0", "id": req.get("id"), "error": {"code": -32603, "message": str(e)}}
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()

    def run_stdio_server(self) -> None:
        """Bucle de servidor MCP estándar JSON-RPC 2.0 sobre stdin/stdout con soporte de framing robusto."""
        if hasattr(sys.stdin, "reconfigure"):
            try:
                sys.stdin.reconfigure(encoding="utf-8")
            except Exception:
                pass
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass

        buffer = ""
        content_length: Optional[int] = None

        while True:
            # Framing estilo Content-Length (LSP / MCP HTTP/stdio header)
            if content_length is not None:
                body = sys.stdin.read(content_length)
                content_length = None
                if not body:
                    break
                try:
                    req = json.loads(body)
                except Exception as e:
                    err_resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}}
                    sys.stdout.write(json.dumps(err_resp) + "\n")
                    sys.stdout.flush()
                    continue
                self._handle_request(req)
                continue

            line = sys.stdin.readline()
            if not line:
                break

            stripped = line.strip()
            # Ignorar silenciosamente líneas vacías/en blanco (ej. enter en consola)
            if not buffer and not stripped:
                continue

            # Detectar encabezados estilo Content-Length
            if stripped.lower().startswith("content-length:"):
                parts = stripped.split(":")
                try:
                    content_length = int(parts[1].strip())
                except ValueError:
                    content_length = None
                # Consumir líneas de encabezado restantes hasta la línea vacía
                while True:
                    h_line = sys.stdin.readline()
                    if not h_line or not h_line.strip():
                        break
                continue

            buffer += line
            try:
                req = json.loads(buffer)
                buffer = ""  # Parse exitoso, reiniciar buffer
            except json.JSONDecodeError:
                # Si el contenido no empieza con estructura JSON, reportar y reiniciar
                if not buffer.strip().startswith(("{", "[")):
                    err_resp = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {buffer.strip()}"},
                    }
                    sys.stdout.write(json.dumps(err_resp) + "\n")
                    sys.stdout.flush()
                    buffer = ""
                # Si empieza con '{' o '[', continuar acumulando líneas para JSON multilínea
                continue

            self._handle_request(req)


if __name__ == "__main__":
    bridge = MCPBridge()
    bridge.run_stdio_server()
