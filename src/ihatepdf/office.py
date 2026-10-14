"""Office conversion through Microsoft PowerPoint or LibreOffice."""

from pathlib import Path
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

from .core import open_pdf
from .output import atomic_write, validate_outputs

WORD_EXTENSIONS = {".doc", ".docx", ".odt", ".rtf"}
PPT_EXTENSIONS = {".ppt", ".pptx", ".odp"}
OFFICE_EXTENSIONS = WORD_EXTENSIONS | PPT_EXTENSIONS | {".xls", ".xlsx", ".ods"}
NATIVE_PPT_EXTENSIONS = {".ppt", ".pptx"}


def powerpoint_available() -> bool:
    """Detect registration and the Python bridge without launching PowerPoint."""
    if sys.platform != "win32" or importlib.util.find_spec("win32com") is None:
        return False
    import winreg
    for view in (0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"PowerPoint.Application\CLSID", 0, winreg.KEY_READ | view):
                return True
        except OSError:
            continue
    return False


def conversion_status() -> dict[str, bool]:
    try:
        libreoffice = bool(find_libreoffice())
    except ValueError:
        libreoffice = False
    return dict(libreoffice=libreoffice, powerpoint=powerpoint_available())


def powerpoint_to_pdf(input: Path, output: Path, *, timeout=120, force=False) -> None:
    if input.suffix.lower() not in NATIVE_PPT_EXTENSIONS:
        raise ValueError("Microsoft PowerPoint conversion supports PPT and PPTX files.")
    validate_outputs([output], [input], force)
    with tempfile.TemporaryDirectory(prefix="ihatepdf-powerpoint-") as directory:
        work = Path(directory)
        local_input = work / ("document" + input.suffix.lower())
        shutil.copy2(input, local_input)
        converted = work / "document.pdf"
        environment = os.environ.copy()
        # run.py works without an editable installation; propagate its source
        # path so the private subprocess works in that setup as well.
        source_root = str(Path(__file__).resolve().parents[1])
        environment["PYTHONPATH"] = source_root + os.pathsep + environment.get("PYTHONPATH", "")
        command = [sys.executable, "-m", "ihatepdf._powerpoint", str(local_input), str(converted)]
        try:
            process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                     timeout=timeout, env=environment,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as exc:
            # The Python worker is stopped, never the user's PowerPoint process.
            raise ValueError(f"PowerPoint conversion timed out after {timeout} seconds. Check PowerPoint for an open dialog, close the temporary presentation if needed, and retry.") from exc
        if process.returncode or not converted.is_file():
            try:
                detail = json.loads(process.stdout).get("error", "")
            except (json.JSONDecodeError, AttributeError):
                detail = (process.stderr or process.stdout).strip()[-1200:]
            raise ValueError(detail or "PowerPoint could not produce a PDF. Check that it is activated and opens normally.")
        with open_pdf(converted):
            pass
        atomic_write(output, lambda staged: shutil.copyfile(converted, staged), force=force)


def find_libreoffice(explicit: str | None = None) -> Path | None:
    configured = explicit or os.environ.get("IHATEPDF_LIBREOFFICE")
    if configured:
        candidate = Path(configured.strip('"')).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        found = shutil.which(configured)
        if found:
            return Path(found)
        raise ValueError(f"LibreOffice executable not found: {configured}.")
    for name in ("soffice.com", "soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return Path(found)
    for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        folder = os.environ.get(env_name)
        if folder:
            for name in ("soffice.com", "soffice.exe"):
                candidate = Path(folder) / "LibreOffice" / "program" / name
                if candidate.is_file():
                    return candidate
    return None


def office_to_pdf(input: Path, output: Path, *, kind="office-to-pdf", executable=None,
                  timeout=120, force=False) -> None:
    extensions = WORD_EXTENSIONS if kind == "word-to-pdf" else PPT_EXTENSIONS if kind == "ppt-to-pdf" else OFFICE_EXTENSIONS
    if input.suffix.lower() not in extensions:
        raise ValueError(f"Unsupported file for {kind}: {input.suffix}. Expected {', '.join(sorted(extensions))}.")
    if not input.is_file():
        raise ValueError(f"Input file not found: {input}.")
    if timeout <= 0:
        raise ValueError("Conversion timeout must be positive.")
    validate_outputs([output], [input], force)
    native_error = None
    if input.suffix.lower() in NATIVE_PPT_EXTENSIONS and executable is None and powerpoint_available():
        try:
            powerpoint_to_pdf(input, output, timeout=timeout, force=force)
            return
        except (ValueError, OSError, RuntimeError) as exc:
            native_error = str(exc)
    soffice = find_libreoffice(executable)
    if soffice is None:
        if native_error:
            raise ValueError(native_error)
        if input.suffix.lower() in NATIVE_PPT_EXTENSIONS:
            raise ValueError("PPT/PPTX conversion needs Microsoft PowerPoint on Windows or LibreOffice. Install either, then restart this app.")
        raise ValueError("LibreOffice is required for Office conversion. Install LibreOffice and restart this app.")
    with tempfile.TemporaryDirectory(prefix="ihatepdf-office-") as directory:
        work = Path(directory)
        profile = (work / "profile").as_uri()
        # Work from a private copy so output naming is deterministic even for unusual input paths.
        local_input = work / ("document" + input.suffix.lower())
        shutil.copy2(input, local_input)
        filter_name = "writer_pdf_Export" if input.suffix.lower() in WORD_EXTENSIONS else "impress_pdf_Export" if input.suffix.lower() in PPT_EXTENSIONS else "calc_pdf_Export"
        command = [str(soffice), f"-env:UserInstallation={profile}", "--headless", "--nologo",
                   "--nodefault", "--nofirststartwizard", "--convert-to", f"pdf:{filter_name}",
                   "--outdir", str(work), str(local_input)]
        try:
            process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                     errors="replace", timeout=timeout,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"LibreOffice conversion timed out after {timeout} seconds.") from exc
        converted = work / "document.pdf"
        if process.returncode or not converted.is_file():
            detail = (process.stderr or process.stdout).strip()[-1200:]
            raise ValueError(f"LibreOffice could not convert {input.name}. {detail}")
        # LibreOffice sometimes returns success even if it failed; validate the actual PDF.
        with open_pdf(converted):
            pass
        atomic_write(output, lambda staged: shutil.copyfile(converted, staged), force=force)

