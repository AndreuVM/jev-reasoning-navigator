"""Políticas de intervención cognitiva, poda forzada y generación de directivas de desbloqueo."""

from typing import List, Optional
from jev_navigator.config import JEVConfig, default_config
from jev_navigator.core.state_graph import StateGraph
from jev_navigator.models.schema import (
    InterventionDirective,
    InterventionLevel,
    JEVScore,
    LoopReport,
    LoopType,
    Step,
)


class InterventionPolicy:
    """Motor de decisión y formulación de directivas correctivas para agentes LLM."""

    def __init__(self, state_graph: StateGraph, config: Optional[JEVConfig] = None):
        self.graph = state_graph
        self.config = config or state_graph.config or default_config

    def evaluate_and_intervene(
        self,
        current_step: Optional[Step] = None,
        jev_score: Optional[JEVScore] = None,
        loop_report: Optional[LoopReport] = None,
    ) -> Optional[InterventionDirective]:
        """Evalúa las condiciones de la trayectoria y genera una directiva de intervención si aplica."""
        if loop_report is None or not loop_report.loop_detected:
            # Si no hay loop detectado pero el JEV es crítico (< 0.0)
            if jev_score and jev_score.total_jev < self.config.critical_jev_threshold:
                return self._generate_level_1_directive(
                    loop_report or LoopReport(loop_detected=False),
                    current_step,
                    reason=f"El Joint Expected Value ({jev_score.total_jev:.2f}) cayó por debajo del umbral crítico ({self.config.critical_jev_threshold:.2f})."
                )
            return None

        # Determinar nivel de severidad de la intervención
        if loop_report.loop_type == LoopType.HALLUCINATION:
            return self._generate_hallucination_directive(loop_report, current_step)
        elif loop_report.loop_type == LoopType.UNGROUNDED_PREMISE:
            return self._generate_ungrounded_premise_directive(loop_report, current_step)
        elif loop_report.loop_type == LoopType.ENTROPIC_STAGNATION:
            return self._generate_level_3_directive(loop_report, current_step)
        elif loop_report.loop_type in (LoopType.ONE_HOP_TOOL_REPEAT, LoopType.N_HOP_CYCLE):
            return self._generate_level_2_directive(loop_report, current_step)
        elif loop_report.severity >= 4:
            return self._generate_level_3_directive(loop_report, current_step)
        elif loop_report.severity >= 2 or loop_report.loop_type == LoopType.SEMANTIC_FIXATION:
            return self._generate_level_2_directive(loop_report, current_step)
        else:
            return self._generate_level_1_directive(loop_report, current_step)


    def _generate_level_1_directive(
        self,
        loop_report: LoopReport,
        current_step: Optional[Step],
        reason: Optional[str] = None,
    ) -> InterventionDirective:
        """Nivel 1 (Meta-Feedback): Aviso suave y reflexión obligatoria antes de continuar."""
        explanation = reason or loop_report.explanation or "Se ha detectado una repetición estéril de acciones."
        message = (
            f"[JEV-MONITOR | NIVEL 1 - META-FEEDBACK]\n"
            f"Alerta: {explanation}\n"
            "INSTRUCCIÓN OBLIGATORIA: Antes de invocar cualquier otra herramienta o tomar una decisión táctica, "
            "describe en exactamente 1 frase por qué tu premisa anterior no produjo el resultado esperado."
        )

        injection = (
            f"<system_intervention level='1'>\n"
            f"{message}\n"
            f"</system_intervention>"
        )

        return InterventionDirective(
            level=InterventionLevel.LEVEL_1_META_FEEDBACK,
            target_step_id=current_step.id if current_step else None,
            message=message,
            forbidden_actions=[],
            suggested_action="Reflexionar brevemente sobre el fallo antes de continuar",
            context_injection=injection,
        )

    def _generate_level_2_directive(
        self,
        loop_report: LoopReport,
        current_step: Optional[Step],
    ) -> InterventionDirective:
        """Nivel 2 (Poda Forzada / Backtracking): Retroceso al último estado con alto JEV y prohibición de acción."""
        # Localizar el mejor estado previo para retroceder
        highest_step = self.graph.get_highest_jev_step()
        target_id = highest_step.id if highest_step else (
            self.graph.get_chronological_nodes()[0] if self.graph.get_chronological_nodes() else "root"
        )
        target_desc = highest_step.content if highest_step else "Estado inicial de la tarea"

        forbidden: List[str] = []
        if loop_report.culprit_tool:
            forbidden.append(loop_report.culprit_tool)

        forbidden_text = f"Queda TERMINANTEMENTE PROHIBIDO volver a ejecutar: {', '.join(forbidden)} con los mismos parámetros." if forbidden else ""

        message = (
            f"[JEV-MONITOR | NIVEL 2 - PODA FORZADA Y BACKTRACKING]\n"
            f"Alerta Crítica: {loop_report.explanation}\n"
            f"INSTRUCCIÓN OBLIGATORIA DE PODA:\n"
            f"1. La rama de razonamiento actual ha sido podada por ciclo cerrado o degenerativo.\n"
            f"2. Debes RETROCEDER de inmediato al estado '{target_id}' ({target_desc[:120]}...).\n"
            f"3. {forbidden_text}\n"
            f"4. Plantea un camino de resolución alternativo e inexplorado."
        )

        injection = (
            f"<system_intervention level='2' target_node='{target_id}'>\n"
            f"{message}\n"
            f"</system_intervention>"
        )

        return InterventionDirective(
            level=InterventionLevel.LEVEL_2_FORCED_BACKTRACKING,
            target_step_id=target_id,
            message=message,
            forbidden_actions=forbidden,
            suggested_action=f"Retroceder al paso {target_id} y explorar hipótesis disyuntiva",
            context_injection=injection,
        )

    def _generate_level_3_directive(
        self,
        loop_report: LoopReport,
        current_step: Optional[Step],
    ) -> InterventionDirective:
        """Nivel 3 (Cambio de Nivel de Abstracción): Pausa táctica y Abogado del Diablo."""
        message = (
            "[JEV-MONITOR | NIVEL 3 - INTERVENCIÓN CRÍTICA DE ABSTRACCIÓN]\n"
            f"Emergencia Cognitiva: {loop_report.explanation}\n"
            "PARADA TÁCTICA OBLIGATORIA:\n"
            "Has caído en parálisis por análisis o fijación intratable. Se suspende la ejecución táctica.\n"
            "MODO ABOGADO DEL DIABLO FORZADO:\n"
            "1. Enumera 3 razones fundamentales por las cuales tu premisa original es COMPLETAMENTE FALSA.\n"
            "2. Pregúntate: '¿Qué información o supuesto no he cuestionado hasta ahora?'\n"
            "3. Redefine la estrategia desde un nivel de abstracción superior antes de intentar cualquier acción."
        )

        injection = (
            "<system_intervention level='3' mode='devils_advocate'>\n"
            f"{message}\n"
            "</system_intervention>"
        )

        forbidden = ["*"]
        if loop_report.culprit_tool:
            forbidden.append(loop_report.culprit_tool)

        return InterventionDirective(
            level=InterventionLevel.LEVEL_3_ABSTRACTION_SHIFT,
            target_step_id=current_step.id if current_step else None,
            message=message,
            forbidden_actions=forbidden,
            suggested_action="Reflexión de Abogado del Diablo y reformulación estratégica global",
            context_injection=injection,
        )

    def _generate_hallucination_directive(
        self,
        loop_report: LoopReport,
        current_step: Optional[Step],
    ) -> InterventionDirective:
        """Directiva de Prevención de Alucinaciones: Exige fundamentación en observaciones empíricas."""
        explanation = loop_report.explanation or "Se ha detectado una acción o afirmación no fundamentada en el contexto o en las observaciones previas."
        culprit = loop_report.culprit_tool
        forbidden = [culprit] if culprit else []
        message = (
            "[JEV-MONITOR | ANTI-ALUCINACIÓN - PREVENCIÓN DE ALUCINACIÓN DEL LLM]\n"
            f"Alerta Crítica: {explanation}\n"
            "INSTRUCCIÓN OBLIGATORIA DE FUNDAMENTACIÓN:\n"
            "1. Tu acción propuesta incluye supuestos, herramientas, archivos o afirmaciones no fundamentadas en las observaciones.\n"
            "2. Queda PROHIBIDO asumir que un comando funcionó o que un archivo existe sin haberlo verificado antes.\n"
            "3. Vuelve a examinar la última observación empírica real y formula una acción basada ÚNICAMENTE en datos observados."
        )
        injection = (
            f"<system_intervention level='2' type='anti_hallucination'>\n"
            f"{message}\n"
            f"</system_intervention>"
        )
        return InterventionDirective(
            level=InterventionLevel.LEVEL_2_FORCED_BACKTRACKING,
            target_step_id=current_step.id if current_step else None,
            message=message,
            forbidden_actions=forbidden,
            suggested_action="Verificar hechos en observaciones empíricas y corregir alucinación",
            context_injection=injection,
        )

    def _generate_ungrounded_premise_directive(
        self,
        loop_report: LoopReport,
        current_step: Optional[Step],
    ) -> InterventionDirective:
        """Aviso de premisa no fundamentada: Exige validar antes de concluir."""
        explanation = loop_report.explanation or "Se ha asumido que el problema está resuelto o que un estado cambió sin validación empírica."
        message = (
            "[JEV-MONITOR | PREMISA NO FUNDAMENTADA]\n"
            f"Aviso: {explanation}\n"
            "INSTRUCCIÓN OBLIGATORIA: Antes de declarar la tarea terminada o cambiar de fase, "
            "ejecuta una herramienta de verificación (ej. compilar, ejecutar pruebas o leer archivo) para comprobar empíricamente el estado."
        )
        injection = (
            f"<system_intervention level='1' type='ungrounded_premise'>\n"
            f"{message}\n"
            f"</system_intervention>"
        )
        return InterventionDirective(
            level=InterventionLevel.LEVEL_1_META_FEEDBACK,
            target_step_id=current_step.id if current_step else None,
            message=message,
            forbidden_actions=[],
            suggested_action="Ejecutar prueba o verificación empírica antes de continuar",
            context_injection=injection,
        )

