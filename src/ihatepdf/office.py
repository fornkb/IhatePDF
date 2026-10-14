"""Optional Office conversion using a locally installed LibreOffice."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from .core import open_pdf
from .output import atomic_write, validate_outputs

WORD_EXTENSIONS = {".doc", ".docx", ".odt", ".rtf"}
PPT_EXTENSIONS = {".ppt", ".pptx", ".odp"}
OFFICE_EXTENSIONS = WORD_EXTENSIONS | PPT_EXTENSIONS | {".xls", ".xlsx", ".ods"}


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
    soffice = find_libreoffice(executable)
    if soffice is None:
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

