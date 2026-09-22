"""Motor de evaluación de acciones y trayectorias basado exclusivamente en TypeSafe AI (System One)."""

from typing import Any, Dict, List, Optional, Tuple

from jev_navigator.config import JEVConfig, default_config
from jev_navigator.core.state_graph import StateGraph
from jev_navigator.core.typesafe_client import TypeSafeJEVClient
from jev_navigator.models.schema import ActionCandidate, JEVScore, LoopReport, LoopType, Step, StepType, Trajectory


class JEVEngine:
    """Motor de evaluación y ordenamiento cognitivo impulsado por TypeSafe AI."""

    def __init__(self, state_graph: StateGraph, config: Optional[JEVConfig] = None):
        self.graph = state_graph
        self.config = config or state_graph.config or default_config
        self.typesafe_client = TypeSafeJEVClient(self.config)

    def evaluate_candidate(self, candidate: ActionCandidate) -> JEVScore:
        """Evalúa un candidato individual mediante TypeSafe AI y retorna su puntuación JEV estructurada."""
        typesafe_eval = None
        history_steps = [s for s in self.graph.get_all_steps() if s.id != candidate.id]

        if self.typesafe_client.is_available():
            typesafe_eval = self.typesafe_client.evaluate_candidate(
                goal=self.graph.goal,
                history=history_steps,
                candidate=candidate,
            )

        if typesafe_eval is not None:
            p_progress = float(typesafe_eval.get("p_progress", 0.5))
            delta_u = float(typesafe_eval.get("delta_u", 0.5))
            loop_penalty = float(typesafe_eval.get("loop_penalty", 0.0))
        else:
            # Si TypeSafe no está disponible, puntuación neutral por defecto
            p_progress = 0.5
            delta_u = 0.5
            loop_penalty = 0.0

        # Cálculo JEV semántico: progreso + novedad normalizado - penalización por bucle/alucinación
        raw_jev = ((p_progress + delta_u) / 2.0) - loop_penalty
        total_jev = max(-1.0, min(1.0, float(raw_jev)))

        details = {
            "source": "typesafe_ai",
            "goal": self.graph.goal,
            "raw_score": raw_jev,
            "typesafe_eval": typesafe_eval,
        }

        return JEVScore(
            candidate_id=candidate.id,
            p_progress=round(p_progress, 4),
            delta_u=round(delta_u, 4),
            loop_penalty=round(loop_penalty, 4),
            total_jev=round(total_jev, 4),
            details=details,
        )

    def evaluate_candidate_chunk(
        self, candidates: List[ActionCandidate]
    ) -> List[Tuple[ActionCandidate, JEVScore, Optional[Dict[str, Any]]]]:
        """Evalúa un bloque agrupado de candidatos en una sola llamada a TypeSafe AI (System One)."""
        if not candidates:
            return []

        chunk_eval = None
        candidate_ids = {c.id for c in candidates}
        history_steps = [s for s in self.graph.get_all_steps() if s.id not in candidate_ids]

        if self.typesafe_client.is_available():
            chunk_eval = self.typesafe_client.evaluate_step_chunk(
                goal=self.graph.goal,
                history=history_steps,
                candidates=candidates,
            )

        results: List[Tuple[ActionCandidate, JEVScore, Optional[Dict[str, Any]]]] = []
        flagged_idx = chunk_eval.get("flagged_index") if chunk_eval else None

        for idx, cand in enumerate(candidates):
            if chunk_eval is not None:
                # Si este paso es el divergente o posterior en el bloque
                if flagged_idx is not None and idx >= flagged_idx:
                    is_exact_flagged = (idx == flagged_idx)
                    p_progress = 0.05 if is_exact_flagged else 0.01
                    delta_u = 0.0
                    loop_penalty = float(chunk_eval.get("loop_penalty", 1.5))
                else:
                    p_progress = float(chunk_eval.get("p_progress", 0.8))
                    delta_u = float(chunk_eval.get("delta_u", 0.8))
                    loop_penalty = 0.0
            else:
                p_progress = 0.5
                delta_u = 0.5
                loop_penalty = 0.0

            raw_jev = ((p_progress + delta_u) / 2.0) - loop_penalty
            total_jev = max(-1.0, min(1.0, float(raw_jev)))

            details = {
                "source": "typesafe_ai_chunk",
                "goal": self.graph.goal,
                "raw_score": raw_jev,
                "chunk_eval": chunk_eval,
                "is_divergent": bool(flagged_idx is not None and idx >= flagged_idx),
            }

            score = JEVScore(
                candidate_id=cand.id,
                p_progress=round(p_progress, 4),
                delta_u=round(delta_u, 4),
                loop_penalty=round(loop_penalty, 4),
                total_jev=round(total_jev, 4),
                details=details,
            )
            results.append((cand, score, chunk_eval))

        return results

    def evaluate_step_chunk(
        self, steps: List[Step]
    ) -> List[Tuple[Step, JEVScore, Optional[Dict[str, Any]]]]:
        """Convierte y evalúa un bloque de pasos existentes o propuestos mediante TypeSafe AI."""
        candidates = [
            ActionCandidate(
                id=step.id,
                description=step.content,
                tool_name=step.tool_name,
                tool_args=step.tool_args,
            )
            for step in steps
        ]
        cand_results = self.evaluate_candidate_chunk(candidates)
        step_results: List[Tuple[Step, JEVScore, Optional[Dict[str, Any]]]] = []
        for step, (_, sc, metadata) in zip(steps, cand_results):
            step_results.append((step, sc, metadata))
        return step_results

    def evaluate_step(self, step: Step) -> JEVScore:
        """Evalúa un paso de razonamiento existente en el grafo mediante TypeSafe AI."""
        candidate = ActionCandidate(
            id=step.id,
            description=step.content,
            tool_name=step.tool_name,
            tool_args=step.tool_args,
        )
        return self.evaluate_candidate(candidate)

    def rank_candidates(
        self, candidates: List[ActionCandidate]
    ) -> List[Tuple[ActionCandidate, JEVScore]]:
        """Evalúa un lote de candidatos y los devuelve ordenados de mayor a menor JEV según TypeSafe AI."""
        scored: List[Tuple[ActionCandidate, JEVScore]] = []
        for cand in candidates:
            score = self.evaluate_candidate(cand)
            scored.append((cand, score))

        scored.sort(key=lambda item: item[1].total_jev, reverse=True)
        return scored

    def diagnose_trajectory(self, trajectory: Optional[Trajectory] = None) -> LoopReport:
        """Diagnostica la trayectoria actual o proporcionada usando TypeSafe AI."""
        traj = trajectory or Trajectory(
            session_id=self.graph.session_id,
            goal=self.graph.goal,
            steps=self.graph.get_all_steps(),
        )
        return self.typesafe_client.diagnose_trajectory(traj)

