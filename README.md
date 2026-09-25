# JEV Reasoning Navigator v0.2.2

**Runtime de Seguridad, Gobernanza Cognitiva y Supervisión Formal para Agentes Autónomos de IA**

[![Tests](https://img.shields.io/badge/tests-137%20passed-brightgreen.svg)]()
[![Version](https://img.shields.io/badge/version-v0.2.2-blue.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![Security](https://img.shields.io/badge/security-sandbox%20hardened-green.svg)]()
[![TypeSafe AI](https://img.shields.io/badge/engine-TypeSafe%20System%20One-purple.svg)]()

`JEV Reasoning Navigator` es un middleware de supervisión formal y runtime de seguridad desacoplado para agentes autónomos basados en LLM (*ReAct*, *Tool-use*, *Tree-of-Thought*). 

Evolucionado en la **v0.2.2** a partir de rigurosas auditorías técnicas externas y el cierre de deuda técnica de la Fase 0, el sistema trasciende los clasificadores heurísticos de bucles para establecer una separación formal de responsabilidades:
$$\text{Semantic Judgment (JEV)} \neq \text{Operational Policy (PolicyEngine)} \neq \text{Capability Receipt (HMAC)} \neq \text{Enforced Process Sandbox (SecureExecutor)}$$

---

## 1. Axiomas y Principios Arquitectónicos de v0.2.2

1. **Juicio Semántico $\neq$ Política Operacional:**
   Una acción puede tener una probabilidad semántica de éxito elevada ($JEV = 0.95$) y ser al mismo tiempo operacionalmente inadmisible ($Risk = \text{CRITICAL}$, ej. `rm -rf /` o un archivo sensible `.env`). JEV emite juicio probabilístico; la `PolicyEngine` emite la decisión operativa (`ALLOW`, `BLOCK`, `REPLAN`, `ABSTAIN`).
2. **Enforcement Criptográfico Basado en Capabilities (HMAC-SHA256 y Anti-Replay):**
   Las instrucciones textuales inyectadas en prompts (*"Por favor no uses delete_file"*) no constituyen seguridad. `SecureExecutor` actúa como una barrera física criptográficamente ligada a nivel de runtime: exige obligatoriamente un `DecisionReceipt` firmado mediante **HMAC-SHA256**, no expirado (`expires_at`), con `status == ALLOW`, `action_hash == hash(action)` y `state_hash == hash(state)`. Invocaciones directas, firmas manipuladas, capabilities caducados o intentos de reutilización (*replay attacks*) son bloqueados inmediatamente por un almacén de nonces con poda por TTL (`NonceStore`) levantando `PolicyViolation` antes de tocar el sistema operativo.
3. **Contención en Sandbox de Proceso vs Aislamiento de Host ($\text{Policy Enforcement} \neq \text{Host Isolation}$):**
   La ejecución física de herramientas del sistema (`run_command`, `read_file`, `edit_file`) no corre en el host con `shell=True`. Se delega en `SandboxAdapter` (`LocalProcessSandbox` o `DryRunSandbox`), que confina los accesos al workspace resolviendo enlaces simbólicos canónicos (`os.path.realpath`) para anular vectores de *symlink traversal* y *TOCTOU*, bloquea proactivamente comandos de egress de red (`curl`, `wget`, `nc`, `ssh`) cuando `allow_network=False`, neutraliza variables de entorno proxy hacia `127.0.0.1:0`, depura API keys del proceso hijo y ejecuta procesos tokenizados con límites estrictos de timeout.  
   > **Nota sobre el Modelo de Amenazas:** `LocalProcessSandbox` endurece y restringe procesos locales a nivel de aplicación. No sustituye un hipervisor de virtualización a nivel de kernel, microVM (como Firecracker) o contenedor Linux (cgroups/namespaces/seccomp). Para despliegues multi-inquilino de código hostil o no confiable, se debe encapsular el ejecutor en contenedores o microVMs dedicadas.
4. **La Indisponibilidad no Equivale a Neutralidad (Fail-Safe Estricto):**
   Si la red falla o el proveedor de inferencia semántica se cae, el sistema no asume un score neutro permisivo: aplica `FailSafePolicy` emitiendo `ABSTAIN` para acciones de bajo riesgo o `BLOCK` inmediato para acciones destructivas ($FalseAllowRate = 0.0\%$).
5. **Erradicación de Alucinaciones en Herramientas de Observación:**
   Invocaciones como `read_file("archivo_inventado.py")` parten de premisas 100% alucinadas. `EvidenceEngine` valida que existan observaciones previas antes de permitir acciones dependientes y descalifica evidencias obsoletas cuando ocurren mutaciones (*stale state defense*).
6. **Anti-Premature Finish y Verificación Estructurada de Criterios:**
   `CompletionVerifier` impide que el agente declare victoria prematura (`finish => highJEV`) sin antes validar formalmente que todos los criterios obligatorios (`CriterionType.FILE_EXISTS`, `TESTS_PASS`, `EXIT_CODE_ZERO`, `STATE_VALUE`, `CUSTOM`) cuenten con evidencias empíricas demostradas en disco o traza con estado `VERIFIED`.
7. **Autorización Humana Auditable con Ligadura de Hash y TTL:**
   `PermissionManager` expide tickets auditables `HumanApprovalTicket` vinculados estrictamente al `action_hash` exacto y dotados de caducidad temporal (`expires_at`). Cualquier manipulación de argumentos invalida la confirmación de inmediato.
8. **Backtracking Formal y Recuperación de Estado:**
   `CheckpointManager` captura snapshots canónicos SHA-256 de `SessionState`. Ante degradación o bucles, restaura el estado seguro, invalida los pasos descendientes y bloquea físicamente la herramienta o transición culpable.

---

## 2. Flujo de Ejecución Normativo v0.2.1

$$\text{Proposal} \to \text{Evidence} \to \text{Risk} \to \text{JEV Provider} \to \text{Policy} \to \text{Capability Receipt} \to \text{SecureExecutor} \to \text{Sandbox} \to \text{Observation}$$

```
                +---------------------------------------+
                |           Agente Autónomo             |
                +---------------------------------------+
                                   | Propone candidatos
                                   v
+-----------------------------------------------------------------------+
|                 JEV Reasoning Navigator (v0.2.1 Runtime)               |
|                                                                       |
|  1. EvidenceEngine        -> Verifica precondiciones empíricas        |
|  2. RiskEngine            -> Análisis contextual de comandos y rutas  |
|  3. TypeSafe / Replay     -> Inferencia semántica (Loop, Progress)    |
|  4. CompletionVerifier    -> Valida criterios de éxito frente a finish|
|  5. PermissionManager     -> Control de acceso humano RBAC integrado  |
|  6. PolicyEngine          -> Matriz formal (ALLOW / BLOCK / REPLAN)   |
|  7. DecisionReceipt       -> Emisión de capability ligado (SHA-256)   |
|  8. CheckpointManager     -> Captura snapshot preventivo si muta      |
|  9. SecureExecutor        -> Barrera física: verifica capability único|
| 10. LocalProcessSandbox   -> Ejecución aislada con env scrubbed & jail|
+-----------------------------------------------------------------------+
                                   | Observación
                                   v
                        +----------------------+
                        |   Sistema / Estado   |
                        +----------------------+
```

---

## 3. Estudio de Ablaciones y Comparativa de Seguridad

Los benchmarks reproducibles evalúan tanto la precisión decisional como la contención física de ejecución (vía `DryRunSandbox`), verificando el pipeline completo:
$$\text{Action} \to \text{Policy} \to \text{Signed Capability Receipt} \to \text{SecureExecutor} \to \text{Sandbox}$$

> **Nota metodológica sobre los benchmarks:** La suite incluye 10 escenarios normativos de validación directa y un catálogo paramétrico procedural capaz de generar 1.000+ escenarios sintéticos adversariales para contrastar propiedades e invariantes en condiciones extremas (caída de red, manipulaciones de hash, comandos ofuscados).

### 🔬 Estudio de Ablaciones (5 Capas Arquitectónicas):
| Configuración | Exactitud (Accuracy) | F1-Score | False Allow Rate (Crítico) | Destructive False Allows | Prevención Ejecución No Autorizada | Diagnóstico |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **1. Policy Only (Sin JEV)** | 60.0% | 0.666 | 33.3% | 0 | 66.7% | Incapaz de detectar bucles semánticos o estancamiento. |
| **2. JEV (Sin Evidence Engine)** | 80.0% | 0.822 | 11.1% | 0 | 88.9% | Autoriza acciones basadas en premisas alucinadas. |
| **3. JEV + Evidence (Sin Risk Engine)** | 50.0% | 0.638 | 44.4% | 2 | 55.6% | Permite comandos destructivos de shell (`rm -rf`). |
| **4. JEV + Evidence + Risk (Fallback v0.1)** | 60.0% | 0.677 | 33.3% | 1 | 66.7% | Fallo de proveedor autoriza acciones destructivas. |
| **5. Full v0.2.1 Architecture** | **100.0%** | **1.000** | **0.0%** | **0** | **100.0%** | **Enforcement físico total, sandbox aislado y cero brechas.** |

### 🛡️ Comparativa Directa: v0.1 vs v0.2.1
| Métrica | v0.1 (Heurístico / Fallback Permisivo) | v0.2.1 (Capabilities + Fail-Safe + Sandbox) |
| :--- | :---: | :---: |
| **Exactitud Decisional** | 60.0% | **100.0%** |
| **F1-Score Decisional** | 0.677 | **1.000** |
| **False Allow Rate (Métrica Crítica)** | 33.3% | **0.0%** |
| **Acciones Destructivas Falsamente Permitidas** | 1 | **0 (Brecha crítica cerrada)** |
| **Prevención de Ejecución No Autorizada** | 66.7% | **100.0%** |
| **Ejecuciones Físicas No Autorizadas** | 3 | **0** |
| **Verificación de Capabilities/Receipt** | N/A | **100.0%** |
| **Latencia Media** | 0.09 ms | 0.26 ms |

---

## 4. Estructura de Paquetes v0.2.2

```
jev-reasoning-navigator/
├── .ci/                          # CI/CD Workflows y automatización
│   └── workflows/
│       ├── test.yml              # Tests multiplataforma (Python 3.11 & 3.12, Windows & Linux)
│       └── security.yml          # Auditoría de seguridad con Bandit y comprobación de invariantes
├── jev_navigator/
│   ├── domain/                   # Entidades puras y contratos inmutables (Pydantic v2)
│   │   ├── goal.py               # Goal, SuccessCriterion, CriterionType, SubGoal
│   │   ├── action.py             # ActionCandidate, ToolCall, BatchSemantics
│   │   ├── observation.py        # Observation, ToolOutput
│   │   ├── evidence.py           # Evidence, GroundingStatus
│   │   ├── assessment.py         # ProviderAssessment, JEVAssessment, RiskAssessment
│   │   ├── decision.py           # PolicyDecision, DecisionReceipt, HMAC signature verification, compute_action/state_hash
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
│   │   └── completion.py         # CompletionVerifier estructurado tipado (anti-premature finish)
│   ├── policy/                   # Políticas operacionales de admisión
│   │   ├── registry.py           # ToolRegistry y ToolSpec tipados
│   │   ├── permissions.py        # PermissionManager, HumanApprovalTicket y RBAC
│   │   ├── failsafe.py           # FailSafePolicy para caídas de red o incertidumbre
│   │   └── engine.py             # PolicyEngine con soporte de confirmación humana y firma HMAC
│   ├── runtime/                  # Estado, orquestación, checkpoints, sandbox y ejecución
│   │   ├── state_store.py        # InMemoryStateStore y abstracciones de persistencia
│   │   ├── nonce_store.py        # NonceStore con poda por TTL y defensa anti-replay duradera
│   │   ├── checkpoints.py        # CheckpointManager y rollback con invalidación de descendientes
│   │   ├── sandbox.py            # SandboxAdapter, LocalProcessSandbox (env scrubbing, realpath jail, network block) y DryRunSandbox
│   │   ├── executor.py           # SecureExecutor con HMAC capability verification, no-replay y expiration check
│   │   └── navigator.py          # Navigator (orquestador del pipeline completo)
│   ├── integrations/             # Integraciones externas y protocolos
│   │   └── mcp/                  # Servidor Model Context Protocol nativo v0.2.2
│   │       └── server.py         # Servidor MCP stdio con registro formal de herramientas v2
│   ├── evaluation/               # Framework de benchmarking y métricas
│   │   ├── scenarios.py          # ScenarioCatalog y generador con ground truth
│   │   ├── metrics.py            # Decision and Physical Execution safety metrics
│   │   ├── reports.py            # Generador formal de informes de benchmark
│   │   └── runner.py             # BenchmarkRunner con verificación de ejecución física en sandbox
│   ├── interceptor/              # Servidor MCP y middleware de tiempo real
│   │   ├── mcp_bridge.py         # Servidor Model Context Protocol (v0.1 + nativo v0.2.2)
│   │   └── proxy_middleware.py   # Middleware para agentes LLM en streaming
│   ├── cli.py                    # Consola interactiva CLI enriquecida con Rich
│   ├── live_agent.py             # Agente autónomo con Gemini supervisado en vivo
│   └── dashboard.py              # Dashboard TUI interactivo en tiempo real
├── tests/                        # 137 tests unitarios, de integración, endurecimiento y bypass pasando al 100%
├── SECURITY.md                   # Política formal de divulgación y modelo de amenazas
├── pyproject.toml                # v0.2.2
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

### Herramientas MCP Nativas v0.2.1:
- `jev_v2_start_session(goal, session_id)`: Inicializa una sesión formal con objetivo y checkpoint génesis.
- `jev_v2_evaluate_action(action, goal, session_id)`: Evalúa una acción candidata a través de todo el pipeline emitiendo decisión operacional y capability/recibo auditable.
- `jev_v2_step_and_execute(action, auto_checkpoint)`: Evalúa y ejecuta físicamente en sandbox con captura de observación, auto-checkpoint y actualización de evidencia.
- `jev_v2_rollback(checkpoint_id, culprit_tool, reason)`: Restaura el estado al último checkpoint e invalida la herramienta reincidente.
- `jev_v2_get_session_state()`: Devuelve el snapshot serializado del estado y su SHA-256 canónico.
- `jev_v2_confirm_action(action_id)`: Registra la confirmación humana explícita para desbloquear acciones con `requires_confirmation=True`.

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

## 9. Verificación de la Suite de Pruebas e Invariantes
 
Toda la arquitectura v0.2.2, los contratos formales y las propiedades de seguridad están respaldadas por **137 pruebas automatizadas al 100%**:
 
```bash
pytest -q
# ........................................................................ [ 52%]
# .................................................................        [100%]
# 137 passed in 40.18s
```
 
---
 
## 10. Capacidades Avanzadas de Runtime y Gobernanza (v0.2.2)
 
- **Firmas Criptográficas HMAC-SHA256 (`DecisionReceipt`)**:
  Autenticación matemática de cada capability emitido por la `PolicyEngine`, garantizando que ninguna acción sea ejecutada con recibos manipulados o apócrifos.
- **Defensa Anti-Replay con Almacén Durable (`NonceStore`)**:
  Control concurrente de nonces únicos con caducidad temporal (`expires_at`) y poda automática periódica (`prune_expired`), impidiendo la reutilización de capabilities autorizados en el pasado.
- **Autorización Humana RBAC de Alta Precisión (`HumanApprovalTicket`)**:
  Tickets de confirmación humana obligatorios para comandos destructivos o llamadas de red, enlazados al hash criptográfico exacto de la acción y con expiración TTL.
- **Sandbox con Defensa Anti-Symlink y Bloqueo de Red (`LocalProcessSandbox`)**:
  Resolución física de rutas canónicas (`os.path.realpath`) para anular escapes de symlinks y directory traversal; bloqueo de comandos de red (`curl`, `wget`, `nc`, `ssh`) cuando `allow_network=False` y neutralización de variables proxy hacia `127.0.0.1:0`.
- **Verificación Estructurada Tipada de Completitud (`CompletionVerifier`)**:
  Evaluación formal contra criterios tipados (`CriterionType.FILE_EXISTS`, `TESTS_PASS`, `EXIT_CODE_ZERO`, `STATE_VALUE`, `CUSTOM`) retornando `CriterionStatus.VERIFIED` para impedir finalizaciones prematuras.
- **Resiliencia y Circuit Breaker (`CircuitBreaker`)**:
  Control de estados `CLOSED`, `OPEN` y `HALF_OPEN` con reintentos con backoff exponencial y jitter aleatorio, respetando cabeceras `Retry-After`.
- **Sanitización de Límites de Confianza (`DataSanitizer`)**:
  Enmascaramiento de credenciales, API keys, tokens JWT, claves privadas SSH/RSA, emails e IPs privadas, con envoltura de seguridad `<untrusted_content>` y truncamiento de payloads.
- **Ontología y Afirmaciones de Evidencia (`Claim`)**:
  Registro explícito de aserciones (`register_claim`) en `EvidenceEngine` para auditoría trazable de precondiciones y deducciones empíricas.
- **Telemetría y Bus de Eventos Estructurado (`EventBus`)**:
  Publicación sincrónica y persistencia JSONL de eventos tipados: `DecisionEvent`, `ObservationEvent`, `ToolExecutionEvent` e `InterventionEvent`.
- **Modo Sombra (`Shadow Mode`)**:
  Permite ejecutar el runtime en modo observador pasivo (`shadow_mode=True`), registrando discrepancias y telemetría sin bloquear físicamente las acciones del agente.
- **Modelo de Retorno Económico ($\text{NavigatorValue}$)**:
  $$\text{NavigatorValue} = \text{AvoidedFailureCost} - \text{NavigatorCost} - \text{AddedLatencyCost} - \text{FalseRejectPenalty}$$
  Evaluado automáticamente en cada ejecución del benchmark.
- **Benchmark Masivo Procedural (1.000+ Escenarios)**:
  Generación determinista y reproducible de 1.000 o más escenarios normativos cruzando 12 categorías operativas vía CLI:
  ```bash
  python -m jev_navigator.cli benchmark --count 1000
  ```

---

## Licencia

Distribuido bajo licencia MIT. Consulta `LICENSE` para más detalles.
