import os
import sys
import time
import socket
import signal
import subprocess
from pathlib import Path


def _find_free_port() -> int:
    """Find an available TCP port by binding to 0 and reading the assigned port.

    Note: There's a tiny race between closing this socket and the server binding,
    but for local tests it's acceptable and avoids hard-coding 5000.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_lines(proc: subprocess.Popen, phrases: list[str], timeout: float = 5.0) -> str:
    """Read stdout until all phrases appear or timeout expires.

    Returns the captured output so far for assertions/debugging.
    """
    start = time.time()
    captured: list[str] = []
    # Ensure non-blocking line reads; Python's -u flag handles flush on the child
    while proc.poll() is None and (time.time() - start) < timeout:
        line = proc.stdout.readline() if proc.stdout else b""
        if not line:
            # Give the child a tiny breather
            time.sleep(0.05)
            continue
        try:
            text = line.decode(errors="replace")
        except Exception:
            text = str(line)
        captured.append(text)
        if all(p in "".join(captured) for p in phrases):
            break
    return "".join(captured)


def _terminate_process(proc: subprocess.Popen, wait: float = 5.0) -> None:
    """Terminate the server process, then force-kill if it doesn't exit quickly.

    We avoid leaving the socket bound between tests and keep CI clean.
    """
    if proc.poll() is None:
        # Try a soft interrupt first so Flask-SocketIO/Werkzeug can clean up
        try:
            if os.name == "nt":
                # Send CTRL+BREAK to the new process group (requires CREATE_NEW_PROCESS_GROUP on spawn)
                proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                proc.send_signal(signal.SIGINT)
        except Exception:
            pass
        # Wait a bit for graceful shutdown
        try:
            proc.wait(timeout=wait)
        except Exception:
            # Fall back to terminate/kill
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def test_server_starts_and_exits_cleanly(tmp_path: Path):
    """Launch server.py on a free port, verify startup messages, then stop it.

    This test ensures the server boots without binding conflicts and that we
    cleanly terminate it after ~5 seconds to avoid leaving a stray listener
    (which would cause subsequent runs to fail).
    """
    repo_root = Path(__file__).resolve().parents[1]
    server_py = repo_root / "server" / "server.py"
    assert server_py.exists(), f"Missing server.py at {server_py}"

    port = _find_free_port()

    env = os.environ.copy()
    # Force non-interactive, disable AI prompt, and bind a free port
    env["MUD_NO_INTERACTIVE"] = "1"
    env["GEMINI_NO_PROMPT"] = "1"
    env["CI"] = env.get("CI", "true")  # hint to skip any prompts
    env["HOST"] = "127.0.0.1"
    env["PORT"] = str(port)

    # Use the current Python interpreter; -u for unbuffered stdout
    cmd = [sys.executable, "-u", str(server_py)]

    # Start process with stdout captured; use repo root as CWD
    creationflags = 0
    if os.name == "nt":
        # Needed so we can send CTRL_BREAK_EVENT to the child process group
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    proc = subprocess.Popen(
        cmd,
        cwd=str(repo_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
        creationflags=creationflags,
    )

    try:
        # Wait up to ~5 seconds for clear startup prints
        output = _wait_for_lines(proc, ["AI MUD Server Starting", "Listening on:"], timeout=5.0)
        # Even if we time out, we still proceed to terminate to avoid stranding the process
        assert "AI MUD Server Starting" in output, f"Startup banner missing. Output was:\n{output}"
        assert "Listening on:" in output, f"Listening line missing. Output was:\n{output}"
    finally:
        _terminate_process(proc)

    # Ensure the process is gone; avoid immediate port rebind on Windows (TIME_WAIT is expected)
    assert proc.poll() is not None, "Server process did not exit after termination attempts"
