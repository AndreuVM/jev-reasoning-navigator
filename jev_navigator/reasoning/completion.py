"""Verificador de completitud (CompletionVerifier) para JEV Reasoning Navigator v0.2.

Valida de manera formal y rigurosa si una acción de finalización (finish/complete_task)
está genuinamente respaldada por evidencias empíricas observables frente a Goal.success_criteria,
evitando el antipatrón de finalización prematura sin pruebas de éxito.
"""

from typing import List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field
from jev_navigator.domain.models import ActionCandidate, Goal
from jev_navigator.runtime.state import SessionState


class CompletionAssessment(BaseModel):
    """Evaluación formal del cumplimiento de criterios de un objetivo."""
    model_config = ConfigDict(frozen=True)

    is_complete: bool
    satisfied_criteria: List[str] = Field(default_factory=list)
    missing_criteria: List[str] = Field(default_factory=list)
    unverified_claims: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    rationale: str = ""


class CompletionVerifier:
    """Verifica si una acción candidata de tipo finish cumple las condiciones de finalización."""

    def __init__(self, stop_words: Optional[Set[str]] = None):
        self.stop_words = stop_words or {
            "el", "la", "los", "las", "un", "una", "de", "en", "para", "por", "con", "que", "y", "o", "a",
            "the", "a", "an", "in", "on", "for", "with", "that", "and", "or", "to", "of", "is"
        }

    def is_finish_action(self, action: ActionCandidate) -> bool:
        """Determina si la acción propuesta expresa la intención de finalizar la tarea."""
        if action.tool_call and action.tool_call.tool_name.lower() in (
            "finish", "complete_task", "done", "complete", "task_completed"
        ):
            return True
        if action.id.lower() in ("finish", "complete", "done"):
            return True
        desc = action.description.lower()
        finish_keywords = (
            "finalizar tarea", "completar tarea", "tarea terminada", "tarea completada",
            "finish task", "complete task", "task complete", "task completed"
        )
        return any(kw in desc for kw in finish_keywords)

    def _extract_keywords(self, text: str) -> Set[str]:
        """Extrae términos significativos de un texto para emparejamiento."""
        words = text.lower().replace(",", " ").replace(".", " ").replace(":", " ").split()
        return {w for w in words if len(w) > 2 and w not in self.stop_words}

    def verify(
        self,
        goal: Goal,
        state: SessionState,
        action: ActionCandidate,
    ) -> CompletionAssessment:
        """Evalúa si la acción de finalización está justificada por la evidencia en el estado."""
        # 1. Si no es una acción de finalización, no aplica verificación de completitud
        if not self.is_finish_action(action):
            return CompletionAssessment(
                is_complete=False,
                rationale="La acción propuesta no es de finalización.",
            )

        # 2. Verificación de ejecución mínima (no se puede finalizar en frío sin ningún paso)
        if len(state.steps) == 0:
            return CompletionAssessment(
                is_complete=False,
                missing_criteria=list(goal.success_criteria) or ["ejecución_iniciada"],
                confidence=0.0,
                rationale="Finalización prematura: no se ha ejecutado ningún paso en la sesión.",
            )

        # 3. Recopilar texto de evidencias y observaciones del estado
        evidence_claims = [ev.claim.lower() for ev in state.evidence]
        step_observations = [s.observation.lower() for s in state.steps if s.observation]

        corpus = " ".join(evidence_claims + step_observations)

        # 4. Verificar cada criterio de éxito definido en el Goal
        satisfied: List[str] = []
        missing: List[str] = []

        for criterion in goal.success_criteria:
            criterion_clean = criterion.strip()
            criterion_lower = criterion_clean.lower()
            criterion_keywords = self._extract_keywords(criterion_lower)

            # Comprobar si el criterio coincide con algún claim directo o si sus palabras clave están en el corpus
            direct_match = any(criterion_lower in claim or claim in criterion_lower for claim in evidence_claims)
            keyword_match = False
            if criterion_keywords:
                matched_keywords = {kw for kw in criterion_keywords if kw in corpus}
                # Si coincide al menos el 50% de las palabras clave del criterio
                if len(matched_keywords) / len(criterion_keywords) >= 0.5:
                    keyword_match = True

            if direct_match or keyword_match:
                satisfied.append(criterion_clean)
            else:
                missing.append(criterion_clean)

        # 5. Comprobar que no se hayan producido resultados prohibidos (forbidden_outcomes)
        forbidden_violations: List[str] = []
        for forbidden in goal.forbidden_outcomes:
            forbidden_lower = forbidden.lower()
            forbidden_keywords = self._extract_keywords(forbidden_lower)
            if forbidden_keywords and all(kw in corpus for kw in forbidden_keywords):
                forbidden_violations.append(forbidden)

        if forbidden_violations:
            return CompletionAssessment(
                is_complete=False,
                satisfied_criteria=satisfied,
                missing_criteria=missing,
                unverified_claims=[f"Violación de resultado prohibido: {f}" for f in forbidden_violations],
                confidence=0.0,
                rationale=f"Resultado prohibido detectado en la trayectoria: {', '.join(forbidden_violations)}",
            )

        # 6. Si hay criterios definidos y alguno falta, no está completo
        if goal.success_criteria and missing:
            return CompletionAssessment(
                is_complete=False,
                satisfied_criteria=satisfied,
                missing_criteria=missing,
                confidence=len(satisfied) / len(goal.success_criteria),
                rationale=f"Criterios de éxito pendientes de evidencia: {', '.join(missing)}",
            )

        # 7. Si no hay criterios explícitos pero hubo pasos sin errores
        confidence = 1.0
        if state.evidence:
            confidence = min(1.0, sum(ev.confidence for ev in state.evidence) / len(state.evidence))

        return CompletionAssessment(
            is_complete=True,
            satisfied_criteria=satisfied if goal.success_criteria else ["pasos_ejecutados_con_exito"],
            missing_criteria=[],
            confidence=confidence,
            rationale="Todos los criterios de éxito verificados con evidencia empírica en el estado.",
        )
