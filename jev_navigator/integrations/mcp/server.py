"""Servidor Model Context Protocol (MCP) para integración formal v0.2.

Expone las herramientas y diagnósticos de supervisión cognitiva de JEV Reasoning Navigator:
- jev_evaluate_next_step
- jev_evaluate_step_chunk
- jev_diagnose_trace
- jev_checkpoint_rollback
- jev_get_receipts
"""

import sys
from typing import Optional

from jev_navigator.config import JEVConfig, default_config
from jev_navigator.interceptor.mcp_bridge import MCPBridge
from jev_navigator.runtime.navigator import Navigator


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
