"""Middleware proxy para interceptar y supervisar llamadas de agentes LLM en tiempo real."""

from typing import Any, Callable, Dict, List, Optional, Tuple

from jev_navigator.config import JEVConfig, default_config
from jev_navigator.core.intervention_policy import InterventionPolicy
from jev_navigator.core.jev_engine import JEVEngine
from jev_navigator.core.state_graph import StateGraph
from jev_navigator.models.schema import (
    ActionCandidate,
    ChunkEvaluationResult,
    InterventionDirective,
    InterventionLevel,
    LoopReport,
    LoopType,
    Step,
    StepType,
    Trajectory,
)


class JEVProxyMiddleware:
    """Interceptor de flujo para agentes autónomos supervisado por TypeSafe AI."""

    def __init__(self, goal: str, config: Optional[JEVConfig] = None):
        self.config = config or default_config
        self.goal = goal
        self.trajectory = Trajectory(session_id="proxy_session", goal=goal, steps=[])
        self.graph = StateGraph(self.config)
        self.graph.load_trajectory(self.trajectory)
        self.engine = JEVEngine(self.graph, self.config)
        self.policy = InterventionPolicy(self.graph, self.config)

    def intercept_step_chunk(
        self,
        proposed_steps: List[Dict[str, Any]],
    ) -> ChunkEvaluationResult:
        """Supervisa y valida un bloque agrupado de pasos candidatos en una sola llamada a TypeSafe AI."""
        if not proposed_steps:
            return ChunkEvaluationResult(all_safe=True, valid_step_count=0, explanation="Bloque vacío")

        start_idx = len(self.graph.get_chronological_nodes())
        candidate_steps: List[Step] = []

        for offset, p in enumerate(proposed_steps):
            step_id = f"step_{start_idx + offset}"
            st_raw = p.get("step_type") or ("tool_call" if p.get("tool_name") else "thought")
            st_type = StepType(st_raw) if st_raw in StepType._value2member_map_ else StepType.TOOL_CALL
            step = Step(
                id=step_id,
                step_type=st_type,
                content=p.get("thought_rationale") or p.get("content") or "",
                tool_name=p.get("tool_name"),
                tool_args=p.get("tool_args"),
            )
            candidate_steps.append(step)

        # Evaluar todo el bloque agrupado mediante TypeSafe AI
        eval_results = self.engine.evaluate_step_chunk(candidate_steps)
        step_scores = [sc for _, sc, _ in eval_results]

        # Verificar paso a paso la convergencia y detectar el primer fallo
        for idx, (step, score, metadata) in enumerate(eval_results):
            # Probar inserción provisional en el grafo
            self.graph.add_step(step)
            self.graph.set_step_jev(step.id, score.total_jev)

            # Comprobar si TypeSafe reportó loop o alucinación en este paso
            is_ts_loop = bool(metadata and metadata.get("is_loop") and metadata.get("flagged_index") == idx)
            is_hallucination = bool(metadata and metadata.get("is_hallucination") and metadata.get("flagged_index") == idx)
            hallucination_type = metadata.get("hallucination_type") if metadata else None
            is_divergent = bool(score.details.get("is_divergent", False))

            # Las herramientas de solo lectura/inspección empírica no pueden ser alucinaciones destructivas
            is_observational = (
                step.tool_name in ("read_file", "view_file", "grep_search", "list_dir", "cat") or
                (step.tool_name == "run_command" and any(c in str(step.tool_args or {}).lower() for c in ("dir", "ls", "grep", "cat", "status", "inspect", "head", "tail", "type ", "echo ", "version", "get-childitem", "get-content")))
            )
            is_terminal = (step.tool_name == "finish")
            is_evasive_finish = False

            if is_terminal:
                summary_raw = str((step.tool_args or {}).get("summary") or "").lower()
                content_raw = str(step.content or "").lower()
                combined_finish = f"{summary_raw} {content_raw}"

                # 1. Comprobar si el finish es evasivo, un placeholder o una excusa de planificación
                evasive_markers = (
                    "pendiente de", "pendiente", "planificación", "planificacion",
                    "como soy un agente", "la acción real", "la accion real",
                    "todavía no", "aún no he", "aun no he", "sin analizar",
                    "no he podido leer", "no he podido", "provisional", "pending",
                    "este paso es de"
                )
                if any(m in combined_finish for m in evasive_markers):
                    is_evasive_finish = True

                # 2. Comprobar si viene en el mismo bloque donde hay acciones de lectura previas
                has_prior_unexecuted_inspection = any(
                    prev_c.tool_name in ("read_file", "view_file", "run_command")
                    for prev_c in candidate_steps[:idx]
                )
                if has_prior_unexecuted_inspection:
                    is_evasive_finish = True

            if is_observational and is_hallucination:
                is_hallucination = False
                is_divergent = False

            if is_evasive_finish:
                is_terminal = False
                is_hallucination = True
                is_divergent = True
                score.total_jev = -0.5
                hallucination_type = "evasive_or_premature_finish"
            elif is_terminal:
                # La acción terminal finish es genuina y concluye la tarea
                is_hallucination = False
                is_divergent = False
                is_ts_loop = False
                score.total_jev = max(0.90, score.total_jev)

            loop_detected = is_ts_loop or is_hallucination or is_divergent or (not is_observational and not is_terminal and score.total_jev < self.config.critical_jev_threshold)
            loop_rep = LoopReport(loop_detected=False)

            if loop_detected:
                if is_evasive_finish:
                    loop_rep = LoopReport(
                        loop_detected=True,
                        loop_type=LoopType.UNGROUNDED_PREMISE,
                        severity=4,
                        explanation=(
                            f"Finalización evasiva o prematura rechazada en paso {step.id}: "
                            "El agente intentó finalizar con una excusa de planificación ('pendiente de lectura') "
                            "o antes de examinar las observaciones. Debe formular su conclusión real usando las observaciones ya obtenidas."
                        ),
                        culprit_tool=step.tool_name,
                    )
                elif is_hallucination:
                    loop_rep = LoopReport(
                        loop_detected=True,
                        loop_type=LoopType.HALLUCINATION,
                        severity=4,
                        explanation=f"Alucinación detectada en paso {step.id}: {hallucination_type or 'afirmación o herramienta no fundamentada'}",
                        culprit_tool=step.tool_name,
                    )
                else:
                    loop_rep = LoopReport(
                        loop_detected=True,
                        loop_type=metadata.get("loop_type", LoopType.ONE_HOP_TOOL_REPEAT) if metadata else LoopType.ONE_HOP_TOOL_REPEAT,
                        severity=3,
                        explanation=f"Poda preventiva JEV activada: acción divergente en paso {step.id}",
                        culprit_tool=step.tool_name,
                    )

            directive = self.policy.evaluate_and_intervene(
                current_step=step,
                jev_score=score,
                loop_report=loop_rep,
            )

            if loop_detected:
                if not directive:
                    directive = self.policy._generate_level_2_directive(loop_rep, step)

                # Revertir inserciones provisionales desde este paso en adelante
                for rev_step in candidate_steps[idx:]:
                    self.graph.remove_step(rev_step.id)

                return ChunkEvaluationResult(
                    all_safe=False,
                    valid_step_count=idx,
                    flagged_step_index=idx,
                    step_scores=step_scores,
                    directive=directive,
                    loop_report=loop_rep,
                    hallucination_detected=is_hallucination,
                    hallucination_type=hallucination_type,
                    explanation=directive.message,
                )

        return ChunkEvaluationResult(
            all_safe=True,
            valid_step_count=len(candidate_steps),
            flagged_step_index=None,
            step_scores=step_scores,
            directive=None,
            loop_report=None,
            hallucination_detected=False,
            explanation="Bloque completo validado como convergente y fundamentado",
        )

    def intercept_tool_call(
        self,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
        thought_rationale: str = "",
    ) -> Tuple[bool, Optional[str]]:
        """Intercepta una llamada a herramienta individual antes de su ejecución mediante TypeSafe AI."""
        step_id = f"step_{len(self.graph.get_chronological_nodes())}"
        candidate_step = Step(
            id=step_id,
            step_type=StepType.TOOL_CALL,
            content=thought_rationale,
            tool_name=tool_name,
            tool_args=tool_args,
        )

        if tool_name == "finish":
            summary_raw = str((tool_args or {}).get("summary") or "").lower()
            content_raw = str(thought_rationale or "").lower()
            combined_finish = f"{summary_raw} {content_raw}"
            evasive_markers = (
                "pendiente de", "pendiente", "planificación", "planificacion",
                "como soy un agente", "la acción real", "la accion real",
                "todavía no", "aún no he", "aun no he", "sin analizar",
                "no he podido leer", "no he podido", "provisional", "pending",
                "este paso es de"
            )
            if any(m in combined_finish for m in evasive_markers):
                return False, (
                    "<system_intervention type=\"rejection\" level=\"critical\">\n"
                    "JEV CRITICAL: Finalización evasiva rechazada. NO puedes finalizar con 'pendiente de lectura' "
                    "ni excusas de planificación. Sintetiza y formula tu respuesta final basándote en la información y observaciones "
                    "que ya has recolectado.\n"
                    "</system_intervention>"
                )
            self.graph.add_step(candidate_step)
            self.graph.set_step_jev(step_id, 0.95)
            return True, None

        score = self.engine.evaluate_step(candidate_step)

        # Detectar bucle según TypeSafe
        ts_eval = score.details.get("typesafe_eval") or {}
        is_loop = bool(ts_eval.get("is_loop", False) or score.total_jev < self.config.critical_jev_threshold)
        loop_type = ts_eval.get("loop_type", LoopType.ONE_HOP_TOOL_REPEAT if is_loop else LoopType.NONE)

        loop_rep = LoopReport(
            loop_detected=is_loop,
            loop_type=loop_type,
            severity=3 if is_loop else 0,
            explanation=f"Reintento o acción no constructiva detectada para herramienta '{tool_name}'",
            culprit_tool=tool_name,
        )

        directive = self.policy.evaluate_and_intervene(
            current_step=candidate_step,
            jev_score=score,
            loop_report=loop_rep,
        )

        if is_loop and directive:
            return False, directive.context_injection

        self.graph.add_step(candidate_step)
        self.graph.set_step_jev(step_id, score.total_jev)
        return True, None

    def record_observation(self, observation_text: str) -> None:
        """Registra el resultado/observación devuelto por una herramienta ejecutada."""
        step_id = f"obs_{len(self.graph.get_chronological_nodes())}"
        obs_step = Step(
            id=step_id,
            step_type=StepType.OBSERVATION,
            content=observation_text,
        )
        self.graph.add_step(obs_step)

    def record_thought(self, thought_text: str) -> Tuple[bool, Optional[str]]:
        """Registra un pensamiento reflexivo y evalúa convergencia mediante TypeSafe AI."""
        step_id = f"th_{len(self.graph.get_chronological_nodes())}"
        th_step = Step(
            id=step_id,
            step_type=StepType.THOUGHT,
            content=thought_text,
        )
        score = self.engine.evaluate_step(th_step)
        ts_eval = score.details.get("typesafe_eval") or {}
        is_loop = bool(ts_eval.get("is_loop", False) or score.total_jev < self.config.critical_jev_threshold)

        if is_loop:
            loop_rep = LoopReport(
                loop_detected=True,
                loop_type=ts_eval.get("loop_type", LoopType.SEMANTIC_FIXATION),
                severity=2,
                explanation="Fijación o estancamiento reflexivo detectado",
            )
            directive = self.policy.evaluate_and_intervene(
                current_step=th_step,
                jev_score=score,
                loop_report=loop_rep,
            )
            if directive:
                return False, directive.context_injection

        self.graph.add_step(th_step)
        self.graph.set_step_jev(step_id, score.total_jev)
        return True, None

    def start_subtask(self, new_goal: str) -> None:
        """Transiciona la supervisión hacia una nueva tarea concatenada preservando la memoria acumulada."""
        self.goal = new_goal
        self.graph.goal = new_goal
        trans_id = f"subtask_trans_{len(self.graph.get_chronological_nodes())}"
        step = Step(
            id=trans_id,
            step_type=StepType.THOUGHT,
            content=f"[TRANSICIÓN A NUEVA TAREA]: {new_goal}",
        )
        self.graph.add_step(step)
        self.graph.set_step_jev(trans_id, 1.0)


