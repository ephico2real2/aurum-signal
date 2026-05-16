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

import os, json, logging, select, subprocess, shutil, time, shlex

log = logging.getLogger("mcp_client")

_PY = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_PY, ".."))

MCP_SERVER_CMD = os.environ.get(
    "LENS_MCP_CMD",
    "npx tradingview-mcp-jackson"
)


class MCPTimeoutError(TimeoutError):
    """Raised when the MCP server does not produce a response in time."""


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
        read_timeout = min(timeout or self.timeout or 15, 15)
        deadline = time.time() + read_timeout
        while time.time() < deadline:
            remaining = max(0.0, deadline - time.time())
            ready, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if not ready:
                try:
                    self.proc.kill()
                finally:
                    raise MCPTimeoutError(f"MCP response timed out after {read_timeout}s")
            line = self.proc.stdout.readline()
            if not line:
                continue
            line = line.decode("utf-8", errors="ignore").strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        try:
            self.proc.kill()
        finally:
            raise MCPTimeoutError(f"MCP response timed out after {read_timeout}s")


def quick_call(tool: str, arguments: dict = None, timeout: int = 20) -> dict:
    """One-shot: spawn server, init, call one tool, kill.

    Convenient for scripts that only need a single MCP call.
    For multiple calls, use MCPSession as a context manager.
    """
    with create_session(timeout=timeout) as session:
        return session.call(tool, arguments)


# ─────────────────────────────────────────────────────────────────────────
# F5 — HTTP transport client (talks to the launchd-managed tv-mcp daemon)
#
# Same call() API as MCPSession, but uses HTTP instead of spawning a
# subprocess per Python process. The transport is selected by the
# LENS_MCP_TRANSPORT env var:
#   - LENS_MCP_TRANSPORT=stdio (default, unchanged) → MCPSession (spawn-per-Python)
#   - LENS_MCP_TRANSPORT=http  → MCPHttpSession (talks to localhost:8765/mcp)
#
# Why HTTP at all? See docs/lens/LENS_MCP_FORK_ENHACEMENT.md §"Honest payoff
# summary". The win: 1 long-lived daemon + 1 CDP attachment + 1 mutex
# serves ALL consumers; per-call latency drops from ~300ms (spawn cost)
# to ~5ms (HTTP round-trip).
# ─────────────────────────────────────────────────────────────────────────

import urllib.request
import urllib.error


class MCPHttpSession:
    """HTTP transport variant of MCPSession.

    Same call() API. Uses Streamable HTTP per MCP spec 2025-11-25
    against the launchd-managed tv-mcp daemon at MCP_HTTP_HOST:PORT.
    Session ID is established by the initialize handshake and reused
    across subsequent calls in the same Python process.
    """

    def __init__(self, base_url: str = None, timeout: int = 20):
        host = os.environ.get("MCP_HTTP_HOST", "127.0.0.1")
        port = os.environ.get("MCP_HTTP_PORT", "8765")
        path = os.environ.get("MCP_HTTP_PATH", "/mcp")
        self.base_url = base_url or os.environ.get("MCP_HTTP_URL", f"http://{host}:{port}{path}")
        self.timeout = timeout
        self.session_id = None
        self._initialized = False
        self._id_counter = 0

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def start(self):
        """Initialize handshake — gets a session ID from the response header."""
        resp = self._post({
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "signal_system", "version": "1.0"},
            },
        })
        if not resp or "result" not in resp:
            raise ConnectionError(f"MCP HTTP server failed to initialize at {self.base_url}")
        # Fire the initialized notification (sessionless follow-up)
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialized = True
        log.debug("MCP HTTP session initialized: sid=%s url=%s", self.session_id, self.base_url)

    def close(self):
        """DELETE the session per MCP spec so the server cleans up state."""
        if self.session_id:
            try:
                req = urllib.request.Request(
                    self.base_url, method="DELETE",
                    headers={"Mcp-Session-Id": self.session_id},
                )
                urllib.request.urlopen(req, timeout=2).close()
            except Exception:
                pass
        self.session_id = None
        self._initialized = False

    def call(self, tool: str, arguments: dict = None) -> dict:
        if not self._initialized:
            raise RuntimeError("MCP HTTP session not initialized — call start() first")
        self._id_counter += 1
        resp = self._post({
            "jsonrpc": "2.0",
            "id": self._id_counter,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments or {}},
        })
        if not resp or "result" not in resp:
            return {}
        for block in resp["result"].get("content", []):
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (json.JSONDecodeError, TypeError):
                    return {"raw_text": block["text"]}
        return resp.get("result", {})

    def _post(self, body: dict) -> dict | None:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(
            self.base_url, method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
        )
        try:
            response = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            # 404 = session expired — caller should re-initialize
            if e.code == 404:
                self.session_id = None
                self._initialized = False
                raise ConnectionError(f"MCP HTTP session expired/unknown (404). Re-create session.") from e
            raise
        # Capture session ID on the initialize response (header is per MCP spec)
        sid = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
        if sid and not self.session_id:
            self.session_id = sid
        # Parse SSE response — for unary calls the server sends ONE data event
        return self._parse_sse(response)

    def _parse_sse(self, response) -> dict | None:
        raw = response.read().decode("utf-8", errors="ignore")
        # SSE frames: "data: {json}\n\n" — there may be multiple events; we
        # care about the one carrying the JSON-RPC result.
        for line in raw.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                payload = line[6:]
                try:
                    return json.loads(payload)
                except json.JSONDecodeError:
                    continue
        return None


def create_session(timeout: int = 20):
    """Factory — pick the right session class based on LENS_MCP_TRANSPORT.

    Consumers (lens.py, aurum.py, scripts) call this instead of MCPSession
    directly so the transport choice is centralised. Default is stdio for
    backward compatibility; flip via LENS_MCP_TRANSPORT=http when the
    tv-mcp launchd daemon is running.
    """
    transport = (os.environ.get("LENS_MCP_TRANSPORT") or "stdio").lower()
    if transport == "http":
        return MCPHttpSession(timeout=timeout)
    return MCPSession(timeout=timeout)
