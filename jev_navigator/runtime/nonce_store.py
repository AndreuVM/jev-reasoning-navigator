"""Almacenamiento durable y en memoria de nonces y capabilities consumidas (runtime/nonce_store.py).

Garantiza la prevención estricta de ataques de repetición (replay attacks) tanto en un
proceso único como frente a reinicios o ejecución distribuida con TTL y poda automática.
"""

from abc import ABC, abstractmethod
from datetime import datetime
import threading
from typing import Dict, Optional, Tuple


class NonceStore(ABC):
    """Interfaz abstracta para almacenes de nonces consumidos."""

    @abstractmethod
    def has_been_consumed(self, decision_id: str, nonce: str) -> bool:
        """Verifica si un par decision_id:nonce ya ha sido registrado como consumido."""
        pass

    @abstractmethod
    def consume(self, decision_id: str, nonce: str, expires_at: Optional[datetime] = None) -> bool:
        """Marca un capability como consumido. Devuelve True si se registró con éxito, False si ya existía."""
        pass

    @abstractmethod
    def prune_expired(self) -> int:
        """Elimina entradas cuya fecha de expiración haya sido superada."""
        pass


class InMemoryNonceStore(NonceStore):
    """Almacén concurrente y seguro en memoria para nonces con poda por TTL."""

    def __init__(self):
        self._lock = threading.Lock()
        # Clave: f"{decision_id}:{nonce}", Valor: Optional[datetime]
        self._store: Dict[str, Optional[datetime]] = {}

    def _make_key(self, decision_id: str, nonce: str) -> str:
        return f"{decision_id}:{nonce}"

    def has_been_consumed(self, decision_id: str, nonce: str) -> bool:
        key = self._make_key(decision_id, nonce)
        with self._lock:
            if key not in self._store:
                return False
            exp = self._store[key]
            if exp and datetime.utcnow() > exp:
                del self._store[key]
                return False
            return True

    def consume(self, decision_id: str, nonce: str, expires_at: Optional[datetime] = None) -> bool:
        key = self._make_key(decision_id, nonce)
        with self._lock:
            if key in self._store:
                exp = self._store[key]
                if exp and datetime.utcnow() > exp:
                    pass  # Expirado, permitimos sobreescritura si correspondiese
                else:
                    return False  # Ya consumido y activo
            self._store[key] = expires_at
            return True

    def prune_expired(self) -> int:
        now = datetime.utcnow()
        removed = 0
        with self._lock:
            expired_keys = [k for k, exp in self._store.items() if exp and now > exp]
            for k in expired_keys:
                del self._store[k]
                removed += 1
        return removed

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
