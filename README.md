# JEV Reasoning Navigator v0.2.0

**Runtime de Seguridad, Gobernanza Cognitiva y Supervisión Formal para Agentes Autónomos de IA**

[![Tests](https://img.shields.io/badge/tests-113%20passed-brightgreen.svg)]()
[![Version](https://img.shields.io/badge/version-v0.2.0-blue.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![TypeSafe AI](https://img.shields.io/badge/engine-TypeSafe%20System%20One-purple.svg)]()

`JEV Reasoning Navigator` es un middleware de supervisión formal y runtime de seguridad desacoplado para agentes autónomos basados en LLM (*ReAct*, *Tool-use*, *Tree-of-Thought*). 

Evolucionado en la **v0.2.0** a partir de una auditoría técnica externa, el sistema trasciende los clasificadores heurísticos de bucles para establecer una separación formal de responsabilidades:
$$\text{Semantic Judgment (JEV)} \neq \text{Operational Policy (PolicyEngine)} \neq \text{Physical Execution (SecureExecutor)}$$

---

## 1. Axiomas y Principios Arquitectónicos de v0.2

1. **Juicio Semántico $\neq$ Política Operacional:**
   Una acción puede tener una probabilidad semántica de éxito elevada ($JEV = 0.95$) y ser al mismo tiempo operacionalmente inadmisible ($Risk = \text{CRITICAL}$, ej. `rm -rf /` o un archivo sensible `.env`). JEV emite juicio probabilístico; la `PolicyEngine` emite la decisión operativa (`ALLOW`, `BLOCK`, `REPLAN`, `ABSTAIN`).
2. **Enforcement Físico Real (Defensa contra Prompt Injection):**
   Las instrucciones textuales inyectadas en prompts (*"Por favor no uses delete_file"*) no constituyen seguridad. `SecureExecutor` actúa como una barrera física infranqueable a nivel de runtime: si la decisión no es `ALLOW` o la herramienta está prohibida, aborta inmediatamente levantando `PolicyViolation` antes de tocar el sistema operativo.
3. **La Indisponibilidad no Equivale a Neutralidad (Fail-Safe Estricto):**
   Si la red falla o el proveedor de inferencia semántica se cae, el sistema no asume un score neutro permisivo: aplica `FailSafePolicy` emitiendo `ABSTAIN` para acciones de bajo riesgo o `BLOCK` inmediato para acciones destructivas ($FalseAllowRate = 0.0\%$).
4. **Erradicación de Alucinaciones en Herramientas de Observación:**
   Invocaciones como `read_file("archivo_inventado.py")` parten de premisas 100% alucinadas. `EvidenceEngine` valida que existan observaciones previas antes de permitir acciones dependientes y descalifica evidencias obsoletas cuando ocurren mutaciones (*stale state defense*).
5. **Anti-Premature Finish:**
   `CompletionVerifier` impide que el agente declare victoria prematura (`finish => highJEV`) sin antes validar formalmente que todos los `Goal.success_criteria` estén respaldados por evidencias empíricas comprobadas.
6. **Backtracking Formal y Recuperación de Estado:**
   `CheckpointManager` captura snapshots canónicos SHA-256 de `SessionState`. Ante degradación o bucles, restaura el estado seguro, invalida los pasos descendientes y bloquea físicamente la herramienta o transición culpable.

---

## 2. Flujo de Ejecución Normativo v0.2

$$\text{Proposal} \to \text{Evidence} \to \text{Risk} \to \text{JEV Provider} \to \text{Policy} \to \text{Decision} \to \text{Execution} \to \text{Observation}$$

```
                +---------------------------------------+
                |           Agente Autónomo             |
                +---------------------------------------+
                                   | Propone candidatos
                                   v
+-----------------------------------------------------------------------+
|                 JEV Reasoning Navigator (v0.2 Runtime)                 |
|                                                                       |
|  1. EvidenceEngine        -> Verifica precondiciones empíricas        |
|  2. RiskEngine            -> Análisis contextual de comandos y rutas  |
|  3. TypeSafe / Replay     -> Inferencia semántica (Loop, Progress)    |
|  4. CompletionVerifier    -> Valida criterios de éxito frente a finish|
|  5. PolicyEngine          -> Matriz formal (ALLOW / BLOCK / REPLAN)   |
|  6. CheckpointManager     -> Captura snapshot preventivo si muta      |
|  7. SecureExecutor        -> Aplica veto físico o ejecuta en sandbox  |
|  8. DecisionReceipt       -> Emisión de recibo criptográfico SHA-256   |
+-----------------------------------------------------------------------+
                                   | Observación
                                   v
                        +----------------------+
                        |   Sistema / Estado   |
                        +----------------------+
```

---

## 3. Estudio de Ablaciones y Comparativa de Seguridad

Los benchmarks reproducibles con escenarios normativos de ground truth demuestran la necesidad crítica de cada capa:

### 🔬 Estudio de Ablaciones (5 Capas Arquitectónicas):
| Configuración | Exactitud (Accuracy) | F1-Score | False Allow Rate (Crítico) | Destructive False Allows | Diagnóstico |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **1. Policy Only (Sin JEV)** | 50.0% | 0.531 | 55.6% | 1 | Incapaz de detectar bucles semánticos o estancamiento. |
| **2. JEV (Sin Evidence Engine)** | 70.0% | 0.769 | 33.3% | 1 | Autoriza acciones basadas en premisas alucinadas. |
| **3. JEV + Evidence (Sin Risk Engine)** | 50.0% | 0.638 | 44.4% | 2 | Permite comandos destructivos de shell (`rm -rf`). |
| **4. JEV + Evidence + Risk (Fallback v0.1)** | 50.0% | 0.546 | 44.4% | 1 | Fallo de proveedor autoriza acciones destructivas. |
| **5. Full v0.2 Architecture** | **100.0%** | **1.000** | **0.0%** | **0** | **Enforcement físico total y cero brechas de seguridad.** |

### 🛡️ Comparativa Directa: v0.1 vs v0.2
| Métrica | v0.1 (Heurístico / Fallback Permisivo) | v0.2 (Arquitectura Desacoplada / Fail-Safe) |
| :--- | :---: | :---: |
| **Exactitud (Accuracy)** | 50.0% | **100.0%** |
| **F1-Score** | 0.546 | **1.000** |
| **False Allow Rate (Crítico)** | 44.4% | **0.0%** |
| **Acciones Destructivas Falsamente Permitidas** | 1 | **0 (Brecha crítica cerrada)** |
| **Latencia Media** | 0.07 ms | 0.22 ms |

---

## 4. Estructura de Paquetes v0.2

```
jev-reasoning-navigator/
├── jev_navigator/
│   ├── domain/                   # Entidades puras y contratos inmutables (Pydantic v2)
│   │   ├── goal.py               # Goal, SuccessCriterion, SubGoal
│   │   ├── action.py             # ActionCandidate, ToolCall, BatchSemantics
│   │   ├── observation.py        # Observation, ToolOutput
│   │   ├── evidence.py           # Evidence, GroundingStatus
│   │   ├── assessment.py         # ProviderAssessment, JEVAssessment, RiskAssessment
│   │   ├── decision.py           # PolicyDecision, DecisionReceipt, DecisionStatus
│   │   ├── checkpoint.py         # Checkpoint, SessionSnapshot
│   │   ├── state.py              # SessionState (hash canónico SHA-256 determinista)
│   │   ├── models.py             # Re-exportador canónico de dominio
│   │   └── interfaces.py         # Protocols: ReasoningProvider, EvidenceProvider, Executor
│   ├── providers/                # Adaptadores de inferencia semántica
│   │   ├── typesafe.py           # Adaptador de TypeSafe AI System One con fail-safe
│   │   └── replay.py             # ReplayProvider determinista para tests y benchmarks offline
│   ├── reasoning/                # Evaluación de evidencias, bucles, fundamentación y completitud
│   │   ├── evidence.py           # EvidenceEngine (almacén, validación e invalidación)
│   │   ├── loop_detector.py      # LoopDetector y análisis de anomalías
│   │   ├── grounding.py          # GroundingVerifier (fundamentación empírica estricta)
│   │   ├── risk.py               # RiskEngine (inspección de argumentos shell y archivos)
│   │   └── completion.py         # CompletionVerifier (anti-premature finish)
│   ├── policy/                   # Políticas operacionales de admisión
│   │   ├── registry.py           # ToolRegistry y ToolSpec tipados
│   │   ├── permissions.py        # PermissionManager y control de acceso RBAC
│   │   ├── failsafe.py           # FailSafePolicy para caídas de red o incertidumbre
│   │   └── engine.py             # PolicyEngine (matriz ALLOW / BLOCK / REPLAN / ABSTAIN)
│   ├── runtime/                  # Estado, orquestación, checkpoints y ejecución
│   │   ├── state_store.py        # InMemoryStateStore y abstracciones de persistencia
│   │   ├── checkpoints.py        # CheckpointManager y rollback con invalidación de descendientes
│   │   ├── executor.py           # SecureExecutor y excepción PolicyViolation
│   │   └── navigator.py          # Navigator (orquestador del pipeline completo)
│   ├── integrations/             # Integraciones externas y protocolos
│   │   └── mcp/                  # Servidor Model Context Protocol nativo v0.2.0
│   │       └── server.py         # Servidor MCP stdio con registro formal de herramientas
│   ├── evaluation/               # Framework de benchmarking y métricas
│   │   ├── scenarios.py          # ScenarioCatalog y generador con ground truth
│   │   ├── metrics.py            # Precision, Recall, F1, FalseAllowRate, percentiles p50/p95
│   │   ├── reports.py            # Generador formal de informes de benchmark
│   │   └── runner.py             # BenchmarkRunner y motor de ablaciones
│   ├── interceptor/              # Servidor MCP y middleware de tiempo real
│   │   ├── mcp_bridge.py         # Servidor Model Context Protocol (v0.1 + v0.2)
│   │   └── proxy_middleware.py   # Middleware para agentes LLM en streaming
│   ├── cli.py                    # Consola interactiva CLI enriquecida con Rich
│   ├── live_agent.py             # Agente autónomo con Gemini supervisado en vivo
│   └── dashboard.py              # Dashboard TUI interactivo en tiempo real
├── tests/                        # 113 tests unitarios y de integración pasando al 100%
├── pyproject.toml
└── README.md
```

---

## 5. Instalación y Configuración

### Requisitos
- Python >= 3.11
- Gestor de paquetes `uv` (recomendado) o `pip`

```bash
git clone https://github.com/AndreuVM/jev-reasoning-navigator.git
cd jev-reasoning-navigator

# Instalación con uv
uv sync
```

### Configuración del archivo `.env`
Crea un archivo `.env` en la raíz del proyecto:
```env
TYPESAFE_API_KEY=tu_typesafe_api_key
GEMINI_API_KEY=tu_gemini_api_key
```

---

## 6. Uso desde la Línea de Comandos (CLI)

El CLI `jev-nav` provee acceso tanto a las capacidades analíticas de la v0.1 como a los nuevos motores de benchmark de la v0.2:

### A. Suite Formal de Benchmark y Ablaciones (`jev-nav benchmark`)
```bash
# 1. Ejecutar benchmark completo con tabla de escenarios y métricas consolidadas
uv run jev-nav benchmark

# 2. Ejecutar estudio formal de ablaciones de las 5 capas
uv run jev-nav benchmark --ablation

# 3. Comparativa cuantitativa de seguridad v0.1 vs v0.2
uv run jev-nav benchmark --compare-v1

# 4. Exportar reporte de auditoría a JSON
uv run jev-nav benchmark --output auditoria_report.json
```

### B. Dashboard TUI en Vivo (`jev-dash` / `jev-nav dashboard`)
Monitor visual interactivo en terminal con 3 paneles sincronizados en tiempo real:
```bash
# Modo demostración interactiva
uv run jev-dash

# Modo vivo conectando el agente LLM real
uv run jev-dash --live --model gemini-3.6-flash --max-steps 25
```

| Parámetro | Tipo | Por defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--live` | `flag` | `False` | Conecta el agente LLM real en vivo. |
| `--task` | `string` | `None` | Objetivo o tarea inicial a resolver. |
| `--model` | `string` | `gemini-3.6-flash` | Modelo de Gemini para la ejecución. |
| `--max-steps` | `int` | `25` | Límite máximo de turnos permitidos. |
| `--once` | `flag` | `False` | Ejecuta una única tarea y finaliza. |

### C. Agente Autónomo Interactivo (`jev-live`)
```bash
# Modo continuo interactivo
uv run jev-live

# Ejecutar una tarea puntual con modelo específico
uv run jev-live "Corregir función en parser.py" --model gemini-2.5-flash --once --steps 20
```

---

## 7. Servidor MCP (Model Context Protocol)

`JEV-Reasoning-Navigator` incluye un servidor MCP compatible con clientes como **Antigravity IDE**, **Claude Desktop** y **Cursor**:

```json
{
  "mcpServers": {
    "jev-navigator": {
      "command": "uv",
      "args": ["run", "jev-mcp"],
      "cwd": "C:/ruta/al/proyecto/jev-reasoning-navigator"
    }
  }
}
```

### Herramientas MCP Nativas v0.2:
- `jev_v2_start_session(goal, session_id)`: Inicializa una sesión formal con objetivo y checkpoint génesis.
- `jev_v2_evaluate_action(action, goal, session_id)`: Evalúa una acción candidata a través de todo el pipeline emitiendo decisión operacional y recibo auditable.
- `jev_v2_step_and_execute(action, auto_checkpoint)`: Evalúa y ejecuta físicamente con captura de observación, auto-checkpoint y actualización de evidencia.
- `jev_v2_rollback(checkpoint_id, culprit_tool, reason)`: Restaura el estado al último checkpoint e invalida la herramienta reincidente.
- `jev_v2_get_session_state()`: Devuelve el snapshot serializado del estado y su SHA-256 canónico.

### Herramientas MCP Compatibles v0.1:
- `jev_evaluate_next_step`: Evaluación reactiva de siguiente paso.
- `jev_evaluate_step_chunk`: Evaluación de bloques candidatos de 3-4 pasos.
- `jev_diagnose_trace`: Diagnóstico de traza completa de razonamiento.

---

## 8. Uso Programático en Python (Runtime v0.2)

```python
from jev_navigator.domain import Goal, ActionCandidate, ToolCall
from jev_navigator.providers.typesafe import TypeSafeAdapter
from jev_navigator.runtime import Navigator, SecureExecutor

# 1. Inicializar componentes desacoplados
provider = TypeSafeAdapter()             # Juicio semántico (TypeSafe System One)
executor = SecureExecutor(dry_run=False) # Ejecución física garantizada
navigator = Navigator(provider=provider, executor=executor)

# 2. Iniciar sesión formal con objetivo y criterios verificables
goal = Goal(
    objective="Refactorizar módulo de pagos",
    success_criteria=["archivo payment.py actualizado", "tests de pagos pasando al 100%"]
)
state = navigator.start_session(goal, session_id="sesion_01")

# 3. Supervisar y ejecutar un paso normativo
accion = ActionCandidate(
    id="paso_1",
    description="Leer archivo de configuración",
    tool_call=ToolCall(tool_name="read_file", arguments={"path": "config.yaml"}),
    requires_evidence=[]
)

decision, observacion = navigator.step(accion, auto_checkpoint=True)

if decision.status == "allow":
    print(f"Paso ejecutado con éxito: {observacion.output}")
else:
    print(f"Acción denegada por política: {decision.status} - Motivos: {decision.reason_codes}")

# 4. Recuperación determinista ante bucles
if decision.status == "replan":
    navigator.rollback(culprit_tool=accion.tool_call.tool_name, reason="Degradación de trayectoria")
```

---

## 9. Verificación de la Suite de Pruebas

Toda la arquitectura v0.2 y la compatibilidad con v0.1 están respaldadas por **113 pruebas unitarias y de integración automatizadas**:

```bash
uv run pytest -v
# ============================ 113 passed in 36.28s =============================
```

---

## Licencia

Distribuido bajo licencia MIT. Consulta `LICENSE` para más detalles.
