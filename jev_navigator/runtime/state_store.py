"""Almacén de estado y sesiones para recuperación atómica (runtime/state_store.py)."""

from typing import Dict, List, Optional
from jev_navigator.domain.interfaces import CheckpointStore, StateStore
from jev_navigator.domain.models import Checkpoint
from jev_navigator.runtime.state import SessionState


class InMemoryStateStore(StateStore, CheckpointStore):
    """Implementación en memoria de almacén de estados y checkpoints de sesión."""

    def __init__(self):
        self._states: Dict[str, SessionState] = {}
        self._checkpoints: Dict[str, Checkpoint] = {}
        self._session_checkpoints: Dict[str, List[str]] = {}

    def save_state(self, state: SessionState) -> None:
        """Guarda o actualiza el estado de la sesión."""
        self._states[state.session_id] = state

    def load_state(self, session_id: str) -> Optional[SessionState]:
        """Recupera el estado de una sesión por su identificador."""
        return self._states.get(session_id)

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Almacena una instantánea atómica de checkpoint."""
        self._checkpoints[checkpoint.id] = checkpoint
        if checkpoint.session_id not in self._session_checkpoints:
            self._session_checkpoints[checkpoint.session_id] = []
        self._session_checkpoints[checkpoint.session_id].append(checkpoint.id)

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Obtiene un checkpoint por su ID."""
        return self._checkpoints.get(checkpoint_id)

    def get_latest_checkpoint(self, session_id: Optional[str] = None) -> Optional[Checkpoint]:
        """Obtiene el último checkpoint registrado para una sesión o globalmente."""
        if session_id:
            cids = self._session_checkpoints.get(session_id, [])
            if not cids:
                return None
            return self._checkpoints.get(cids[-1])
        if not self._checkpoints:
            return None
        last_id = list(self._checkpoints.keys())[-1]
        return self._checkpoints.get(last_id)

    def list_checkpoints(self, session_id: str) -> List[Checkpoint]:
        """Lista cronológicamente todos los checkpoints de una sesión."""
        cids = self._session_checkpoints.get(session_id, [])
        return [self._checkpoints[cid] for cid in cids if cid in self._checkpoints]

    def clear(self) -> None:
        """Limpia todos los estados y checkpoints."""
        self._states.clear()
        self._checkpoints.clear()
        self._session_checkpoints.clear()
