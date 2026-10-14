from pathlib import Path
import json
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from ihatepdf import office
from ihatepdf._powerpoint import export_pdf


def test_native_powerpoint_is_preferred(sample, tmp_path, monkeypatch):
    source = tmp_path / "slides.pptx"
    source.write_bytes(b"presentation")
    output = tmp_path / "slides.pdf"
    monkeypatch.setattr(office, "powerpoint_available", lambda: True)
    def convert(input, output, **kwargs):
        assert input == source and kwargs["timeout"] == 90
        output.write_bytes(sample.read_bytes())
    monkeypatch.setattr(office, "powerpoint_to_pdf", convert)
    monkeypatch.setattr(office, "find_libreoffice", lambda *args: pytest.fail("PowerPoint success should not need LibreOffice"))
    office.office_to_pdf(source, output, kind="ppt-to-pdf", timeout=90)
    assert output.read_bytes() == sample.read_bytes()


def test_native_failure_falls_back_to_libreoffice(sample, tmp_path, monkeypatch):
    source = tmp_path / "slides.pptx"
    source.write_bytes(b"presentation")
    monkeypatch.setattr(office, "powerpoint_available", lambda: True)
    def fail(*args, **kwargs):
        raise ValueError("PowerPoint failed")
    monkeypatch.setattr(office, "powerpoint_to_pdf", fail)
    monkeypatch.setattr(office, "find_libreoffice", lambda *args: Path("soffice"))
    def convert(command, **kwargs):
        assert "--headless" in command
        work = Path(command[command.index("--outdir") + 1])
        (work / "document.pdf").write_bytes(sample.read_bytes())
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(office.subprocess, "run", convert)
    output = tmp_path / "out.pdf"
    office.office_to_pdf(source, output)
    assert output.is_file()


def test_native_error_is_preserved_without_fallback(tmp_path, monkeypatch):
    source = tmp_path / "slides.pptx"
    source.write_bytes(b"presentation")
    monkeypatch.setattr(office, "powerpoint_available", lambda: True)
    monkeypatch.setattr(office, "find_libreoffice", lambda *args: None)
    def fail(*args, **kwargs):
        raise ValueError("PowerPoint needs activation")
    monkeypatch.setattr(office, "powerpoint_to_pdf", fail)
    with pytest.raises(ValueError, match="activation"):
        office.office_to_pdf(source, tmp_path / "out.pdf")


def test_odp_still_uses_libreoffice(sample, tmp_path, monkeypatch):
    source = tmp_path / "slides.odp"
    source.write_bytes(b"presentation")
    monkeypatch.setattr(office, "powerpoint_available", lambda: True)
    monkeypatch.setattr(office, "powerpoint_to_pdf", lambda *args, **kwargs: pytest.fail("ODP should use LibreOffice"))
    monkeypatch.setattr(office, "find_libreoffice", lambda *args: None)
    with pytest.raises(ValueError, match="LibreOffice is required"):
        office.office_to_pdf(source, tmp_path / "out.pdf")


def test_native_worker_output_is_validated(sample, tmp_path, monkeypatch):
    source = tmp_path / "slides.pptx"
    source.write_bytes(b"presentation")
    def convert(command, **kwargs):
        assert command[1:3] == ["-m", "ihatepdf._powerpoint"]
        assert "PYTHONPATH" in kwargs["env"]
        Path(command[-1]).write_bytes(sample.read_bytes())
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(office.subprocess, "run", convert)
    output = tmp_path / "out.pdf"
    office.powerpoint_to_pdf(source, output)
    assert output.read_bytes() == sample.read_bytes()


def test_native_timeout_is_actionable(tmp_path, monkeypatch):
    source = tmp_path / "slides.pptx"
    source.write_bytes(b"presentation")
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 2)
    monkeypatch.setattr(office.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="open dialog"):
        office.powerpoint_to_pdf(source, tmp_path / "out.pdf", timeout=2)


@pytest.mark.parametrize("failure", [None, "open", "export"])
def test_worker_closes_its_presentation_and_restores_macro_settings(tmp_path, monkeypatch, failure):
    events = []
    presentation = SimpleNamespace(Close=lambda: events.append("close"))
    app = SimpleNamespace(AutomationSecurity=2, Quit=lambda: pytest.fail("Never quit the user's PowerPoint"))
    def open_presentation(path, readonly, untitled, window):
        assert app.AutomationSecurity == 3
        assert readonly == -1 and window == 0
        if failure == "open":
            raise RuntimeError("open failed")
        return presentation
    def export(path, format, *args):
        assert app.AutomationSecurity == 2 and format == 2
        assert args[5] is None  # Explicit PrintRange
        if failure == "export":
            raise RuntimeError("export failed")
        events.append("export")
    presentation.ExportAsFixedFormat = export
    app.Presentations = SimpleNamespace(Open=open_presentation)
    com = ModuleType("pythoncom")
    com.CoInitialize = lambda: events.append("initialize")
    com.CoUninitialize = lambda: events.append("uninitialize")
    client = ModuleType("win32com.client")
    client.dynamic = SimpleNamespace(Dispatch=lambda name: app)
    monkeypatch.setitem(sys.modules, "pythoncom", com)
    monkeypatch.setitem(sys.modules, "win32com", ModuleType("win32com"))
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    if failure:
        with pytest.raises(RuntimeError, match=f"{failure} failed"):
            export_pdf(tmp_path / "source.pptx", tmp_path / "out.pdf")
    else:
        export_pdf(tmp_path / "source.pptx", tmp_path / "out.pdf")
    if failure == "open":
        assert events == ["initialize", "uninitialize"]
    else:
        assert events[-2:] == ["close", "uninitialize"]
    assert app.AutomationSecurity == 2


def test_status_detects_engines_independently(tmp_path, monkeypatch):
    monkeypatch.setattr(office, "powerpoint_available", lambda: True)
    monkeypatch.setattr(office, "find_libreoffice", lambda *args: None)
    from ihatepdf.web import create_app
    client = create_app(tmp_path / "jobs").test_client()
    assert client.get("/api/status").json["office_backends"] == {"libreoffice": False, "powerpoint": True}
    html = client.get("/").get_data(as_text=True)
    assert '"powerpoint": true' in html

