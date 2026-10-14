"""Launch the IhatePDF web interface with: python run.py."""

from pathlib import Path
import subprocess
import sys


def main() -> int:
    project = Path(__file__).resolve().parent
    # Reuse the installed project environment without requiring activation.
    local_python = project / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if local_python.is_file() and Path(sys.executable).absolute() != local_python.absolute():
        try:
            return subprocess.call([str(local_python), str(Path(__file__).resolve()), *sys.argv[1:]])
        except KeyboardInterrupt:
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

