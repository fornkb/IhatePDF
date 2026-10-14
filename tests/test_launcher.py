import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace


def test_launcher_stops_windows_interpreter_tree_on_cancel(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "run.py"
    spec = importlib.util.spec_from_file_location("ihatepdf_launcher", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    # This cancellation test must work on Linux checkouts without a Windows venv.
    monkeypatch.setattr(Path, "is_file", lambda path: True)
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.setattr(launcher.sys, "executable", str(path.parent / "other-python.exe"))
    waits = 0
    def wait(**kwargs):
        nonlocal waits
        waits += 1
        if waits == 1:
            raise KeyboardInterrupt
        return 0
    child = SimpleNamespace(pid=12345, wait=wait, kill=lambda: None)
    commands = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda args: child)
    monkeypatch.setattr(launcher.subprocess, "run", lambda args, **kwargs: commands.append(args))
    assert launcher.main() == 130
    assert commands == [["taskkill", "/PID", "12345", "/T", "/F"]]


def test_local_server_does_not_reuse_windows_port():
    from ihatepdf.server import LocalServer
    assert LocalServer.allow_reuse_address is False

