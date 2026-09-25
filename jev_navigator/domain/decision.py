"""Decisiones formales de política y recibos inmutables de auditoría (Cuadro 1)."""

from datetime import datetime
from enum import Enum
import hashlib
import hmac
import json
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from jev_navigator.domain.assessment import ProviderAssessment, RiskAssessment


class DecisionStatus(str, Enum):
    """Estados canónicos de decisión formal del supervisor."""
    ALLOW = "allow"      # Acción autorizada por la política actual
    BLOCK = "block"      # Denegación formal o imperativo de seguridad
    REPLAN = "replan"    # Trayectoria inadecuada; replanificación obligatoria
    ABSTAIN = "abstain"  # Abstención preventiva por incertidumbre o indisponibilidad


class PolicyDecision(BaseModel):
    """Decisión final consolidada por la PolicyEngine."""
    model_config = ConfigDict(frozen=True)

    status: DecisionStatus
    reason_codes: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    target_checkpoint: Optional[str] = None
    forbidden_tools: List[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    provider: Optional[ProviderAssessment] = None
    grounding: Optional[float] = None
    risk: Optional[RiskAssessment] = None


class DecisionReceipt(BaseModel):
    """Recibo criptográficamente auditable de una decisión de supervisión (Contrato Cuadro 1)."""
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    # 1. Contexto
    decision_id: str
    session_id: str
    action_id: str
    state_hash: str
    action_hash: str
    nonce: str = Field(default_factory=lambda: uuid.uuid4().hex)
    signature: Optional[str] = None
    expires_at: Optional[datetime] = None

    # 2. Proveedor
    provider_available: bool = True
    model_identifier: Optional[str] = None
    latency_ms: float = 0.0

    # 3. Razonamiento
    progress_score: Optional[float] = None
    grounded_score: Optional[float] = None
    loop_type: Optional[str] = None
    novelty_score: Optional[float] = None

    # 4. Riesgo
    risk_level: Optional[str] = None
    risk_reasons: List[str] = Field(default_factory=list)
    destructive_potential: bool = False

    # 5. Política
    decision_status: DecisionStatus = DecisionStatus.ALLOW
    reason_codes: List[str] = Field(default_factory=list)

    # 6. Ejecución
    is_executed: bool = False
    observation_id: Optional[str] = None
    execution_timestamp: Optional[datetime] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def __init__(self, **data: Any):
        # Compatibilidad: si se pasa 'status' o 'decision' en lugar de 'decision_status'
        if "status" in data and "decision_status" not in data:
            data["decision_status"] = data.pop("status")
        elif "decision" in data and "decision_status" not in data:
            data["decision_status"] = data.pop("decision")
        super().__init__(**data)

    @property
    def decision(self) -> DecisionStatus:
        """Alias para compatibilidad hacia atrás con v0.2 temprana."""
        return self.decision_status

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Determina si el capability receipt ha superado su ventana temporal de validez."""
        if self.expires_at is None:
            return False
        current_time = now or datetime.utcnow()
        return current_time > self.expires_at


def compute_receipt_signature(
    secret_key: str,
    decision_id: str,
    session_id: str,
    action_hash: str,
    state_hash: str,
    nonce: str,
    decision_status: DecisionStatus,
    expires_at: Optional[datetime] = None,
) -> str:
    """Calcula un HMAC-SHA256 para autenticar criptográficamente la emisión del capability por PolicyEngine."""
    exp_str = expires_at.isoformat() if expires_at else "none"
    status_val = decision_status.value if isinstance(decision_status, DecisionStatus) else str(decision_status)
    payload = f"{decision_id}:{session_id}:{action_hash}:{state_hash}:{nonce}:{status_val}:{exp_str}"
    return hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_receipt(receipt: DecisionReceipt, secret_key: str) -> DecisionReceipt:
    """Firma un DecisionReceipt con la clave secreta y devuelve una instancia actualizada con su firma HMAC."""
    sig = compute_receipt_signature(
        secret_key=secret_key,
        decision_id=receipt.decision_id,
        session_id=receipt.session_id,
        action_hash=receipt.action_hash,
        state_hash=receipt.state_hash,
        nonce=receipt.nonce,
        decision_status=receipt.decision_status,
        expires_at=receipt.expires_at,
    )
    return receipt.model_copy(update={"signature": sig})


def verify_receipt_signature(secret_key: str, receipt: DecisionReceipt) -> bool:
    """Verifica de forma inmune a ataques de temporización si el recibo fue firmado con la clave del runtime."""
    if not receipt.signature:
        return False
    expected = compute_receipt_signature(
        secret_key=secret_key,
        decision_id=receipt.decision_id,
        session_id=receipt.session_id,
        action_hash=receipt.action_hash,
        state_hash=receipt.state_hash,
        nonce=receipt.nonce,
        decision_status=receipt.decision_status,
        expires_at=receipt.expires_at,
    )
    return hmac.compare_digest(receipt.signature, expected)


def compute_state_hash(state_dict: Any) -> str:
    """Calcula un hash SHA-256 determinista para el estado canónico."""
    if hasattr(state_dict, "to_snapshot"):
        state_dict = state_dict.to_snapshot()
    elif hasattr(state_dict, "model_dump"):
        state_dict = state_dict.model_dump()
    elif not isinstance(state_dict, dict):
        try:
            state_dict = dict(state_dict)
        except Exception:
            state_dict = {"repr": str(state_dict)}
    canonical = json.dumps(state_dict, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

