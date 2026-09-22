# Regla de Supervisión Cognitiva con JEV-Navigator y TypeSafe AI

Esta regla instruye al agente de Antigravity para utilizar activamente el servidor MCP `jev-navigator` para prevenir alucinaciones y validar planes complejos de resolución de problemas.

## 1. Cuándo invocar JEV vía MCP (`jev-navigator`)

El agente debe invocar la herramienta MCP `jev_evaluate_step_chunk` (servidor `jev-navigator`) en los siguientes casos:
1. **Antes de ejecutar planes de más de 2 pasos** que involucren modificación de archivos, parches de código o ejecución de comandos de terminal.
2. **Ante errores recurrentes**: Si una prueba o comando falla más de una vez, empaquetar los pasos de resolución propuestos y enviarlos a `jev_evaluate_step_chunk`.
3. **Verificación de Fundamentación Empírica**: Cuando se formulen supuestos sobre la existencia de archivos o funciones, validar con JEV que la acción no sea una alucinación no fundamentada.

## 2. Parámetros de Invocación (`jev_evaluate_step_chunk`)

- `goal`: El objetivo principal o tarea actual que se está resolviendo.
- `proposed_steps`: Lista de objetos que representan los pasos que el agente planea ejecutar:
  ```json
  [
    {
      "thought_rationale": "Descripción del razonamiento del paso 1",
      "tool_name": "edit_file",
      "tool_args": {"path": "ruta/al/archivo.py", "diff": "..."}
    },
    {
      "thought_rationale": "Verificar compilación o pruebas",
      "tool_name": "run_command",
      "tool_args": {"command": "pytest"}
    }
  ]
  ```

## 3. Manejo de la Respuesta de JEV

- **Si `all_safe: true`**: Proceder con confianza a ejecutar las herramientas del bloque.
- **Si `all_safe: false`**: 
  - Leer inmediatamente la `directive` y `explanation` devuelta por TypeSafe AI.
  - Abortar la acción en el índice `flagged_step_index`.
  - Aplicar la instrucción correctiva (poda, retroceso o verificación empírica) antes de proponer cualquier otra acción.
