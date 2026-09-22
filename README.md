# JEV-Reasoning-Navigator

**Motor de Navegación Cognitiva y Prevención de Alucinaciones para LLMs basado en TypeSafe AI (System One)**

`JEV-Reasoning-Navigator` es un árbitro cognitivo externo y middleware desacoplado diseñado para supervisar en tiempo real los flujos de razonamiento (*Chain-of-Thought*, *Tree-of-Thought* y ejecuciones de agentes autónomos con llamadas a herramientas). Impulsado por el motor probabilístico **System One de TypeSafe AI**, evalúa la viabilidad y fundamentación (*groundedness*) de los pasos propuestos, detecta patrones degenerativos (bucles de acción, fijación semántica, alucinaciones) y emite directivas estratégicas de intervención, poda y *backtracking*.

---

## 1. Supervisión Cognitiva con TypeSafe AI (System One)

En lugar de depender de heurísticas matemáticas frágiles o distancias vectoriales locales de coseno, `JEV-Reasoning-Navigator` utiliza **TypeSafe AI (`typesafe-sdk`)** como motor único y autoritativo de decisión cognitiva:

* **Evaluación Tipada y Probabilística:** TypeSafe System One evalúa el objetivo, el historial y las acciones propuestas emitiendo decisiones estructuradas (`Noul`, `Choice`, `Score`) con probabilidades calibradas en una única pasada de inferencia.
* **Prevención de Alucinaciones y Desvíos:** Detecta de forma semántica cuándo el modelo genera acciones inventadas, no fundamentadas en observaciones previas (*ungrounded steps*), o reintentos estériles de herramientas fallidas.
* **Supervisión por Lotes (*Chunking*):** Agrupa secuencias de 3 a 4 pasos candidatos en una única evaluación cognitiva. Esto minimiza el consumo de cuota (evitando saturar el RPM y RPD de la API del LLM) y permite al agente ejecutar de forma autónoma bloques seguros sin llamadas intermedias innecesarias.

---

## 2. Diagnóstico de Trayectorias y Taxonomía de Errores

El motor clasifica en tiempo real el estado de la trayectoria del agente mediante diagnóstico continuo:

| Categoría de Estado | Diagnóstico | Acción de JEV |
| :--- | :--- | :--- |
| **SAFE / ON_TRACK** | Progreso medible hacia el objetivo con premisas consistentes. | Permite la ejecución del paso o del bloque completo. |
| **1-HOP TOOL REPEAT** | Reejecución inmediata de una herramienta idéntica con mismos argumentos tras fallo. | Intervención Nivel 1 o Nivel 2: Bloqueo de acción y aviso al agente. |
| **N-HOP CYCLE** | Ciclos periódicos de razonamiento o alternancia circular de acciones. | Intervención Nivel 2: Poda de rama y *backtracking* al último nodo válido en el DAG. |
| **SEMANTIC FIXATION** | Obsesión con una premisa errónea sin alterar la estrategia. | Intervención Nivel 3: Cambio radical de abstracción y cuestionamiento de hipótesis. |
| **UNGROUNDED / HALLUCINATION** | Inferencia o invocación de herramientas basada en datos inexistentes. | Intervención Nivel 1 / 2: Prohibición de la acción y exigencia de verificación de hechos. |
| **DEAD END** | Agotamiento del enfoque actual sin posibilidad de avance. | Intervención Nivel 2: Retroceso guiado a la mejor bifurcación alternativa. |

---

## 3. Grafo de Estados DAG (`StateGraph`)

La trayectoria de razonamiento se modela como un grafo acíclico dirigido (DAG) respaldado por **NetworkX**:
- Registra cada paso, pensamiento, herramienta y resultado de forma inmutable.
- Permite ramificación (*branching*) y poda (*pruning*) cuando una rama degenera.
- Proporciona retroceso instantáneo (*backtracking*) al nodo previo con mejor evaluación cognitiva cuando una intervención de Nivel 2 lo requiere.

---

## 4. Políticas de Intervención Multinivel

Cuando TypeSafe AI diagnostica un bucle, alucinación o degradación, `InterventionPolicy` genera una directiva correctiva inyectable:

* **Nivel 1 (Meta-Feedback):** Alerta al modelo sobre el intento infructuoso o la inconsistencia detectada, exigiéndole explicar en 1 frase por qué la premisa previa falló antes de continuar.
* **Nivel 2 (Poda Forzada / Backtracking):** Poda la rama degenerativa en el grafo DAG, fuerza al agente a retroceder al mejor nodo previo ($S_k$) y prohíbe expresamente la herramienta causante del bucle.
* **Nivel 3 (Cambio de Abstracción / Abogado del Diablo):** Aplica una parada táctica obligatoria y exige formular 3 razones por las cuales la hipótesis fundamental es falsa, obligando a replantear la estrategia global.

---

## 5. Estructura del Proyecto

```
jev-reasoning-navigator/
├── jev_navigator/
│   ├── config.py                 # Umbrales cognitivos, chunking y configuración de TypeSafe
│   ├── cli.py                    # CLI interactivo con Rich (árbol, tablas y diagnóstico)
│   ├── live_agent.py             # Agente interactivo con LLM (Gemini) supervisado por JEV
│   ├── core/
│   │   ├── state_graph.py        # Grafo de estados DAG en NetworkX (historial y poda)
│   │   ├── typesafe_client.py    # Cliente TypeSafe AI System One (evaluación y diagnóstico)
│   │   ├── jev_engine.py         # Fachada de evaluación cognitiva JEV sobre TypeSafe AI
│   │   └── intervention_policy.py# Generador de directivas de rescate multinivel
│   ├── models/
│   │   ├── schema.py             # Modelos Pydantic v2 (Step, JEVScore, ChunkEvaluation, etc.)
│   │   └── trace.py              # Parsers de trazas (ReAct, OpenAI, Anthropic, JSON)
│   └── interceptor/
│       ├── mcp_bridge.py         # Servidor MCP (Model Context Protocol) para clientes AI
│       └── proxy_middleware.py   # Middleware interceptor en tiempo real con soporte de Chunks
├── data/
│   └── loop_traces/              # Banco de trazas sintéticas de prueba
├── tests/                        # Suite completa de tests unitarios y de integración
├── pyproject.toml
└── README.md
```

---

## 6. Configuración de Credenciales

Crea un archivo `.env` en la raíz del proyecto con tu clave de API de TypeSafe AI (y de Gemini para `jev-live`):
```env
TYPESAFE_API_KEY=tu_typesafe_api_key
GEMINI_API_KEY=tu_gemini_api_key
```

---

## 7. Instalación y Uso

### Instalación
Con `uv`:
```bash
uv sync
```

### Ejecutar Tests
```bash
uv run pytest -v
```

### Modo CLI: Diagnóstico y Visualización de Trazas (`jev-nav analyze`)
Genera un diagnóstico visual en consola con árbol cronológico, badges de estado, tabla analítica y panel de intervención:

```bash
uv run jev-nav analyze data/loop_traces/tool_loop.json
```

### Modo CLI: Simulación Paso a Paso (`jev-nav simulate`)
Simula la ejecución secuencial interceptando el razonamiento en el momento exacto en que se desvía o degenera:

```bash
uv run jev-nav simulate data/loop_traces/tool_loop.json
```

### Modo CLI: Agente Autónomo Interactivo (`jev-live`)
Ejecuta un agente interactivo que solicita el objetivo al usuario y resuelve tareas paso a paso, supervisado en cada bloque por TypeSafe AI para evitar alucinaciones:

```bash
uv run jev-live
```

---

## 8. Integración en Agentes LLM

### A. Como Servidor MCP (Model Context Protocol)
Añade `jev-navigator` a tu cliente MCP (Claude Desktop, Cursor, Antigravity):

```json
{
  "mcpServers": {
    "jev-navigator": {
      "command": "uv",
      "args": ["run", "python", "-m", "jev_navigator.interceptor.mcp_bridge"],
      "cwd": "C:/ruta/al/proyecto/jev-reasoning-navigator"
    }
  }
}
```

**Herramientas MCP disponibles:**
- `jev_evaluate_next_step(goal, history, proposed_step)`: Evalúa si el siguiente paso es seguro o si debe inyectarse una directiva de rescate.
- `jev_evaluate_step_chunk(goal, history, proposed_steps)`: Evalúa en lote un bloque agrupado de pasos candidatos, reduciendo llamadas de red y previniendo alucinaciones.
- `jev_diagnose_trace(trace_data)`: Diagnostica una traza completa de razonamiento.

### B. En Código Python mediante `JEVProxyMiddleware` (Modo Bloques / Chunking)
```python
from jev_navigator.interceptor.proxy_middleware import JEVProxyMiddleware

middleware = JEVProxyMiddleware(goal="Solucionar bug de compilación")

# Supervisar un bloque agrupado de pasos (hasta 3-4 pasos) en una sola llamada a TypeSafe:
proposed_chunk = [
    {"tool_name": "read_file", "tool_args": {"path": "src/main.rs"}, "thought_rationale": "Leer función principal"},
    {"tool_name": "cargo", "tool_args": {"subcmd": "check"}, "thought_rationale": "Verificar compilación"},
]

chunk_result = middleware.intercept_step_chunk(proposed_chunk)

if chunk_result.all_safe:
    # Ejecutar de forma autónoma secuencialmente SIN volver a consultar al LLM tras cada paso
    for step in proposed_chunk:
        obs = execute_tool(step["tool_name"], step["tool_args"])
        middleware.record_observation(obs)
else:
    # JEV bloqueó el paso infractor (alucinación o bucle) antes de su ejecución:
    print(f"Alerta JEV: {chunk_result.explanation}")
    # Inyectar la directiva en el contexto del LLM para que rectifique
    messages.append({"role": "system", "content": chunk_result.directive.context_injection})
```

---

## 9. Requisitos No Funcionales (RNF) Verificados

* **RNF-01 (Eficiencia de Cuota & Token Economy):** Agrupamiento de pasos en *chunks* cognitivos para minimizar peticiones HTTP y prevenir límites de RPM/RPD.
* **RNF-02 (Agnóstico a Proveedor):** Supervisa cualquier LLM generador (OpenAI, Anthropic Claude, Google Gemini, Ollama/OpenSource).
* **RNF-03 (Arquitectura Limpia & Cero Modelos Pesados):** Eliminación de dependencias de embeddings locales pesados (`fastembed`), garantizando un inicio instantáneo y mínimo consumo de memoria.
