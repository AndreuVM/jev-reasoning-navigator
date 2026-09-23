"""Orquestador central (Navigator) para JEV Reasoning Navigator v0.2.

Coordina de manera desacoplada:
Proposal -> Evidence -> Risk -> JEV Provider -> Policy -> Decision -> Execution -> Observation
con soporte de checkpoints automáticos, chunking tipado y rollback determinista.
"""

from typing import Any, Dict, List, Optional, Set, Tuple
from jev_navigator.domain.interfaces import ReasoningProvider
from jev_navigator.domain.models import (
    ActionCandidate,
    DecisionReceipt,
    DecisionStatus,
    Goal,
    PolicyDecision,
    ProviderAssessment,
)
from jev_navigator.policy.engine import PolicyEngine
from jev_navigator.reasoning.completion import CompletionAssessment, CompletionVerifier
from jev_navigator.reasoning.evidence import EvidenceEngine
from jev_navigator.reasoning.risk import RiskEngine
from jev_navigator.runtime.checkpoints import Checkpoint, CheckpointManager
from jev_navigator.runtime.executor import SecureExecutor, ToolObservation
from jev_navigator.runtime.state import SessionState


class Navigator:
    """Orquestador central del ciclo de vida de supervisión y ejecución formal del agente."""

    def __init__(
        self,
        provider: ReasoningProvider,
        policy_engine: Optional[PolicyEngine] = None,
        executor: Optional[SecureExecutor] = None,
        evidence_engine: Optional[EvidenceEngine] = None,
        risk_engine: Optional[RiskEngine] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        completion_verifier: Optional[CompletionVerifier] = None,
    ):
        self.provider = provider
        self.policy_engine = policy_engine or PolicyEngine()
        self.executor = executor or SecureExecutor()
        self.evidence_engine = evidence_engine or EvidenceEngine()
        self.risk_engine = risk_engine or RiskEngine()
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.completion_verifier = completion_verifier or CompletionVerifier()

        self.state: Optional[SessionState] = None
        self.audit_receipts: List[DecisionReceipt] = []

    def start_session(self, goal: Goal, session_id: Optional[str] = None) -> SessionState:
        """Inicializa una nueva sesión de supervisión formal con checkpoint génesis."""
        sid = session_id or f"sess_{len(self.audit_receipts)}"
        self.state = SessionState(session_id=sid, goal=goal)
        self.checkpoint_manager.create_checkpoint(self.state, reason="Genesis checkpoint")
        return self.state

    def _ensure_session(self) -> SessionState:
        if self.state is None:
            raise RuntimeError("No hay una sesión activa en Navigator. Llame a start_session(goal) primero.")
        return self.state

    def is_batchable(self, action: ActionCandidate) -> bool:
        """Determina si una acción es segura para ser agrupada en un chunk (Batchable).
        
        Según el principio de chunking de v0.2:
        - Acciones batchables: lecturas independientes, observaciones sin side effects.
        - Acciones NO batchables: mutaciones, destructivas, dependientes de observaciones aún no producidas.
        """
        tool_name = action.tool_call.tool_name if action.tool_call else None
        if not tool_name:
            return True

        spec = self.policy_engine.registry.get_tool(tool_name)
        if spec:
            return spec.read_only and not spec.external_side_effect

        return False

    def propose(self, actions: List[ActionCandidate]) -> List[ActionCandidate]:
        """Filtra y valida candidatos eliminando herramientas prohibidas en el estado actual."""
        state = self._ensure_session()
        viable: List[ActionCandidate] = []
        for action in actions:
            tool_name = action.tool_call.tool_name if action.tool_call else None
            if tool_name and tool_name in state.forbidden_tools:
                continue
            viable.append(action)
        return viable

    def evaluate(
        self,
        actions: List[ActionCandidate],
    ) -> List[Tuple[ActionCandidate, ProviderAssessment, PolicyDecision, DecisionReceipt]]:
        """Evalúa un lote de acciones candidatas produciendo juicios semánticos, decisiones y recibos."""
        state = self._ensure_session()
        results: List[Tuple[ActionCandidate, ProviderAssessment, PolicyDecision, DecisionReceipt]] = []

        # Separar acciones batchables vs no batchables si hay múltiples
        # Para cada acción aplicamos el pipeline:
        for action in actions:
            # 1. Comprobar si es un intento de finalización
            completion_assessment: Optional[CompletionAssessment] = None
            if self.completion_verifier.is_finish_action(action):
                completion_assessment = self.completion_verifier.verify(state.goal, state, action)

            # 2. Evaluación semántica pura (JEV / Provider)
            assessments = self.provider.evaluate(state, [action])
            assessment = assessments[0] if assessments else ProviderAssessment(
                provider="unknown",
                available=False,
                confidence=0.0,
                failure_reason="No assessment returned",
            )

            # 3. Decisión operacional de política
            decision, receipt = self.policy_engine.evaluate_action(
                action=action,
                state=state.to_snapshot(),
                provider_assessment=assessment,
                available_evidence=state.evidence,
                forbidden_tools=state.forbidden_tools,
                completion_assessment=completion_assessment,
                session_id=state.session_id,
            )

            self.audit_receipts.append(receipt)
            results.append((action, assessment, decision, receipt))

        return results

    def decide(
        self,
        action: ActionCandidate,
        assessment: Optional[ProviderAssessment] = None,
    ) -> Tuple[PolicyDecision, DecisionReceipt]:
        """Toma la decisión operacional formal para una única acción."""
        state = self._ensure_session()

        completion_assessment: Optional[CompletionAssessment] = None
        if self.completion_verifier.is_finish_action(action):
            completion_assessment = self.completion_verifier.verify(state.goal, state, action)

        if assessment is None:
            assessments = self.provider.evaluate(state, [action])
            assessment = assessments[0] if assessments else ProviderAssessment(
                provider="unknown",
                available=False,
                confidence=0.0,
                failure_reason="No assessment returned",
            )

        decision, receipt = self.policy_engine.evaluate_action(
            action=action,
            state=state.to_snapshot(),
            provider_assessment=assessment,
            available_evidence=state.evidence,
            forbidden_tools=state.forbidden_tools,
            completion_assessment=completion_assessment,
            session_id=state.session_id,
        )
        self.audit_receipts.append(receipt)
        return decision, receipt

    def step(
        self,
        action: ActionCandidate,
        auto_checkpoint: bool = True,
    ) -> Tuple[PolicyDecision, Optional[ToolObservation]]:
        """Ejecuta un paso normativo completo de supervisión y ejecución:
        
        Proposal -> Evidence -> Risk -> JEV -> Policy -> Decision -> Execution -> Observation.
        """
        state = self._ensure_session()

        # 1. Evaluar decisión con la política
        decision, receipt = self.decide(action)

        # 2. Si la política DENEGÓ la ejecución (BLOCK, REPLAN, ABSTAIN)
        if decision.status != DecisionStatus.ALLOW:
            state.add_step(action=action, decision=decision, observation=None)
            return decision, None

        # 3. La acción está AUTORIZADA (ALLOW)
        tool_name = action.tool_call.tool_name if action.tool_call else None
        tool_args = action.tool_call.arguments if action.tool_call else {}

        # Checkpoint preventivo automático ante mutaciones relevantes
        if auto_checkpoint and tool_name:
            spec = self.policy_engine.registry.get_tool(tool_name)
            if spec and not spec.read_only:
                self.checkpoint_manager.create_checkpoint(
                    state,
                    reason=f"Auto-checkpoint previo a mutación por '{tool_name}'",
                )

        # 4. Ejecución física con el Executor garantizado
        observation = self.executor.execute(action, state, decision)

        # 5. Ingestión de evidencia y resolución de mutaciones
        if observation.success:
            if tool_name:
                # Ingestar evidencias automáticas derivadas de la observación (gestiona internamente invalidación de mutaciones)
                new_evidences = self.evidence_engine.ingest_from_observation(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    observation=observation.output,
                    step_id=f"step_{len(state.steps)}",
                )
                for ev in new_evidences:
                    state.add_evidence(ev)

        # 6. Registrar paso completado en el estado canónico
        state.add_step(action=action, decision=decision, observation=observation.output)

        return decision, observation

    def rollback(
        self,
        checkpoint_id: Optional[str] = None,
        culprit_tool: Optional[str] = None,
        reason: str = "Rollback formal por degradación de trayectoria",
    ) -> SessionState:
        """Restaura el estado al checkpoint indicado o al más reciente, prohibiendo transiciones fallidas."""
        state = self._ensure_session()
        target_id = checkpoint_id
        if not target_id:
            latest = self.checkpoint_manager.get_latest_checkpoint()
            if not latest:
                raise RuntimeError("No existen checkpoints disponibles para rollback.")
            target_id = latest.id

        restored_state = self.checkpoint_manager.rollback(
            checkpoint_id=target_id,
            current_state=state,
            culprit_tool=culprit_tool,
            reason=reason,
        )
        self.state = restored_state
        return self.state

    def get_receipts(self) -> List[DecisionReceipt]:
        """Devuelve todos los recibos de auditoría emitidos."""
        return list(self.audit_receipts)
