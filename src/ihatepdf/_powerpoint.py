"""Private subprocess worker for PowerPoint's native PDF export on Windows."""

from pathlib import Path
import json
import sys


def export_pdf(source: Path, output: Path) -> None:
    import pythoncom
    from win32com.client import dynamic

    pythoncom.CoInitialize()
    application = presentation = None
    try:
        # PowerPoint is a single-instance COM server. Never quit the application:
        # it may be the user's existing session, even when obtained via Dispatch.
        application = dynamic.Dispatch("PowerPoint.Application")
        previous_security = application.AutomationSecurity
        try:
            application.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
            presentation = application.Presentations.Open(str(source.resolve()), -1, 0, 0)
        finally:
            application.AutomationSecurity = previous_security
        # PDF, print quality, slides, all pages, no hidden slides. PrintRange
        # must explicitly be None rather than a missing optional COM argument.
        presentation.ExportAsFixedFormat(str(output.resolve()), 2, 2, 0, 1, 1, 0,
                                         None, 1, "", True, True, True, True, False)
    finally:
        try:
            if presentation is not None:
                presentation.Close()
        finally:
            presentation = application = None
            pythoncom.CoUninitialize()


def main() -> int:
    if len(sys.argv) != 3:
        print(json.dumps({"error": "Invalid PowerPoint conversion request."}))
        return 1
    try:
        export_pdf(Path(sys.argv[1]), Path(sys.argv[2]))
        return 0
    except Exception as exc:
        # Return a concise message to the parent without a traceback.
        details = getattr(exc, "excepinfo", None)
        message = details[2] if details and len(details) > 2 and details[2] else str(exc)
        print(json.dumps({"error": f"PowerPoint could not convert this presentation. {message}"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

