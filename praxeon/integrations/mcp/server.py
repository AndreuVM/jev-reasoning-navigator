"""Servidor Model Context Protocol (MCP) para integración formal v0.2.1.

Expone las herramientas y diagnósticos de supervisión cognitiva de JEV Reasoning Navigator:
- jev_v2_start_session
- jev_v2_evaluate_action
- jev_v2_step_and_execute
- jev_v2_rollback
- jev_v2_get_session_state
- jev_v2_confirm_action
- jev_evaluate_next_step (compatibilidad v0.1)
- jev_evaluate_step_chunk (compatibilidad v0.1)
- jev_diagnose_trace (compatibilidad v0.1)
"""

import sys
from typing import Optional

from praxeon.config import JEVConfig, default_config
from praxeon.interceptor.mcp_bridge import MCPBridge
from praxeon.runtime.navigator import Navigator


class MCPServer(MCPBridge):
    """Servidor MCP formal bajo la topología de integraciones v0.2."""

    def __init__(
        self,
        config: Optional[JEVConfig] = None,
        navigator: Optional[Navigator] = None,
    ):
        super().__init__(config=config, navigator=navigator)


def main() -> None:
    """Punto de entrada CLI para ejecutar el servidor MCP sobre stdio."""
    server = MCPServer()
    server.run_stdio_server()


if __name__ == "__main__":
    main()
