"""Entidades ontológicas de evidencia y asertos empíricos (Cadena: Observation -> Evidence -> Claim -> Action)."""

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class Claim(BaseModel):
    """Afirmación o aserto declarativo derivado de una evidencia empírica."""
    model_config = ConfigDict(frozen=True)

    id: str
    statement: str
    confidence: float = 1.0
    evidence_ids: List[str] = Field(default_factory=list)


class Evidence(BaseModel):
    """Pieza de evidencia observada en el entorno o suministrada por el usuario."""
    model_config = ConfigDict(frozen=True)

    id: str
    source_step_id: Optional[str] = None
    source_type: Literal["tool_observation", "user_input", "system", "external_source"] = "tool_observation"
    claim: str
    content_hash: str = Field(default="")
    confidence: float = 1.0
    claims: List[Claim] = Field(default_factory=list)

