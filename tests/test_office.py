from pathlib import Path
import subprocess

import pytest

from ihatepdf import office


@pytest.fixture(autouse=True)
def no_native_powerpoint(monkeypatch):
    # Unit tests never open the user's desktop PowerPoint.
    monkeypatch.setattr(office, "powerpoint_available", lambda: False)


def test_missing_libreoffice_is_actionable(tmp_path, monkeypatch):
    monkeypatch.setattr(office, "find_libreoffice", lambda explicit=None: None)
    input = tmp_path / "report.docx"
    input.write_bytes(b"document")
    with pytest.raises(ValueError, match="LibreOffice is required"):
        office.office_to_pdf(input, tmp_path / "report.pdf")


@pytest.mark.parametrize("kind,extension,filter_name", [
    ("word-to-pdf", ".docx", "writer_pdf_Export"),
    ("word-to-pdf", ".doc", "writer_pdf_Export"),
    ("ppt-to-pdf", ".pptx", "impress_pdf_Export"),
    ("ppt-to-pdf", ".ppt", "impress_pdf_Export"),
    ("office-to-pdf", ".xlsx", "calc_pdf_Export"),
])
def test_office_process_and_validated_output(sample, tmp_path, monkeypatch, kind, extension, filter_name):
    input = tmp_path / ("office input" + extension)
    input.write_bytes(b"document")
    output = tmp_path / "converted.pdf"
    monkeypatch.setattr(office, "find_libreoffice", lambda explicit=None: Path("soffice"))
    def run(command, **options):
        assert "--headless" in command
        assert f"pdf:{filter_name}" in command
        assert any(value.startswith("-env:UserInstallation=file:") for value in command)
        assert options["timeout"] == 120
        work = Path(command[command.index("--outdir") + 1])
        (work / "document.pdf").write_bytes(sample.read_bytes())
        return subprocess.CompletedProcess(command, 0, "converted", "")
    monkeypatch.setattr(office.subprocess, "run", run)
    office.office_to_pdf(input, output, kind=kind)
    assert output.read_bytes() == sample.read_bytes()


def test_office_success_without_pdf_is_rejected(tmp_path, monkeypatch):
    input = tmp_path / "broken.pptx"
    input.write_bytes(b"broken")
    monkeypatch.setattr(office, "find_libreoffice", lambda explicit=None: Path("soffice"))
    monkeypatch.setattr(office.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""))
    with pytest.raises(ValueError, match="could not convert"):
        office.office_to_pdf(input, tmp_path / "out.pdf")
    assert not (tmp_path / "out.pdf").exists()


def test_office_timeout_has_clear_error(tmp_path, monkeypatch):
    input = tmp_path / "report.docx"
    input.write_bytes(b"document")
    monkeypatch.setattr(office, "find_libreoffice", lambda explicit=None: Path("soffice"))
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 120)
    monkeypatch.setattr(office.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="timed out"):
        office.office_to_pdf(input, tmp_path / "out.pdf")


def test_explicit_executable_is_checked(tmp_path):
    with pytest.raises(ValueError, match="executable not found"):
        office.find_libreoffice(str(tmp_path / "missing.exe"))


def test_wrong_office_format_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        office.office_to_pdf(tmp_path / "slides.pptx", tmp_path / "out.pdf", kind="word-to-pdf")

