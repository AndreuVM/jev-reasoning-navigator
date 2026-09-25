# JEV Reasoning Navigator v0.4.0

**Runtime de Seguridad, Gobernanza Cognitiva y Supervisión Formal para Agentes Autónomos de IA**

[![Tests](https://img.shields.io/badge/tests-199%20passed-brightgreen.svg)]()
[![Version](https://img.shields.io/badge/version-v0.4.0-blue.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![Security](https://img.shields.io/badge/security-sandbox%20%26%20container%20hardened-green.svg)]()
[![Providers](https://img.shields.io/badge/providers-TypeSafe%20%7C%20LAYA%20%7C%20CascadeRouter-purple.svg)]()

`JEV Reasoning Navigator` es un middleware de supervisión formal y runtime de seguridad desacoplado para agentes autónomos basados en LLM (*ReAct*, *Tool-use*, *Tree-of-Thought*). 

Evolucionado a la versión **v0.4.0** a partir de la implementación de enrutamiento adaptativo (*Confidence-Aware Routing & Calibración*): enrutador en cascada de dos niveles (`ConfidenceAwareRouter`), vía rápida local (System-1 / LAYA), escalado dinámico a supervisores superiores (System-2 / TypeSafe), umbrales adaptativos por nivel de riesgo operacional, detección de incertidumbre dual con abstención formal (`ABSTAIN`), análisis formal de calibración probabilística (ECE, MCE, Brier Score, curvas de Cobertura vs Riesgo Selectivo) y suite de evaluación multidimensional con 1.000+ escenarios procedurales.

$$\text{Semantic Judgment (JEV/LAYA Router)} \neq \text{Operational Policy (PolicyEngine)} \neq \text{Capability Receipt (HMAC)} \neq \text{Enforced Sandbox/Container (SecureExecutor)}$$

---

## ⚡ Inicio Rápido (Zero-Config / 100% Offline)

Puedes probar JEV Reasoning Navigator inmediatamente **sin costo de API, sin registro y sin conexión externa**:

```bash
# 1. Clonar e instalar en entorno virtual
git clone https://github.com/AndreuVM/jev-reasoning-navigator.git
cd jev-reasoning-navigator
pip install -e ".[dev]"

# 2. Ejecutar la demostración interactiva visual (sin APIs externas)
python demo.py

# 3. Ejecutar la suite completa de benchmarks reproducibles
python scripts/run_benchmarks.py
```


## 1. Axiomas y Principios Arquitectónicos de v0.4

1. **Juicio Semántico $\neq$ Política Operacional:**
   Una acción puede tener una probabilidad semántica de éxito elevada ($JEV = 0.95$) y ser al mismo tiempo operacionalmente inadmisible ($Risk = \text{CRITICAL}$, ej. `rm -rf /` o un archivo sensible `.env`). JEV emite juicio probabilístico; la `PolicyEngine` emite la decisión operativa (`ALLOW`, `BLOCK`, `REPLAN`, `ABSTAIN`).
2. **Enforcement Criptográfico Basado en Capabilities (HMAC-SHA256 y Anti-Replay con Store Durable):**
   Las instrucciones textuales inyectadas en prompts (*"Por favor no uses delete_file"*) no constituyen seguridad. `SecureExecutor` actúa como una barrera física criptográficamente ligada a nivel de runtime: exige obligatoriamente un `DecisionReceipt` firmado mediante **HMAC-SHA256**, no expirado (`expires_at`), con `status == ALLOW`, `action_hash == hash(action)` y `state_hash == hash(state)`. Invocaciones directas, firmas manipuladas, capabilities caducados o intentos de reutilización (*replay attacks*) son bloqueados inmediatamente por un almacén de nonces durable en SQLite (`SqliteNonceStore`) o memoria (`InMemoryNonceStore`) con poda automática por TTL (`prune_expired`), levantando `PolicyViolation` antes de tocar el sistema operativo.
3. **Aislamiento en Contenedores y Sandboxing de Procesos ($\text{Policy Enforcement} \neq \text{Host Isolation}$):**
   La ejecución física de herramientas del sistema (`run_command`, `read_file`, `edit_file`) no corre en el host con `shell=True`. Se delega en `SandboxAdapter`:
   - `ContainerSandboxAdapter`: Confinamiento en contenedores OCI (Docker/Podman) con filesystem raíz de solo lectura (`--read-only`), aislamiento de red total (`--network=none`), límites de memoria/CPU (cgroups), supresión de privilegios (`--cap-drop=ALL`) y fallback ordenado a sandbox local.
   - `LocalProcessSandbox`: Confina los accesos al workspace resolviendo enlaces simbólicos canónicos (`os.path.realpath`) para anular vectores de *symlink traversal* y *TOCTOU*, bloquea proactivamente comandos de egress de red (`curl`, `wget`, `nc`, `ssh`) cuando `allow_network=False`, neutraliza variables de entorno proxy hacia `127.0.0.1:0`, depura API keys del proceso hijo y ejecuta procesos tokenizados con límites estrictos de timeout.
4. **Política Formal de Egress de Red y Defensa contra SSRF (`EgressPolicy`):**
   Neutraliza vectores de fuga de credenciales o ataque a servicios internos bloqueando incondicionalmente interfaces de loopback (`127.0.0.1`, `localhost`), rangos privados RFC 1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) y metadatos cloud (`169.254.169.254`, `metadata.google.internal`), permitiendo únicamente dominios validados en modo `ALLOWLIST`.
5. **Persistencia Durable de Estado y Auditoría Inmutable:**
   - `SqliteStateStore`: Serialización transaccional de sesiones y checkpoints versionados en SQLite WAL.
   - `PermissionManager`: Trazabilidad completa en disco mediante archivo de log de auditoría JSONL inmutable (`audit_log_path`) con marcas de tiempo y hashes criptográficos de cada aprobación humana.
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
9. **Normalización y Acotación Estricta de Contexto (`ProviderContextBuilder`):**
   La construcción de inputs para los modelos semánticos no concatena texto libre sin límites. `ProviderContextBuilder` impone ventanas temporales acotadas de pasos históricos (`max_history_steps`), budgets estrictos de tokens (`token_budget`), truncamiento canónico de salidas voluminosas de herramientas (`max_observation_chars`) con señalización explícita (`truncated: bool`), generando serializaciones tipadas independientes para LAYA y TypeSafe AI.
10. **Supervisión Selectiva y Escalado por Confianza (*JEV-as-a-Judge: Accept When Confident, Escalate When Unsure*):**
   La inferencia probabilística del proveedor no es una decisión ciega: si el proveedor emite una evaluación con baja confianza ($\text{confidence} < 0.40$), el motor de política no otorga permiso ni arriesga ejecuciones dudosas, sino que escala deterministamente a `DecisionStatus.ABSTAIN` con código `LOW_PROVIDER_CONFIDENCE_ESCALATE` para requerir supervisión humana o intervención guiada.

---

## 2. Flujo de Ejecución Normativo v0.3-alpha

$$\text{Proposal} \to \text{Evidence} \to \text{Risk} \to \text{ProviderContext} \to \text{Semantic Provider (LAYA / TypeSafe)} \to \text{Policy} \to \text{Capability Receipt} \to \text{SecureExecutor} \to \text{Sandbox} \to \text{Observation}$$

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

## 4. Estructura de Paquetes v0.3-alpha

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
│   │   ├── assessment.py         # ProviderAssessment (con metadata de reproducibilidad), JEVAssessment, RiskAssessment
│   │   ├── decision.py           # PolicyDecision, DecisionReceipt, HMAC signature verification, compute_action/state_hash
│   │   ├── checkpoint.py         # Checkpoint, SessionSnapshot
│   │   ├── state.py              # SessionState (hash canónico SHA-256 determinista)
│   │   ├── models.py             # Re-exportador canónico de dominio
│   │   └── interfaces.py         # Protocols: ReasoningProvider, EvidenceProvider, Executor
│   ├── providers/                # Adaptadores de inferencia semántica desacoplados
│   │   ├── context.py            # ProviderContextBuilder con token budgeting, windowing y truncamiento
│   │   ├── laya.py               # LayaProvider (System-1 primitives: choice, score, noul; auto/local/hosted/simulated)
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
│   │   └── engine.py             # PolicyEngine con escalado por baja confianza, confirmación humana y firma HMAC
│   ├── runtime/                  # Estado, orquestación, checkpoints, sandbox y ejecución
│   │   ├── state_store.py        # InMemoryStateStore y abstracciones de persistencia
│   │   ├── nonce_store.py        # NonceStore con poda por TTL y defensa anti-replay duradera
│   │   ├── checkpoints.py        # CheckpointManager y rollback con invalidación de descendientes
│   │   ├── sandbox.py            # SandboxAdapter, LocalProcessSandbox (env scrubbing, realpath jail, network block) y DryRunSandbox
│   │   ├── executor.py           # SecureExecutor con HMAC capability verification, no-replay y expiration check
│   │   └── navigator.py          # Navigator (orquestador del pipeline completo)
│   ├── integrations/             # Integraciones externas y protocolos
│   │   └── mcp/                  # Servidor Model Context Protocol nativo v0.2.2+
│   │       └── server.py         # Servidor MCP stdio con registro formal de herramientas v2
│   ├── evaluation/               # Framework de benchmarking y métricas
│   │   ├── scenarios.py          # ScenarioCatalog y generador con ground truth
│   │   ├── metrics.py            # Decision and Physical Execution safety metrics
│   │   ├── reports.py            # Generador formal de informes de benchmark y ProviderComparisonReport
│   │   └── runner.py             # BenchmarkRunner con verificación física y ejecución multi-proveedor
│   ├── interceptor/              # Servidor MCP y middleware de tiempo real
│   │   ├── mcp_bridge.py         # Servidor Model Context Protocol (v0.1 + nativo v0.2.2+)
│   │   └── proxy_middleware.py   # Middleware para agentes LLM en streaming
│   ├── cli.py                    # Consola interactiva CLI enriquecida con Rich y soporte multi-proveedor
│   ├── live_agent.py             # Agente autónomo con Gemini supervisado en vivo
│   └── dashboard.py              # Dashboard TUI interactivo en tiempo real
├── tests/                        # 146 tests unitarios, de integración, endurecimiento, bypass y conformidad pasando al 100%
├── SECURITY.md                   # Política formal de divulgación y modelo de amenazas
├── pyproject.toml                # v0.3.0a1
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

# 2. Ejecutar benchmark comparativo entre proveedores (Replay, LAYA, TypeSafe)
uv run jev-nav benchmark --compare-providers

# 3. Ejecutar benchmark seleccionando un proveedor específico
uv run jev-nav benchmark --provider laya

# 4. Ejecutar estudio formal de ablaciones de las 5 capas
uv run jev-nav benchmark --ablation

# 5. Comparativa cuantitativa de seguridad v0.1 vs v0.2
uv run jev-nav benchmark --compare-v1

# 6. Exportar reporte de auditoría a JSON
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

## 8. Uso Programático en Python (Runtime v0.3-alpha)

```python
from jev_navigator.domain import Goal, ActionCandidate, ToolCall
from jev_navigator.providers import LayaProvider, TypeSafeAdapter
from jev_navigator.runtime import Navigator, SecureExecutor

# 1. Inicializar componentes desacoplados con proveedor a elección (LAYA o TypeSafe)
# LAYA: Primitivas System-1 (choice, score, noul) con backends local, hosted o simulado
provider = LayaProvider(backend="auto")
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
elif decision.status == "abstain":
    print(f"Acción escalada a revisión humana: {decision.reason_codes}")
else:
    print(f"Acción denegada por política: {decision.status} - Motivos: {decision.reason_codes}")

# 4. Recuperación determinista ante bucles
if decision.status == "replan":
    navigator.rollback(culprit_tool=accion.tool_call.tool_name, reason="Degradación de trayectoria")
```

---

## 9. Verificación de la Suite de Pruebas e Invariantes
 
Toda la arquitectura v0.4a1, los contratos formales de proveedores (`LayaProvider`, `TypeSafeAdapter`, `ReplayProvider`, `ConfidenceAwareRouter`), el acotamiento de contexto, las barreras de enforcement físico y la suite de evaluación multidimensional están respaldadas por **199 pruebas automatizadas al 100%**:
 
```bash
pytest -q
# .........s.............................................................. [ 36%]
# ........................................................................ [ 72%]
# ........................................................                 [100%]
# 199 passed, 1 skipped in 46.43s
```
 
---
 
## 10. Capacidades Avanzadas de Runtime y Gobernanza (v0.3 / v0.4)

- **Proveedor LAYA con Primitivas System-1 (`LayaProvider`)**:
  Inferencia probabilística desacoplada que calcula veredictos de clasificación (`choice`), estimación continua de avance (`score`), y probabilidades calibradas de bucle y fundamentación (`noul`). Soporta modos `local` (pesos de red locales), `hosted` (vía HTTP/RPC), `simulated` (determinista para test/CI) y selección automática `auto`, exponiendo metadatos completos de telemetría y reproducibilidad (`latency_ms`, `context_tokens`, `device`, `checkpoint_version`).
- **Normalizador y Gestor de Presupuesto de Contexto (`ProviderContextBuilder`)**:
  Ventanas temporales acotadas (`max_history_steps`), control de presupuesto de tokens (`token_budget`), truncamiento seguro de observaciones extensas (`max_observation_chars`) con marcado formal `truncated: bool`, y exportación canónica para backends LAYA y TypeSafe.
- **Router en Cascada Sensible a la Confianza (`ConfidenceAwareRouter`)**:
  Estrategia adaptativa de inferencia que evalúa primero con modelos ultrarrápidos (p.ej. LAYA) y deriva automáticamente a evaluadores más profundos si la confianza es inferior al umbral calibrado o existe riesgo operacional elevado.
- **Firmas Criptográficas HMAC-SHA256 (`DecisionReceipt`)**:
  Autenticación matemática de cada capability emitido por la `PolicyEngine`, garantizando que ninguna acción sea ejecutada con recibos manipulados o apócrifos.
- **Defensa Anti-Replay con Almacén Durable (`NonceStore` / `SqliteNonceStore`)**:
  Control concurrente de nonces únicos con caducidad temporal (`expires_at`) y poda automática periódica (`prune_expired`), impidiendo la reutilización de capabilities autorizados en el pasado.
- **Sandbox con Defensa Anti-Symlink y Política de Egress (`LocalProcessSandbox` / `ContainerSandbox`)**:
  Resolución física de rutas canónicas (`os.path.realpath`) para anular escapes de symlinks y directory traversal; filtrado estricto de tráfico saliente (`EgressPolicy`) con soporte para bloqueo total (`block_all`), lista blanca de dominios y prevención de ataques SSRF a metadatos cloud (`169.254.169.254`).
- **Verificación Estructurada Tipada de Completitud (`CompletionVerifier`)**:
  Evaluación formal contra criterios tipados (`CriterionType.FILE_EXISTS`, `TESTS_PASS`, `EXIT_CODE_ZERO`, `STATE_VALUE`, `CUSTOM`) retornando `CriterionStatus.VERIFIED` para impedir finalizaciones prematuras.
- **Gestor de Checkpoints y Reversión Formal (`CheckpointManager`)**:
  Creación determinista de snapshots de sesión con rollback ante ramas degenerativas, invalidación de descendientes y bloqueo de transiciones fallidas.

---

## 11. Suite de Evaluación Multidimensional (Fase 4)

El módulo `jev_navigator.evaluation` implementa una batería completa y desacoplada de benchmarks para medir exhaustivamente la calidad de decisión, resistencia física y rendimiento del supervisor:

1. **Dataset Procedural con Partición Holdout (1.000+ escenarios)**:
   - Partición determinista libre de sobreajuste: **800 train / desarrollo** y **200 holdout / prueba** (`ScenarioCatalog.get_holdout_scenarios`).
   - Distribución estratificada en 13 categorías (bucles de 1 a N saltos, fijación semántica, desfundamentación, comandos destructivos, caídas de proveedor y efectos laterales).
2. **Las 5 Dimensiones de Benchmark Especializadas**:
   - **Provider Benchmark**: Precisión, acuerdo inter-proveedor (*agreement rate*), concordancia decisional y latencias p50/p95 entre JEV, LAYA y el Router de Cascada.
   - **Policy Benchmark**: Evaluación de decisiones (`ALLOW`, `BLOCK`, `REPLAN`, `ABSTAIN`), matrices de confusión, tasa de falsos permitidos (`false_allow_rate = 0.0%`) y precisión de bloqueo justificado.
   - **Enforcement Benchmark**: Verificación de barrera física infranqueable (100% prevención de bypasses frente a firmas HMAC alteradas, ataques de replay, evasión por path traversal y violaciones de política egress SSRF).
   - **Runtime Benchmark**: Rendimiento operacional en tiempo real, midiendo throughput (*ops/sec*) y distribución percentil de latencias (`p50`, `p95`, `p99`, `mean`).
   - **Trajectory Benchmark**: Simulación de trayectorias multi-paso de agentes autónomos, validando la detección de bucles cíclicos, activación de rollbacks hacia checkpoints válidos, recuperación adaptativa (*recovery rate*) y prevención de finalizaciones prematuras.
3. **Estudio de Ablación Cuantitativo (6 Configuraciones)**:
   - *Config 1: Sin Supervisor (Baseline / Agente ciego)*
   - *Config 2: Solo Provider JEV (Sin reglas operacionales)*
   - *Config 3: Solo Reglas / FailSafe (Sin razonamiento semántico)*
   - *Config 4: JEV + Reglas (Sin evidencia contextual)*
   - *Config 5: JEV Reasoning Navigator Completo (v0.2/v0.3)*
   - *Config 6: Confidence-Aware Cascade Router (JEV + LAYA Handoff)*
   - Cada configuración computa automáticamente métricas de clasificación, seguridad física y valor económico neto ($\text{NavigatorValue}$).

---

## 12. Limitaciones Actuales y Alcance Técnico

De acuerdo con las mejores prácticas de rigor científico y divulgación técnica transparente, se documentan las siguientes limitaciones del sistema en su versión actual:

1. **Aislamiento en Host Windows vs Linux (Paridad de Sandboxing):**
   - En entornos Linux con Docker o Podman, `ContainerSandboxAdapter` proporciona aislamiento completo a nivel de kernel mediante namespaces de proceso, red, montajes de solo lectura y control estricto de cgroups.
   - En hosts Windows nativos sin contenedor, `LocalProcessSandbox` protege el sistema resolviendo rutas canónicas (`os.path.realpath`) y bloqueando procesos no permitidos, pero el filtrado de red a nivel de socket depende de la política de egress sobre comandos invocados (`curl`, `wget`) y no de un firewall de kernel dedicado.
2. **Horizonte de Contexto y Truncamiento (`ProviderContextBuilder`):**
   - Con el fin de preservar latencias inferiores a 1 ms ($p50$), el constructor de contexto recorta observaciones voluminosas y acota la ventana temporal de pasos históricos. Si una evidencia empírica crucial ocurrió hace muchos turnos y no fue debidamente registrada en `EvidenceEngine`, el supervisor exigirá una re-inspección explícita antes de autorizar mutaciones dependientes.
3. **Calibración de Umbrales en Dominios Específicos:**
   - Los umbrales de confianza del `ConfidenceAwareRouter` ($\tau=0.70-0.75$) han sido calibrados contra el catálogo procedural de agentes de desarrollo de software y administración de sistemas. Para dominios altamente especializados (p.ej. finanzas, medicina o interacción con APIs propietarias opacas), se recomienda ejecutar `scripts/run_benchmarks.py` sobre un conjunto representativo para reajustar los umbrales de riesgo selectivo.
4. **Fundamentación Empírica vs Verificación Formal de Algoritmos:**
   - `EvidenceEngine` y `CompletionVerifier` garantizan que las precondiciones y criterios de éxito estén demostrados por observaciones observables en la sesión o en disco (archivos creados, logs de tests con exit code 0). No reemplazan a verificadores formales de teoremas (Z3, Coq, Lean) para la prueba matemática de corrección de código algorítmico arbitrario.

---

## Licencia

Distribuido bajo licencia MIT. Consulta `LICENSE` para más detalles.


