#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
SECOP II — Launcher Hibrido (GUI + MCP Server)

Modo GUI (por defecto):
    Doble clic en SECOP_Hibrido.exe
    o: SECOP_Hibrido.exe

Modo MCP Server (stdio):
    SECOP_Hibrido.exe --mcp

Modo MCP Server (SSE - HTTP):
    SECOP_Hibrido.exe --mcp-sse [PUERTO]
    (por defecto puerto 8000)

Modo MCP Server (SSE - HTTPS):
    SECOP_Hibrido.exe --mcp-sse-ssl PUERTO CRT KEY

Configuracion Claude Desktop (stdio):
    %APPDATA%\Claude\settings.json
    {
      "mcpServers": {
        "secop": {
          "command": "D:/.../dist/SECOP_Hibrido.exe",
          "args": ["--mcp"]
        }
      }
    }

Configuracion Claude Desktop (SSE HTTPS):
    %APPDATA%\Claude\settings.json
    {
      "mcpServers": {
        "secop": {
          "url": "https://localhost:8000/sse"
        }
      }
    }
"""

import sys

def run_gui():
    """Lanza la aplicacion de escritorio (tkinter)."""
    import app_secop
    app = app_secop.AppSECOP()
    app.mainloop()

def run_mcp():
    """Lanza el servidor MCP para comunicacion con LLMs via stdio."""
    import os
    os.environ["MCP_TRANSPORT"] = "stdio"
    
    import mcp_secop
    mcp_secop.mcp.run(transport="stdio")

def run_mcp_sse(port: int = 8000):
    """Lanza el servidor MCP para comunicacion con LLMs via SSE (HTTP)."""
    import mcp_secop
    mcp_secop.mcp.settings.port = port
    mcp_secop.mcp.settings.host = "127.0.0.1"
    mcp_secop.mcp.settings.log_level = "WARNING"
    mcp_secop.mcp.run(transport="sse")

def run_mcp_sse_ssl(port: int, crt_path: str, key_path: str):
    """Lanza el servidor MCP para comunicacion con LLMs via SSE (HTTPS)."""
    import anyio
    import uvicorn
    import mcp_secop

    app = mcp_secop.mcp.sse_app()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        ssl_certfile=crt_path,
        ssl_keyfile=key_path,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    anyio.run(server.serve)

def _parse_args():
    args = sys.argv[1:]
    if "--mcp" in args:
        return "stdio", None, None, None
    for i, arg in enumerate(args):
        if arg == "--mcp-sse":
            port = 8000
            if i + 1 < len(args):
                try:
                    port = int(args[i + 1])
                except ValueError:
                    pass
            return "sse", port, None, None
        if arg == "--mcp-sse-ssl":
            port = int(args[i + 1])
            crt_path = args[i + 2]
            key_path = args[i + 3]
            return "sse-ssl", port, crt_path, key_path
    return "gui", None, None, None

if __name__ == "__main__":
    mode, port, crt, key = _parse_args()
    if mode == "stdio":
        run_mcp()
    elif mode == "sse":
        run_mcp_sse(port)
    elif mode == "sse-ssl":
        run_mcp_sse_ssl(port, crt, key)
    else:
        run_gui()
