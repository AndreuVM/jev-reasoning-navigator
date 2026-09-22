"""Configuraciones y parámetros del motor JEV-Reasoning-Navigator."""

import os
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Cargar variables de entorno desde .env local o directorio home
load_dotenv()


class JEVConfig(BaseModel):
    """Configuración del supervisor cognitivo basado en TypeSafe AI."""

    # Integración con TypeSafe AI API (Modelo Jev)
    typesafe_api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("TYPESAFE_API_KEY"),
        description="Clave API de TypeSafe AI para invocar el modelo Jev"
    )
    use_typesafe_api: bool = Field(
        default_factory=lambda: bool(os.getenv("TYPESAFE_API_KEY")),
        description="Si es True y hay API key, utiliza la API de TypeSafe AI para evaluar pasos"
    )
    typesafe_model: str = Field(
        default="jev-latest",
        description="Identificador del modelo System One de TypeSafe AI (ej. jev-latest, jev-preview)"
    )

    # Umbrales de decisión e intervención
    critical_jev_threshold: float = Field(
        default=0.0,
        description="Umbral crítico de JEV por debajo del cual se considera que la rama es degenerativa"
    )
    max_history_steps: int = Field(
        default=50,
        description="Máximo número de pasos históricos a retener para contexto de evaluación"
    )

    # Configuración de Supervisión por Bloques (Chunking) y Ahorro de Cuota API
    evaluation_chunk_size: int = Field(
        default=3,
        description="Tamaño máximo de pasos de razonamiento agrupados por llamada a TypeSafe AI"
    )
    enable_chunk_evaluation: bool = Field(
        default=True,
        description="Agrupar evaluaciones en TypeSafe AI para ahorrar peticiones RPM/RPD"
    )
    hallucination_detection: bool = Field(
        default=True,
        description="Activar validación de fundamentación empírica (groundedness) para evitar alucinaciones"
    )
    call_llm_only_on_intervention_or_chunk_end: bool = Field(
        default=True,
        description="Invocar al LLM (Gemini) solo en caso de intervención JEV, error o fin de bloque"
    )


# Instancia global por defecto
default_config = JEVConfig()

