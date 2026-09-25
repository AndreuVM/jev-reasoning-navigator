"""Proveedor de razonamiento semántico basado en LAYA (System One Local & Hosted).

Implementa la arquitectura no-autorregresiva de LAYA con sus tres primitivas de decisión:
1. choice: Selección categórica y distribución de probabilidad (ALLOW, REPLAN, BLOCK, ABSTAIN).
2. score: Evaluación continua y posición ponderada de progreso hacia la meta (0.0 a 1.0).
3. noul: Probabilidades binarias calibradas (is_loop, is_grounded, is_novel).

Soporta backends:
- 'auto': Autodetección entre paquete local, endpoint alojado o simulación calibrada.
- 'local': Motor local (vía biblioteca laya / ONNX / simulación local calibrada).
- 'hosted': Servicio HTTP remoto o microservicio REST de LAYA.
- 'simulated': Motor determinista calibrado para pruebas y benchmarks reproducibles offline.
"""

from datetime import datetime
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from jev_navigator.domain.action import ActionCandidate
from jev_navigator.domain.assessment import ProviderAssessment
from jev_navigator.providers.base import BaseReasoningProvider
from jev_navigator.providers.context import ProviderContext, ProviderContextBuilder

logger = logging.getLogger("jev_navigator.providers.laya")


class LayaDecisionPrimitives(BaseModel):
    """Estructura de las tres primitivas fundamentales retornadas por LAYA."""
    model_config = ConfigDict(frozen=True)

    choice: Dict[str, Any] = Field(
        default_factory=lambda: {"label": "ALLOW", "probabilities": {"ALLOW": 1.0}, "confidence": 1.0}
    )
    score: float = 1.0
    noul: Dict[str, float] = Field(
        default_factory=lambda: {"is_loop": 0.0, "is_grounded": 1.0, "is_novel": 1.0}
    )


class LayaProvider(BaseReasoningProvider):
    """Adaptador de razonamiento semántico para LAYA con soporte para choice, score y noul."""

    def __init__(
        self,
        backend: str = "auto",
        model_name: str = "laya-v1-calibrated",
        endpoint_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        context_builder: Optional[ProviderContextBuilder] = None,
        max_context_tokens: int = 2048,
        timeout: float = 5.0,
        device: str = "cpu",
    ):
        self.requested_backend = backend.lower()
        self.model_name = model_name
        self.endpoint_url = endpoint_url or os.getenv("LAYA_ENDPOINT_URL")
        self.auth_token = auth_token or os.getenv("LAYA_AUTH_TOKEN")
        self.context_builder = context_builder or ProviderContextBuilder(default_max_tokens=max_context_tokens)
        self.max_context_tokens = max_context_tokens
        self.timeout = timeout
        self.device = device
        self._is_warmed_up = False

        self.backend = self._resolve_backend()

    def _resolve_backend(self) -> str:
        """Determina el backend efectivo a utilizar."""
        if self.requested_backend in ("hosted", "remote"):
            return "hosted"
        if self.requested_backend == "simulated":
            return "simulated"
        if self.requested_backend == "local":
            try:
                import laya  # type: ignore
                return "local"
            except ImportError:
                return "simulated"

        # Modo 'auto'
        if self.endpoint_url:
            return "hosted"
        try:
            import laya  # type: ignore
            return "local"
        except ImportError:
            return "simulated"

    def is_available(self) -> bool:
        """Comprueba si el proveedor LAYA está disponible para realizar inferencias."""
        if self.backend == "hosted":
            return bool(self.endpoint_url)
        return True

    def warmup(self) -> bool:
        """Realiza un pase de calentamiento para verificar latencia y disponibilidad."""
        start_t = time.perf_counter()
        try:
            # Consulta mínima de prueba
            dummy_ctx = ProviderContext(
                session_id="warmup_session",
                goal="Warmup check",
                history_window=[],
                active_evidence=[],
                candidate_action={"id": "warmup", "description": "ping"},
                formatted_prompt="GOAL: Warmup check\nCANDIDATE ACTION: ping",
            )
            _ = self._infer_primitives(dummy_ctx)
            self._is_warmed_up = True
            logger.info(f"LAYA warmup completado en {(time.perf_counter() - start_t) * 1000.0:.2f} ms ({self.backend})")
            return True
        except Exception as e:
            logger.warning(f"Fallo en warmup de LAYA ({self.backend}): {e}")
            return False

    def _infer_primitives_hosted(self, ctx: ProviderContext) -> LayaDecisionPrimitives:
        """Invoca el servicio HTTP remoto de LAYA."""
        if not self.endpoint_url:
            raise ValueError("endpoint_url no configurado para backend hosted de LAYA.")

        payload = ctx.to_laya_payload()
        payload["model"] = self.model_name
        req_data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "JEV-Reasoning-Navigator/0.3",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        req = urllib.request.Request(self.endpoint_url, data=req_data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            resp_code = resp.getcode()
            if resp_code != 200:
                raise RuntimeError(f"LAYA endpoint retornó status {resp_code}")
            raw_body = resp.read().decode("utf-8")
            data = json.loads(raw_body)

        choice_data = data.get("choice", {"label": "ALLOW", "probabilities": {"ALLOW": 1.0}, "confidence": 1.0})
        score_val = float(data.get("score", 1.0))
        noul_data = data.get("noul", {"is_loop": 0.0, "is_grounded": 1.0, "is_novel": 1.0})

        return LayaDecisionPrimitives(
            choice=choice_data,
            score=score_val,
            noul=noul_data,
        )

    def _infer_primitives_local_sdk(self, ctx: ProviderContext) -> LayaDecisionPrimitives:
        """Invoca el paquete local laya si está presente."""
        import laya  # type: ignore
        # La interfaz de Laya evalúa choice, score y noul
        model = getattr(laya, "load_model", lambda m: None)(self.model_name)
        prompt = ctx.formatted_prompt

        choice_res = model.choice(prompt, options=["ALLOW", "REPLAN", "BLOCK", "ABSTAIN"])
        score_res = model.score(prompt, scale=(0.0, 1.0))
        is_loop = model.noul(f"{prompt}\n¿La acción propuesta es un bucle o estancamiento repetitivo?")
        is_grounded = model.noul(f"{prompt}\n¿La acción propuesta está fundamentada en observaciones comprobadas?")

        return LayaDecisionPrimitives(
            choice={
                "label": choice_res.label,
                "probabilities": choice_res.probabilities,
                "confidence": choice_res.confidence,
            },
            score=float(score_res),
            noul={
                "is_loop": float(is_loop),
                "is_grounded": float(is_grounded),
                "is_novel": float(1.0 - is_loop),
            },
        )

    def _infer_primitives_calibrated(self, ctx: ProviderContext) -> LayaDecisionPrimitives:
        """Inferencia local simulada de alta fidelidad y calibración matemática."""
        cand = ctx.candidate_action
        desc = (cand.get("description") or "").lower()
        tool_name = (cand.get("tool_name") or "").lower()
        args = cand.get("arguments") or {}
        req_evidence = cand.get("requires_evidence") or []
        evidence_lower = [e.lower() for e in ctx.active_evidence]

        # 1. Comprobación de repetición o bucle frente a pasos previos
        recent_tools = [h.get("tool") for h in ctx.history_window if h.get("tool")]
        repetition_count = recent_tools.count(tool_name) if tool_name else 0

        is_loop = 0.05
        if repetition_count >= 3:
            is_loop = 0.88
        elif repetition_count >= 2:
            is_loop = 0.65

        if any(w in desc for w in ("reintentar", "mismo comando", "bucle", "repetir")):
            is_loop = max(is_loop, 0.85)

        # 2. Comprobación de grounding (fundamentación)
        is_grounded = 0.95
        if req_evidence:
            missing = [r for r in req_evidence if r.lower().strip() not in evidence_lower]
            if missing:
                is_grounded = 0.12

        # 3. Comprobación de peligrosidad / acciones destructivas
        is_destructive = any(
            dest in str(args).lower() or dest in desc
            for dest in ("rm -rf", "drop table", "truncate", "delete from", "format c:", "mkfs")
        )

        # 4. Cálculo de Score de progreso (0.0 a 1.0)
        if is_loop > 0.70:
            score = 0.10
        elif is_grounded < 0.30:
            score = 0.20
        elif is_destructive:
            score = 0.05
        else:
            score = 0.85

        # 5. Determinación de Choice y distribución de probabilidades calibrada
        if is_destructive:
            label = "BLOCK"
            probs = {"BLOCK": 0.92, "ALLOW": 0.02, "REPLAN": 0.04, "ABSTAIN": 0.02}
            confidence = 0.92
        elif is_loop >= 0.70 or is_grounded < 0.30:
            label = "REPLAN"
            probs = {"REPLAN": 0.86, "ALLOW": 0.06, "BLOCK": 0.03, "ABSTAIN": 0.05}
            confidence = 0.86
        elif any(w in desc for w in ("incierto", "desconocido", "duda", "ambiguo")):
            label = "ABSTAIN"
            probs = {"ABSTAIN": 0.40, "ALLOW": 0.30, "REPLAN": 0.20, "BLOCK": 0.10}
            confidence = 0.35  # Baja confianza para disparar escalado
        else:
            label = "ALLOW"
            probs = {"ALLOW": 0.90, "REPLAN": 0.05, "BLOCK": 0.02, "ABSTAIN": 0.03}
            confidence = 0.90

        return LayaDecisionPrimitives(
            choice={"label": label, "probabilities": probs, "confidence": confidence},
            score=score,
            noul={
                "is_loop": is_loop,
                "is_grounded": is_grounded,
                "is_novel": round(1.0 - is_loop, 2),
            },
        )

    def _infer_primitives(self, ctx: ProviderContext) -> LayaDecisionPrimitives:
        """Enruta la inferencia al backend seleccionado."""
        if self.backend == "hosted":
            return self._infer_primitives_hosted(ctx)
        elif self.backend == "local":
            return self._infer_primitives_local_sdk(ctx)
        else:
            return self._infer_primitives_calibrated(ctx)

    def _get_resident_memory_mb(self) -> float:
        """Estima la memoria residente utilizada en megabytes."""
        try:
            import psutil  # type: ignore
            process = psutil.Process(os.getpid())
            return round(process.memory_info().rss / (1024 * 1024), 2)
        except Exception:
            return 0.0

    def evaluate_action(self, state: Any, action: ActionCandidate) -> ProviderAssessment:
        """Evalúa una acción candidata mediante LAYA emitiendo un ProviderAssessment estructurado."""
        start_t = time.perf_counter()

        # Construir contexto normalizado con ProviderContextBuilder
        ctx = self.context_builder.build(state, action, max_tokens=self.max_context_tokens)

        try:
            primitives = self._infer_primitives(ctx)
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0

            choice_data = primitives.choice
            score_val = primitives.score
            noul_data = primitives.noul

            loop_prob = noul_data.get("is_loop", 0.0)
            grounded_prob = noul_data.get("is_grounded", 1.0)
            progress_prob = score_val
            novelty_prob = noul_data.get("is_novel", 1.0 - loop_prob)

            # JEV analítico: producto de progreso, no-bucle y fundamentación
            analytical_jev = progress_prob * (1.0 - loop_prob) * grounded_prob

            reason_codes: List[str] = [f"LAYA_CHOICE_{choice_data.get('label', 'ALLOW')}"]
            if loop_prob >= 0.70:
                reason_codes.append("LAYA_LOOP_PREVENTED")
            if grounded_prob < 0.30:
                reason_codes.append("LAYA_UNGROUNDED_EVIDENCE")
            if score_val >= 0.75:
                reason_codes.append("LAYA_HIGH_PROGRESS")

            metadata = {
                "provider": "laya",
                "backend": self.backend,
                "model_name": self.model_name,
                "device": self.device,
                "latency_ms": round(elapsed_ms, 2),
                "context_tokens": ctx.token_estimate,
                "truncated": ctx.truncated,
                "choice": choice_data,
                "score": score_val,
                "noul": noul_data,
                "memory_mb": self._get_resident_memory_mb(),
                "timestamp": datetime.utcnow().isoformat(),
            }

            return ProviderAssessment(
                provider="laya",
                model=self.model_name,
                available=True,
                confidence=float(choice_data.get("confidence", 0.90)),
                loop_probability=loop_prob,
                grounded_probability=grounded_prob,
                progress_probability=progress_prob,
                novelty_probability=novelty_prob,
                analytical_jev=round(analytical_jev, 4),
                reason_codes=reason_codes,
                metadata=metadata,
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            logger.error(f"Fallo durante la evaluación en LayaProvider ({self.backend}): {e}")

            metadata = {
                "provider": "laya",
                "backend": self.backend,
                "model_name": self.model_name,
                "latency_ms": round(elapsed_ms, 2),
                "error": str(e),
                "context_tokens": ctx.token_estimate,
                "truncated": ctx.truncated,
            }

            return ProviderAssessment(
                provider="laya",
                model=self.model_name,
                available=False,
                confidence=0.0,
                failure_reason=f"LAYA failure ({self.backend}): {str(e)}",
                reason_codes=["LAYA_PROVIDER_UNAVAILABLE"],
                metadata=metadata,
            )

    def evaluate(
        self,
        state: Any,
        actions: List[ActionCandidate],
    ) -> List[ProviderAssessment]:
        """Evalúa un lote de acciones candidatas de forma secuencial preservando consistencia."""
        return [self.evaluate_action(state, action) for action in actions]
