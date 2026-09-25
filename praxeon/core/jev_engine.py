"""Motor de evaluación de acciones y trayectorias basado en TypeSafe AI (Saneado v0.2).

Corrige los fallos basales identificados en la auditoría:
- Erradica el fallback permisivo (fail-open) asignando disponibilidad False ante caídas.
- Parametriza BatchSemantics(independent=True/False) para evitar penalizaciones espurias en cascada.
- Emite tanto JEVScore analítico como ProviderAssessment multidimensional estructurado.
"""

from typing import Any, Dict, List, Optional, Tuple

from praxeon.config import JEVConfig, default_config
from praxeon.core.state_graph import StateGraph
from praxeon.core.typesafe_client import TypeSafeJEVClient
from praxeon.domain.models import ProviderAssessment
from praxeon.models.schema import (
    ActionCandidate,
    BatchSemantics,
    JEVScore,
    LoopReport,
    LoopType,
    Step,
    StepType,
    Trajectory,
)


class JEVEngine:
    """Motor de evaluación cognitiva sin supuestos permisivos en caídas."""

    def __init__(self, state_graph: StateGraph, config: Optional[JEVConfig] = None):
        self.graph = state_graph
        self.config = config or state_graph.config or default_config
        self.typesafe_client = TypeSafeJEVClient(self.config)

    def evaluate_candidate(self, candidate: ActionCandidate) -> JEVScore:
        """Evalúa un candidato individual mediante TypeSafe AI y retorna su puntuación JEV estructurada."""
        typesafe_eval = None
        history_steps = [s for s in self.graph.get_all_steps() if s.id != candidate.id]
        is_provider_up = self.typesafe_client.is_available()

        if is_provider_up:
            typesafe_eval = self.typesafe_client.evaluate_candidate(
                goal=self.graph.goal,
                history=history_steps,
                candidate=candidate,
            )

        # Hallazgo 3.2: Erradicación de Fail-Open
        if typesafe_eval is not None:
            p_progress = float(typesafe_eval.get("p_progress", 0.5))
            delta_u = float(typesafe_eval.get("delta_u", 0.5))
            loop_penalty = float(typesafe_eval.get("loop_penalty", 0.0))
            is_available = True
            raw_jev = ((p_progress + delta_u) / 2.0) - loop_penalty
            total_jev = max(-1.0, min(1.0, float(raw_jev)))
        else:
            # Proveedor indisponible o con fallo: NO asignar puntuación neutral permisiva
            p_progress = 0.0
            delta_u = 0.0
            loop_penalty = 0.0
            total_jev = -0.5  # Penalización preventiva para indicar indisponibilidad/incertidumbre
            raw_jev = -0.5
            is_available = False

        details = {
            "source": "typesafe_ai",
            "goal": self.graph.goal,
            "raw_score": raw_jev,
            "typesafe_eval": typesafe_eval,
            "provider_available": is_available,
        }

        return JEVScore(
            candidate_id=candidate.id,
            p_progress=round(p_progress, 4),
            delta_u=round(delta_u, 4),
            loop_penalty=round(loop_penalty, 4),
            total_jev=round(total_jev, 4),
            details=details,
        )

    def evaluate_candidate_assessment(self, candidate: ActionCandidate) -> ProviderAssessment:
        """Emite el juicio semántico formal desacoplado ProviderAssessment (Hallazgo 3.1)."""
        score = self.evaluate_candidate(candidate)
        ts_eval = score.details.get("typesafe_eval") or {}
        available = bool(score.details.get("provider_available", False))

        if not available:
            return ProviderAssessment(
                provider="typesafe",
                available=False,
                confidence=0.0,
                failure_reason="Proveedor TypeSafe AI no disponible o sin respuesta válida",
                reason_codes=["PROVIDER_OFFLINE"],
            )

        loop_prob = float(ts_eval.get("loop_penalty", score.loop_penalty))
        return ProviderAssessment(
            provider="typesafe",
            model="system-one-v1",
            available=True,
            confidence=float(ts_eval.get("confidence", 0.9)),
            loop_probability=loop_prob,
            grounded_probability=float(ts_eval.get("grounded_prob", 0.95 if loop_prob < 0.3 else 0.2)),
            progress_probability=score.p_progress,
            novelty_probability=score.delta_u,
            analytical_jev=score.total_jev,
            reason_codes=["EVALUATED_BY_TYPESAFE"],
        )

    def evaluate_candidate_chunk(
        self,
        candidates: List[ActionCandidate],
        batch_semantics: Optional[BatchSemantics] = None,
    ) -> List[Tuple[ActionCandidate, JEVScore, Optional[Dict[str, Any]]]]:
        """Evalúa un bloque agrupado de candidatos respetando BatchSemantics (Hallazgo 3.3)."""
        if not candidates:
            return []

        chunk_eval = None
        candidate_ids = {c.id for c in candidates}
        history_steps = [s for s in self.graph.get_all_steps() if s.id not in candidate_ids]
        is_provider_up = self.typesafe_client.is_available()

        if is_provider_up:
            chunk_eval = self.typesafe_client.evaluate_step_chunk(
                goal=self.graph.goal,
                history=history_steps,
                candidates=candidates,
            )

        results: List[Tuple[ActionCandidate, JEVScore, Optional[Dict[str, Any]]]] = []
        flagged_idx = chunk_eval.get("flagged_index") if chunk_eval else None
        is_independent = batch_semantics.independent if batch_semantics else False

        for idx, cand in enumerate(candidates):
            if chunk_eval is not None:
                # Comprobar si este paso diverge
                if flagged_idx is not None and idx >= flagged_idx:
                    is_exact_flagged = (idx == flagged_idx)
                    # Si el lote es independiente, pasos posteriores al índice flaggeado no se penalizan en cascada
                    if is_independent and not is_exact_flagged:
                        p_progress = float(chunk_eval.get("p_progress", 0.7))
                        delta_u = float(chunk_eval.get("delta_u", 0.7))
                        loop_penalty = 0.0
                    else:
                        p_progress = 0.05 if is_exact_flagged else 0.01
                        delta_u = 0.0
                        loop_penalty = float(chunk_eval.get("loop_penalty", 1.5))
                else:
                    p_progress = float(chunk_eval.get("p_progress", 0.8))
                    delta_u = float(chunk_eval.get("delta_u", 0.8))
                    loop_penalty = 0.0

                raw_jev = ((p_progress + delta_u) / 2.0) - loop_penalty
                total_jev = max(-1.0, min(1.0, float(raw_jev)))
                is_available = True
            else:
                # Hallazgo 3.2: Proveedor offline en evaluación de chunk
                p_progress = 0.0
                delta_u = 0.0
                loop_penalty = 0.0
                total_jev = -0.5
                raw_jev = -0.5
                is_available = False

            details = {
                "source": "typesafe_ai_chunk",
                "goal": self.graph.goal,
                "raw_score": raw_jev,
                "chunk_eval": chunk_eval,
                "provider_available": is_available,
                "is_divergent": bool(flagged_idx is not None and (idx == flagged_idx or (not is_independent and idx > flagged_idx))),
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
        self,
        steps: List[Step],
        batch_semantics: Optional[BatchSemantics] = None,
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
        cand_results = self.evaluate_candidate_chunk(candidates, batch_semantics=batch_semantics)
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
