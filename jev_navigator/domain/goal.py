"""Entidad inmutable Goal para la especificación formal de objetivos del agente."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class Goal(BaseModel):
    """Objetivo formal del agente con criterios de éxito verificables."""
    model_config = ConfigDict(frozen=True)

    objective: str
    success_criteria: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    forbidden_outcomes: List[str] = Field(default_factory=list)
    budget: Optional[float] = None
    deadline: Optional[datetime] = None
