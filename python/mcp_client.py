"""
mcp_client.py — TradingView MCP Client
=======================================
Reusable client for communicating with the TradingView MCP server.
Handles the MCP protocol handshake (initialize → notifications/initialized)
and provides a simple call() interface for any MCP tool.

Used by:
  - scripts/setup_tradingview_indicators.py (chart setup)
  - aurum.py (AURUM AI agent — live chart interaction)
  - lens.py (could migrate to this in future)
"""

import os, json, logging, subprocess, shutil, time, shlex

log = logging.getLogger("mcp_client")

_PY = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_PY, ".."))

MCP_SERVER_CMD = os.environ.get(
    "LENS_MCP_CMD",
    "npx tradingview-mcp-jackson"
)


def _mcp_argv() -> list:
    """Resolve the MCP server command to absolute paths."""
    cmd = (MCP_SERVER_CMD or "").strip().strip('"').strip("'")
    parts = shlex.split(cmd)
    if not parts:
        return parts
    exe = shutil.which(parts[0]) or parts[0]
    return [exe] + parts[1:]


class MCPSession:
    """A persistent MCP session — keeps the server process alive for multiple calls."""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.proc = None
        self._initialized = False
        self._id_counter = 0

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def start(self):
        """Spawn the MCP server and perform the protocol handshake."""
        self.proc = subprocess.Popen(
            _mcp_argv(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy(),
        )
        # Initialize handshake
        self._send({
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "signal_system", "version": "1.0"},
            },
        })
        init_resp = self._read_response()
        if not init_resp or "result" not in init_resp:
            raise ConnectionError("MCP server failed to initialize")

        # Send initialized notification
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        time.sleep(0.5)
        self._initialized = True
        log.debug("MCP session initialized")

    def close(self):
        """Kill the MCP server process."""
        if self.proc:
            try:
                self.proc.kill()
                self.proc.wait(timeout=3)
            except Exception:
                pass
            self.proc = None
        self._initialized = False

    def call(self, tool: str, arguments: dict = None) -> dict:
        """Call an MCP tool and return the parsed result.

        Returns the parsed JSON from the tool's text content block,
        or an empty dict if the call fails.
        """
        if not self._initialized:
            raise RuntimeError("MCP session not initialized — call start() first")

        self._id_counter += 1
        self._send({
            "jsonrpc": "2.0",
            "id": self._id_counter,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments or {}},
        })

        resp = self._read_response()
        if not resp or "result" not in resp:
            return {}

        for block in resp["result"].get("content", []):
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (json.JSONDecodeError, TypeError):
                    return {"raw_text": block["text"]}
        return resp.get("result", {})

    def _send(self, obj: dict):
        self.proc.stdin.write((json.dumps(obj) + "\n").encode())
        self.proc.stdin.flush()

    def _read_response(self, timeout: int = None) -> dict | None:
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                continue
            line = line.decode("utf-8", errors="ignore").strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None


def quick_call(tool: str, arguments: dict = None, timeout: int = 20) -> dict:
    """One-shot: spawn server, init, call one tool, kill.

    Convenient for scripts that only need a single MCP call.
    For multiple calls, use MCPSession as a context manager.
    """
    with MCPSession(timeout=timeout) as session:
        return session.call(tool, arguments)
