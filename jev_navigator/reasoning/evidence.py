"""Motor de Evidencia (EvidenceEngine) para JEV Reasoning Navigator v0.2.

Gestiona el almacén de evidencia empírica, evalúa precondiciones declaradas (requires_evidence)
e invalida evidencias obsoletas cuando ocurren mutaciones de estado.
"""

import hashlib
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
from jev_navigator.domain.interfaces import EvidenceProvider
from jev_navigator.domain.models import ActionCandidate, Evidence


class EvidenceEngine(EvidenceProvider):
    """Almacena, indexa, verifica e invalida evidencia empírica para groundedness formal."""

    def __init__(self):
        # Mapeo de claim_key normalizado -> Evidence
        self._evidence_pool: Dict[str, Evidence] = {}
        # Historial de evidencias invalidadas por mutaciones de estado
        self.invalidation_history: List[Dict[str, Any]] = []

    def ingest(
        self,
        claim: str,
        source_type: str = "tool_observation",
        source_step_id: Optional[str] = None,
        confidence: float = 1.0,
        content: str = "",
    ) -> Evidence:
        """Registra una nueva pieza de evidencia empírica validada."""
        normalized_claim = claim.strip()
        key = normalized_claim.lower()

        content_hash = (
            hashlib.sha256(content.encode("utf-8")).hexdigest()
            if content
            else hashlib.sha256(normalized_claim.encode("utf-8")).hexdigest()
        )

        evidence = Evidence(
            id=f"ev_{uuid.uuid4().hex[:8]}",
            source_step_id=source_step_id,
            source_type=source_type,  # type: ignore
            claim=normalized_claim,
            content_hash=content_hash,
            confidence=confidence,
        )
        self._evidence_pool[key] = evidence
        return evidence

    def ingest_from_observation(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        observation: str,
        step_id: Optional[str] = None,
    ) -> List[Evidence]:
        """Extrae e ingesta evidencias automáticas a partir de la ejecución de una herramienta."""
        added: List[Evidence] = []
        is_error = "error" in observation.lower() or "no encontrado" in observation.lower() or "no existe" in observation.lower()

        if tool_name in ("read_file", "view_file") and not is_error:
            path = str(tool_args.get("path") or "").strip()
            if path:
                ev1 = self.ingest(
                    claim=f"file_exists:{path}",
                    source_step_id=step_id,
                    content=observation,
                )
                ev2 = self.ingest(
                    claim=f"file_read:{path}",
                    source_step_id=step_id,
                    content=observation,
                )
                added.extend([ev1, ev2])

        elif tool_name == "edit_file" and not is_error:
            path = str(tool_args.get("path") or "").strip()
            if path:
                # La edición muta el archivo: invalidar lecturas previas
                self.invalidate_resource(path, reason=f"Archivo '{path}' mutado por edit_file")
                ev = self.ingest(
                    claim=f"file_modified:{path}",
                    source_step_id=step_id,
                    content=observation,
                )
                added.append(ev)

        elif tool_name == "delete_file" and not is_error:
            path = str(tool_args.get("path") or "").strip()
            if path:
                # El borrado invalida que el archivo exista
                self.invalidate_resource(path, reason=f"Archivo '{path}' eliminado por delete_file")
                ev = self.ingest(
                    claim=f"file_deleted:{path}",
                    source_step_id=step_id,
                    content=observation,
                )
                added.append(ev)

        return added

    def has_evidence(self, claim: str) -> bool:
        """Verifica si existe evidencia activa para un claim específico."""
        return claim.strip().lower() in self._evidence_pool

    def get_evidence(self, claim: str) -> Optional[Evidence]:
        """Obtiene la evidencia para un claim si existe."""
        return self._evidence_pool.get(claim.strip().lower())

    def check_requirements(self, required_claims: List[str]) -> Tuple[bool, List[str]]:
        """Verifica si se cumplen todas las precondiciones requeridas por una acción."""
        missing = [
            req for req in required_claims
            if req.strip().lower() not in self._evidence_pool
        ]
        return len(missing) == 0, missing

    def assess(
        self,
        state: Any,
        action: ActionCandidate,
    ) -> List[Evidence]:
        """Implementación de EvidenceProvider protocol: recupera evidencias asociadas a la acción."""
        matches: List[Evidence] = []
        for req in action.requires_evidence:
            ev = self._evidence_pool.get(req.strip().lower())
            if ev:
                matches.append(ev)
        return matches

    def invalidate_resource(self, resource_path: str, reason: str = "Recurso mutado") -> List[str]:
        """Invalida evidencias previas asociadas a un recurso cuando este es modificado o eliminado."""
        norm_path = resource_path.strip().lower()
        keys_to_remove = [
            k for k in self._evidence_pool.keys()
            if norm_path in k
        ]

        invalidated_ids: List[str] = []
        for k in keys_to_remove:
            ev = self._evidence_pool.pop(k)
            invalidated_ids.append(ev.id)
            self.invalidation_history.append({
                "timestamp": time.time(),
                "evidence_id": ev.id,
                "claim": ev.claim,
                "reason": reason,
            })

        return invalidated_ids

    def get_all_active_evidence(self) -> List[Evidence]:
        """Devuelve la lista de todas las evidencias activas en el pool."""
        return list(self._evidence_pool.values())

    def clear(self) -> None:
        """Limpia el almacén de evidencias."""
        self._evidence_pool.clear()
        self.invalidation_history.clear()
