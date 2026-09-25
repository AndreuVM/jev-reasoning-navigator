# PRAXEON v0.4.0

**Runtime supervision for autonomous AI agents**

[![Tests](https://img.shields.io/badge/tests-199%20passed-brightgreen.svg)]()
[![Version](https://img.shields.io/badge/version-v0.4.0-blue.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![Security](https://img.shields.io/badge/security-sandbox%20%26%20container%20hardened-green.svg)]()
[![Providers](https://img.shields.io/badge/providers-TypeSafe%20%7C%20LAYA%20%7C%20CascadeRouter-purple.svg)]()

`PRAXEON` es un middleware de supervisión formal y runtime de seguridad desacoplado para agentes autónomos basados en LLM (*ReAct*, *Tool-use*, *Tree-of-Thought*). 

Evolucionado a la versión **v0.4.0** a partir de la implementación de enrutamiento adaptativo (*Confidence-Aware Routing & Calibración*): enrutador en cascada de dos niveles (`ConfidenceAwareRouter`), vía rápida local (System-1 / LAYA), escalado dinámico a supervisores superiores (System-2 / TypeSafe), umbrales adaptativos por nivel de riesgo operacional, detección de incertidumbre dual con abstención formal (`ABSTAIN`), análisis formal de calibración probabilística (ECE, MCE, Brier Score, curvas de Cobertura vs Riesgo Selectivo) y suite de evaluación multidimensional con 1.000+ escenarios procedurales.

$$\text{Semantic Judgment (JEV/LAYA Router)} \neq \text{Operational Policy (PolicyEngine)} \neq \text{Capability Receipt (HMAC)} \neq \text{Enforced Sandbox/Container (SecureExecutor)}$$

---

## ⚡ Inicio Rápido (Zero-Config / 100% Offline)

Puedes probar PRAXEON inmediatamente **sin costo de API, sin registro y sin conexión externa**:

```bash
# 1. Clonar e instalar en entorno virtual
git clone https://github.com/AndreuVM/praxeon.git
cd praxeon
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

## 2. Flujo de Ejecución Normativo de Runtime (v0.4)

$$\text{Proposal} \to \text{Evidence} \to \text{Risk} \to \text{ProviderContext} \to \text{Semantic Provider (LAYA / TypeSafe)} \to \text{Policy} \to \text{Capability Receipt} \to \text{SecureExecutor} \to \text{Sandbox} \to \text{Observation}$$

```
                +---------------------------------------+
                |           Agente Autónomo             |
                +---------------------------------------+
                                   | Propone candidatos
                                   v
+-----------------------------------------------------------------------+
|                 PRAXEON (Runtime Supervision Engine)                  |
|                                                                       |
|  1. EvidenceEngine        -> Verifica precondiciones empíricas        |
|  2. RiskEngine            -> Análisis contextual de comandos y rutas  |
|  3. Semantic Provider     -> Inferencia semántica (LAYA / TypeSafe)   |
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

Los benchmarks reproducibles evalúan formalmente tanto la precisión decisional como la contención física de ejecución (vía `SecureExecutor` y `LocalProcessSandbox`), verificando el pipeline completo:
$$\text{Action} \to \text{Policy} \to \text{Signed Capability Receipt (HMAC)} \to \text{SecureExecutor} \to \text{Sandbox}$$

> **Validación Rigurosa:** La suite evalúa un dataset procedural masivo de **1.000+ escenarios** dividido de forma estricta y determinista en **800 Train** y **200 Holdout** libre de sobreajuste, evaluando 6 configuraciones arquitectónicas y midiendo el valor económico neto del supervisor ($\text{NavigatorValue}$).

### 🔬 Estudio de Ablaciones (6 Configuraciones Arquitectónicas sobre Holdout $n=200$):
| Configuración Arquitectónica | Exactitud (Accuracy) | False Allow Rate | Destructive False Allows | Valor Neto Estimado ($\text{NavigatorValue}$) | Diagnóstico Operacional |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **1. Policy Only (Sin Modelo Semántico)** | 54.0% | 16.8% | 0 | $16,894.40 | Incapaz de detectar bucles semánticos o estancamiento de trayectoria. |
| **2. Provider Only (Sin Evidence Engine)** | 84.5% | 8.1% | 0 | $18,495.60 | Autoriza acciones basadas en premisas y archivos alucinados. |
| **3. Provider + Evidence (Sin Risk Engine)** | 68.5% | 25.4% | 32 | $15,294.00 | Permite comandos destructivos de shell (`rm -rf`, `DROP TABLE`). |
| **4. Provider + Evidence + Risk (Sin FailSafe)** | 68.5% | 25.4% | 16 | $15,294.40 | Caídas de proveedor o de red conceden ejecuciones destructivas. |
| **5. PRAXEON Full Single-Tier** | **100.0%** | **0.0%** | **0** | **$19,994.40** | **Enforcement físico total, sandbox aislado y cero brechas.** |
| **6. PRAXEON Full Cascade Router (LAYA + TypeSafe)** | **100.0%** | **0.0%** | **0** | **$19,994.40** | **Máxima seguridad con vía rápida local (~0.09 ms) y escalado dinámico.** |

### 🛡️ Comparativa: Agente Autónomo Sin Supervisor vs PRAXEON v0.4
| Métrica Operacional y de Seguridad | Agente Sin Supervisor (Baseline) | PRAXEON v0.4 (Full Architecture) |
| :--- | :---: | :---: |
| **Exactitud Decisional Global** | 54.0% | **100.0%** |
| **False Allow Rate (Métrica Crítica)** | 16.8% | **0.0% (Objetivo estricto cumplido)** |
| **Acciones Destructivas Permitidas** | 32 | **0 (Brecha crítica cerrada)** |
| **Prevención de Ejecución No Autorizada** | 0.0% | **100.0% (Barrera criptográfica HMAC)** |
| **Resistencia a Replay y Manipulación** | Vulnerable | **100.0% (NonceStore durable SQLite)** |
| **Contención de Path Traversal & SSRF** | Vulnerable | **100.0% (LocalProcessSandbox + EgressPolicy)** |
| **Latencia de Supervisión p50** | N/A | **0.093 ms (Sobrecarga imperceptible)** |
| **Throughput de Decisiones** | N/A | **~9.800 decisiones/segundo** |

---

## 4. Estructura de Paquetes

```
praxeon/
├── .ci/                          # CI/CD Workflows y automatización
│   └── workflows/
│       ├── test.yml              # Tests multiplataforma (Python 3.11 & 3.12, Windows & Linux)
│       └── security.yml          # Auditoría de seguridad con Bandit y comprobación de invariantes
├── praxeon/
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
│   │   └── mcp/                  # Servidor Model Context Protocol nativo
│   │       └── server.py         # Servidor MCP stdio con registro formal de herramientas v2
│   ├── evaluation/               # Framework de benchmarking y métricas
│   │   ├── scenarios.py          # ScenarioCatalog y generador con ground truth
│   │   ├── metrics.py            # Decision and Physical Execution safety metrics
│   │   ├── reports.py            # Generador formal de informes de benchmark y ProviderComparisonReport
│   │   └── runner.py             # BenchmarkRunner con verificación física y ejecución multi-proveedor
│   ├── interceptor/              # Servidor MCP y middleware de tiempo real
│   │   ├── mcp_bridge.py         # Puente Model Context Protocol y middleware
│   │   └── proxy_middleware.py   # Middleware para agentes LLM en streaming
│   ├── cli.py                    # Consola interactiva CLI enriquecida con Rich y soporte multi-proveedor
│   ├── live_agent.py             # Agente autónomo con Gemini supervisado en vivo
│   └── dashboard.py              # Dashboard TUI interactivo en tiempo real
├── tests/                        # 199 tests unitarios, de integración, endurecimiento, bypass y conformidad pasando al 100%
├── SECURITY.md                   # Política formal de divulgación y modelo de amenazas
├── pyproject.toml                # v0.4.0
└── README.md
```

---

## 5. Inferencia Local con LAYA (System-1 Open-Source)

`PRAXEON` incorpora soporte de primera clase para **LAYA**, un modelo de decisión no-autorregresivo de código abierto (Apache 2.0) diseñado como alternativa *open-weights* para razonamiento reflejo (System-1). A diferencia de los LLMs generativos convencionales que producen texto token a token, LAYA procesa el estado del agente y emite veredictos estructurados en un único *forward pass* ultrarrápido (~33 ms).

### Primitivas de Decisión de LAYA:
1. **`choice`**: Selección categórica (`ALLOW`, `REPLAN`, `BLOCK`, `ABSTAIN`) con distribución de probabilidades calibrada y nivel de confianza.
2. **`score`**: Medición continua del progreso del agente hacia la meta ($0.0 \text{ a } 1.0$).
3. **`noul`**: Probabilidades booleanas calibradas de bucle (`is_loop`), fundamentación empírica (`is_grounded`) y novedad (`is_novel`).

---

### ¿Cómo Funciona la Inferencia Local en PRAXEON?

#### A. Motor Local Calibrado (Zero-Download / Inmediato de Fábrica)
* **¿Requiere descargar pesos?:** **No.**
* Viene **100% integrado en PRAXEON** sin descargas pesadas ni necesidad de PyTorch.
* Opera en memoria con latencia inferior a **$0.1\text{ ms}$ ($p50$)**, evaluando de forma determinista y calibrada patrones de repetición, consistencia de evidencias y riesgo destructivo.
* Se activa por defecto con `LayaProvider(backend="auto")` o `backend="simulated"`.

```python
from praxeon.providers.laya import LayaProvider

# Inferencia local inmediata sin descargas externas
laya_fast = LayaProvider(backend="auto")
```

#### B. Red Neuronal Real Open-Source (`convaiinnovations/laya`)
* **¿Requiere descargar pesos?:** **Sí**, pero la descarga es **automática en la primera ejecución**.
* Para ejecutar los pesos neuronales reales del modelo (~421M parámetros) en tu CPU o GPU (CUDA) local:
  ```bash
  # 1. Instalar el soporte neuronal en tu entorno virtual
  pip install "praxeon[laya]"
  # o directamente:
  pip install laya
  ```
* Al instanciar `LayaProvider(backend="local")`, el SDK de LAYA descarga automáticamente los pesos oficiales desde Hugging Face (`convaiinnovations/laya`) en el primer arranque y los almacena en tu caché local (`~/.cache/huggingface/` o `~/.cache/laya/`).
* Las ejecuciones posteriores reutilizan la instancia en memoria cacheada, logrando tiempos de inferencia de **~33 ms** sin conectarse a internet.

```python
from praxeon.providers.laya import LayaProvider
from praxeon.runtime.navigator import Navigator

# Carga y ejecuta la red neuronal LAYA en hardware local (CPU/GPU)
laya_neural = LayaProvider(backend="local")
navigator = Navigator(provider=laya_neural)
```

#### C. Pesos en Directorio Local Personalizado
Si ya has descargado los pesos previamente o utilizas un checkpoint afinado (*fine-tuned*), indícale la ruta directamente:
```python
laya_custom = LayaProvider(
    backend="local",
    model_name="C:/modelos/laya-421m"  # O definiendo la variable de entorno LAYA_MODEL_PATH
)
```

#### D. Despliegue en Microservicio Alojado (REST / HTTP)
Si prefieres servir LAYA en un contenedor independiente mediante `pip install "laya[serve]"`:
```python
laya_hosted = LayaProvider(
    backend="hosted",
    endpoint_url="http://localhost:8000/v1/decide",
    auth_token="tu_token_opcional"
)
```

---

### Arquitectura en Cascada: System-1 (LAYA) + System-2 (TypeSafe)

En entornos de producción, la configuración recomendada aprovecha la velocidad extrema de LAYA local para el 90%+ de las decisiones cotidianas, derivando automáticamente a TypeSafe/JEV ante dudas o riesgo elevado mediante `ConfidenceAwareRouter`:

```python
from praxeon.providers.laya import LayaProvider
from praxeon.providers.typesafe import TypeSafeAdapter
from praxeon.providers.router import ConfidenceAwareRouter
from praxeon.runtime.navigator import Navigator

# Enrutador adaptativo: LAYA local (vía rápida) + TypeSafe (escalado ante incertidumbre)
cascade_router = ConfidenceAwareRouter(
    primary_provider=LayaProvider(backend="auto"),
    secondary_provider=TypeSafeAdapter(),
    default_confidence_threshold=0.75,
)

navigator = Navigator(provider=cascade_router)
```

---

## 6. Instalación y Configuración

### Requisitos
- Python >= 3.11
- Gestor de paquetes `uv` (recomendado) o `pip`

```bash
git clone https://github.com/AndreuVM/praxeon.git
cd praxeon

# Instalación estándar (incluye motor local calibrado de LAYA)
pip install -e ".[dev]"

# (Opcional) Instalar con soporte para red neuronal LAYA con pesos reales
pip install -e ".[dev,laya]"
```

### Configuración del archivo `.env`
Crea un archivo `.env` en la raíz del proyecto:
```env
TYPESAFE_API_KEY=tu_typesafe_api_key
GEMINI_API_KEY=tu_gemini_api_key
LAYA_ENDPOINT_URL=http://localhost:8000/v1/decide # Opcional si usas LAYA en microservicio
```

---

## 7. Uso desde la Línea de Comandos (CLI)

El CLI `praxeon` (o su alias `jev-nav`) provee acceso tanto a las capacidades analíticas como a los motores de benchmark y supervisión:

### A. Suite Formal de Benchmark y Ablaciones (`praxeon benchmark`)
```bash
# 1. Ejecutar benchmark completo con tabla de escenarios y métricas consolidadas
uv run praxeon benchmark

# 2. Ejecutar benchmark comparativo entre proveedores (Replay, LAYA, TypeSafe)
uv run praxeon benchmark --compare-providers

# 3. Ejecutar benchmark seleccionando un proveedor específico
uv run praxeon benchmark --provider laya

# 4. Ejecutar estudio formal de ablaciones de las 6 capas
uv run praxeon benchmark --ablation

# 5. Comparativa cuantitativa frente a línea base sin supervisor
uv run praxeon benchmark --compare-v1

# 6. Exportar reporte de auditoría a JSON
uv run praxeon benchmark --output auditoria_report.json
```

### B. Dashboard TUI en Vivo (`praxeon-dash` / `praxeon dashboard`)
Monitor visual interactivo en terminal con 3 paneles sincronizados en tiempo real:
```bash
# Modo demostración interactiva
uv run praxeon-dash

# Modo vivo conectando el agente LLM real
uv run praxeon-dash --live --model gemini-3.6-flash --max-steps 25
```

| Parámetro | Tipo | Por defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--live` | `flag` | `False` | Conecta el agente LLM real en vivo. |
| `--task` | `string` | `None` | Objetivo o tarea inicial a resolver. |
| `--model` | `string` | `gemini-3.6-flash` | Modelo de Gemini para la ejecución. |
| `--max-steps` | `int` | `25` | Límite máximo de turnos permitidos. |
| `--once` | `flag` | `False` | Ejecuta una única tarea y finaliza. |

### C. Agente Autónomo Interactivo (`praxeon-live`)
```bash
# Modo continuo interactivo
uv run praxeon-live

# Ejecutar una tarea puntual con modelo específico
uv run praxeon-live "Corregir función en parser.py" --model gemini-2.5-flash --once --steps 20
```

---

## 8. Servidor MCP (Model Context Protocol)

`PRAXEON` incluye un servidor MCP compatible con clientes como **Antigravity IDE**, **Claude Desktop** y **Cursor**:

```json
{
  "mcpServers": {
    "praxeon": {
      "command": "uv",
      "args": ["run", "praxeon-mcp"],
      "cwd": "C:/ruta/al/proyecto/praxeon"
    }
  }
}
```

### Herramientas MCP Nativas de Sesión y Runtime:
- `jev_v2_start_session(goal, session_id)`: Inicializa una sesión formal con objetivo y checkpoint génesis.
- `jev_v2_evaluate_action(action, goal, session_id)`: Evalúa una acción candidata a través de todo el pipeline emitiendo decisión operacional y capability/recibo auditable.
- `jev_v2_step_and_execute(action, auto_checkpoint)`: Evalúa y ejecuta físicamente en sandbox con captura de observación, auto-checkpoint y actualización de evidencia.
- `jev_v2_rollback(checkpoint_id, culprit_tool, reason)`: Restaura el estado al último checkpoint e invalida la herramienta reincidente.
- `jev_v2_get_session_state()`: Devuelve el snapshot serializado del estado y su SHA-256 canónico.
- `jev_v2_confirm_action(action_id)`: Registra la confirmación humana explícita para desbloquear acciones con `requires_confirmation=True`.

### Herramientas MCP de Intercepción Rápida de Traza:
- `jev_evaluate_next_step`: Evaluación reactiva de siguiente paso.
- `jev_evaluate_step_chunk`: Evaluación de bloques candidatos de 3-4 pasos.
- `jev_diagnose_trace`: Diagnóstico de traza completa de razonamiento.

---

## 9. Uso Programático en Python (v0.4)

```python
from praxeon.domain import Goal, ActionCandidate, ToolCall
from praxeon.providers import LayaProvider, TypeSafeAdapter
from praxeon.runtime import Navigator, SecureExecutor

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

## 10. Verificación de la Suite de Pruebas e Invariantes
 
Toda la arquitectura de PRAXEON v0.4, los contratos formales de proveedores (`LayaProvider`, `TypeSafeAdapter`, `ReplayProvider`, `ConfidenceAwareRouter`), el acotamiento de contexto, las barreras de enforcement físico y la suite de evaluación multidimensional están respaldadas por **199 pruebas automatizadas al 100%**:
 
```bash
pytest -q
# .........s.............................................................. [ 36%]
# ........................................................................ [ 72%]
# ........................................................                 [100%]
# 199 passed, 1 skipped in 43.14s
```
 
---
 
## 11. Capacidades Avanzadas de Runtime y Gobernanza (v0.4)

- **Proveedor LAYA con Primitivas System-1 (`LayaProvider`)**:
  Inferencia probabilística desacoplada que calcula veredictos de clasificación (`choice`), estimación continua de avance (`score`), y probabilidades calibradas de bucle y fundamentación (`noul`). Soporta modos `local` (pesos de red locales con descarga automática de Hugging Face), `hosted` (vía HTTP/RPC), `simulated` (determinista para test/CI sin descarga) y selección automática `auto`, exponiendo metadatos completos de telemetría y reproducibilidad (`latency_ms`, `context_tokens`, `device`, `checkpoint_version`).
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

## 12. Suite de Evaluación Multidimensional

El módulo `praxeon.evaluation` implementa una batería completa y desacoplada de benchmarks para medir exhaustivamente la calidad de decisión, resistencia física y rendimiento del supervisor:

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
   - *Config 5: PRAXEON Completo Single-Tier*
   - *Config 6: Confidence-Aware Cascade Router (JEV + LAYA Handoff)*
   - Cada configuración computa automáticamente métricas de clasificación, seguridad física y valor económico neto ($\text{NavigatorValue}$).

---

## 13. Limitaciones Actuales y Alcance Técnico

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


