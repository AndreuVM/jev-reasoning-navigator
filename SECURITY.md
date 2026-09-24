# Política de Seguridad y Modelo de Amenazas: JEV Reasoning Navigator

## 1. Versiones Soportadas

| Versión | Soportada | Estado de Mantenimiento |
| :--- | :---: | :--- |
| **0.2.x (v0.2.1)** | ✅ Sí | Versión activa principal con enforcement formal, capabilities criptográficos y sandboxing. |
| 0.1.x | ❌ No | Deprecada. Se recomienda migrar inmediatamente a la arquitectura desacoplada v0.2. |

---

## 2. Modelo de Amenazas y Filosofía de Defensa en Profundidad

JEV Reasoning Navigator asume un entorno de adversarios hostiles donde el modelo de lenguaje (LLM) está sujeto a:
- **Inyección indirecta de prompts** a través de observaciones del entorno (archivos, páginas web, APIs externas).
- **Alucinación de herramientas y parámetros** (invocaciones no fundamentadas empíricamente).
- **Tentativas de manipulación de estado o replay attacks** (reutilización de autorizaciones pasadas).
- **Evasión de límites del filesystem y ejecución arbitraria en el host**.

Para mitigar estas amenazas, el runtime establece una **cadena formal de custodia de autorización**:

$$\text{LLM Proposal} \to \text{Evidence Grounding} \to \text{Risk Assessment} \to \text{PolicyEngine} \to \text{Bound DecisionCapability} \to \text{SecureExecutor} \to \text{Process Sandbox} \to \text{OS}$$

### Principios Fundamentales:
1. **Separación de Responsabilidades:**
   $$\text{Semantic Judgment (JEV)} \neq \text{Operational Policy (PolicyEngine)} \neq \text{Physical Execution (SecureExecutor)}$$
2. **Capabilidades Ligadas Criptográficamente (DecisionReceipt):**
   `SecureExecutor` no ejecuta ninguna herramienta física sin recibir un capability emitido por la `PolicyEngine` con:
   - `decision_status == ALLOW`
   - `action_hash == SHA256(action)`
   - `state_hash == SHA256(state)`
   - `session_id == active_session_id`
   - `nonce` no consumido previamente (prevención estricta de replay attacks).
3. **Aislamiento en Sandbox (`SandboxAdapter`):**
   - **Depuración de Entorno:** Las variables sensibles (`TYPESAFE_API_KEY`, `GEMINI_API_KEY`, tokens y contraseñas) son purgadas del entorno del proceso hijo antes de cualquier ejecución.
   - **Contención de Directorio (Jail Path):** Las rutas de archivos y comandos son forzadas a resolverse dentro del workspace delimitado, bloqueando accesos por traversals (`../`).
   - **Prevención de Inyección Shell:** Ejecución sin `shell=True` arbitrario y con timeouts forzados.
4. **Sanitización de Salidas (`DataSanitizer`):**
   Las observaciones retornadas por las herramientas son analizadas y enmascaradas (eliminando credenciales, tokens JWT y claves privadas) y envueltas en delimitadores de confianza antes de ser inyectadas en la memoria del agente.

---

## 3. Reporte Responsable de Vulnerabilidades

Agradecemos y valoramos el trabajo de los investigadores de seguridad. Si descubres una vulnerabilidad potencial en JEV Reasoning Navigator:

1. **NO abras una issue pública** en GitHub.
2. Envía un reporte detallado con los pasos para reproducir la vulnerabilidad a través de la pestaña **Security Advisories** de GitHub:
   [https://github.com/AndreuVM/jev-reasoning-navigator/security/advisories/new](https://github.com/AndreuVM/jev-reasoning-navigator/security/advisories/new)
3. Proporciona:
   - Descripción del vector de ataque y componente afectado (`SecureExecutor`, `PolicyEngine`, `SandboxAdapter`, `MCP`, etc.).
   - Prueba de concepto (PoC) ejecutable o traza reproducible.
   - Impacto estimado y posibles mitigaciones.

### Compromiso de Respuesta:
- **Acuse de recibo inicial:** En menos de 48 horas laborables.
- **Evaluación y parche de seguridad:** En un plazo máximo de 14 días.
