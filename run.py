"""Launch the IhatePDF web interface with: python run.py."""

from pathlib import Path
import subprocess
import sys


def main() -> int:
    project = Path(__file__).resolve().parent
    # Reuse the installed project environment without requiring activation.
    local_python = project / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if local_python.is_file() and Path(sys.executable).absolute() != local_python.absolute():
        child = subprocess.Popen([str(local_python), str(Path(__file__).resolve()), *sys.argv[1:]])
        try:
            return child.wait()
        except KeyboardInterrupt:
            if sys.platform == "win32":
                # Windows venv python.exe is a launcher with an interpreter child.
                # Stopping only that launcher leaves the actual web server alive.
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=10)
            else:
                child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            return 130
    sys.path.insert(0, str(project / "src"))
    try:
        from ihatepdf.server import main as start_server
    except ModuleNotFoundError as exc:
        if exc.name not in {"pymupdf", "PIL", "flask"}:
            raise
        print("IhatePDF dependencies are missing. Install them with:\n"
              f'  "{sys.executable}" -m pip install -r "{project / "requirements.txt"}"', file=sys.stderr)
        return 1
    return start_server()


if __name__ == "__main__":
    raise SystemExit(main())

