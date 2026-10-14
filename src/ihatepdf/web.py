"""Local upload -> process -> download workflow for the IhatePDF."""

from pathlib import Path
import json
import math
import secrets
import shutil
import time
from urllib.parse import urlsplit
import uuid
import zipfile

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.utils import secure_filename

from . import core
from .catalog import TOOLS, TOOL_MAP
from .office import OFFICE_EXTENSIONS, PPT_EXTENSIONS, WORD_EXTENSIONS, conversion_status, office_to_pdf

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}


def _options(tool: dict, submitted: dict) -> dict:
    if not isinstance(submitted, dict):
        raise ValueError("Settings must be an object.")
    values = {field["name"]: submitted.get(field["name"], field["default"]) for field in tool["fields"]}
    for field in tool["fields"]:
        if field.get("when") and any(str(values[key]) != expected for key, expected in field["when"].items()):
            values[field["name"]] = field["default"]
            continue
        value = values[field["name"]]
        if field["type"] == "number":
            try:
                number = float(value)
                if not math.isfinite(number) or number < field.get("min", -math.inf) or number > field.get("max", math.inf):
                    raise ValueError
                if field.get("step", 1) == 1 and not number.is_integer():
                    raise ValueError
                values[field["name"]] = int(number) if number.is_integer() else number
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Enter a valid value for {field['label'].lower()}.") from exc
        elif field["type"] == "select":
            if str(value) not in {choice[0] for choice in field["choices"]}:
                raise ValueError(f"Choose a valid {field['label'].lower()}.")
            values[field["name"]] = str(value)
        else:
            if not isinstance(value, str) or len(value) > 4000:
                raise ValueError(f"Invalid {field['label'].lower()}.")
            if field.get("required") and not value:
                raise ValueError(f"{field['label']} is required.")
    password = submitted.get("password", "")
    if not isinstance(password, str) or len(password.encode("utf-8")) > 40:
        raise ValueError("Input passwords must be at most 40 UTF-8 bytes.")
    values["password"] = password or None
    return values


def _save_upload(upload, folder: Path, extensions: set[str]) -> Path:
    filename = secure_filename(upload.filename or "")
    if not filename or Path(filename).suffix.lower() not in extensions:
        raise ValueError(f"Choose a supported file ({', '.join(sorted(extensions))}).")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    upload.save(path)
    if path.stat().st_size == 0:
        raise ValueError(f"{filename} is empty.")
    return path


def _process_one(tool, source, folder, settings, image=None, font=None):
    id = tool["id"]
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / f"{source.stem}_{id.replace('-', '_')}{'.txt' if id == 'text' else '.json' if id == 'inspect' else '.pdf'}"
    common = dict(password=settings["password"])
    notes = []
    details = None
    if id in {"extract", "delete", "reorder", "rotate", "crop"}:
        core.edit_pages(source, output, id, settings.get("pages", "all"), **common,
                        angle=int(settings.get("angle", 90)), margins=tuple(settings.get(side, 0) for side in ("left", "top", "right", "bottom")))
    elif id == "split":
        mode = settings["split_mode"]
        return core.split(source, folder, ranges=settings["ranges"] if mode == "ranges" else None,
                          every=settings["every"] if mode == "chunks" else 1, **common), notes, details
    elif id == "pdf-to-images":
        return core.pdf_to_images(source, folder, pages=settings["pages"], image_format=settings["image_format"],
                                  dpi=settings["dpi"], quality=settings["quality"], **common), notes, details
    elif id == "text":
        if not core.extract_text(source, output, pages=settings["pages"], **common):
            notes.append(f"{source.name}: no extractable text was found.")
    elif id == "compress":
        before, after = core.compress(source, output, quality=settings["quality"] if settings["compression"] == "lossy" else None,
                                     dpi=settings["dpi"], **common)
        notes.append(f"{source.name}: {before:,} → {after:,} bytes ({(1 - after / before) * 100:.1f}% smaller).")
    elif id == "encrypt":
        if settings["new_password"] != settings["confirm_password"]:
            raise ValueError("The new passwords do not match.")
        core.protect(source, output, new_password=settings["new_password"], owner_password=settings["owner_password"] or None, **common)
    elif id == "unlock":
        core.unlock(source, output, **common)
    elif id == "watermark":
        core.watermark(source, output, text=settings["text"] if settings["watermark_type"] == "text" else None,
                       image=image if settings["watermark_type"] == "image" else None, pages=settings["pages"],
                       opacity=settings["opacity"], font_size=settings["font_size"], font_file=font, **common)
    elif id == "number":
        core.number_pages(source, output, pages=settings["pages"], start=settings["start"], position=settings["position"],
                          template=settings["template"], font_size=settings["font_size"], font_file=font, **common)
    elif tool.get("office"):
        office_to_pdf(source, output, kind=id, timeout=settings["timeout"])
    elif id == "inspect":
        details = core.inspect_pdf(source, settings["password"])
        details["file"] = source.name
        output.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    return [output], notes, details


def create_app(work_root: Path | None = None) -> Flask:
    app = Flask(__name__)
    root = (work_root or Path(__file__).resolve().parents[2] / "tmp" / "web-jobs").resolve()
    root.mkdir(parents=True, exist_ok=True)
    app.config.update(MAX_CONTENT_LENGTH=256 * 1024 * 1024, TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"],
                      WORK_ROOT=root, CSRF_TOKEN=secrets.token_urlsafe(32), JOB_TTL=3600)
    jobs = {}
    app.extensions["pdf_jobs"] = jobs

    def remove_job(path):
        resolved = path.resolve()
        if resolved.parent != root or not resolved.name.isalnum():
            raise ValueError("Invalid temporary job path.")
        shutil.rmtree(resolved, ignore_errors=True)

    def cleanup():
        now = time.time()
        for id, job in list(jobs.items()):
            if now - job["created"] > app.config["JOB_TTL"]:
                remove_job(job["path"])
                del jobs[id]

    @app.before_request
    def protect_local_requests():
        cleanup()
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and urlsplit(origin).netloc != request.host:
                abort(403, "Refresh this page and try again.")
            token = request.headers.get("X-IhatePDF-Token", "")
            if not secrets.compare_digest(token.encode(), app.config["CSRF_TOKEN"].encode()):
                abort(403, "Refresh this page and try again.")

    @app.after_request
    def response_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        return response

    @app.get("/")
    def index():
        return render_template("index.html", tools=TOOLS, token=app.config["CSRF_TOKEN"], office_backends=conversion_status())

    @app.get("/api/status")
    def status():
        backends = conversion_status()
        return jsonify(office_ready=backends["libreoffice"], office_backends=backends, tools=len(TOOLS))

    @app.post("/api/process")
    def process():
        id = uuid.uuid4().hex
        path = root / id
        try:
            tool = TOOL_MAP.get(request.form.get("tool"))
            if tool is None:
                raise ValueError("Choose a tool first.")
            try:
                submitted = json.loads(request.form.get("options", "{}"))
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid settings.") from exc
            settings = _options(tool, submitted)
            uploads = [file for file in request.files.getlist("files") if file.filename]
            if not 1 <= len(uploads) <= 100:
                raise ValueError("Choose between 1 and 100 input files.")
            kind = tool.get("input", "pdf")
            extensions = {"pdf": {".pdf"}, "images": IMAGE_EXTENSIONS, "word": WORD_EXTENSIONS,
                          "ppt": PPT_EXTENSIONS, "office": OFFICE_EXTENSIONS}[kind]
            inputs = [_save_upload(upload, path / "inputs" / f"{number:03}", extensions) for number, upload in enumerate(uploads, 1)]
            image = font = None
            if tool["id"] == "watermark" and settings["watermark_type"] == "image":
                if "watermark_image" not in request.files:
                    raise ValueError("Choose a watermark image.")
                image = _save_upload(request.files["watermark_image"], path / "watermark", IMAGE_EXTENSIONS)
            if tool["id"] in {"watermark", "number"} and request.files.get("font") and request.files["font"].filename:
                font = _save_upload(request.files["font"], path / "font", {".ttf", ".otf"})
            outputs, notes, details, failures = [], [], [], []
            output_root = path / "results"
            output_root.mkdir(parents=True)
            if tool.get("combine"):
                output = output_root / ("merged.pdf" if tool["id"] == "merge" else "images.pdf")
                if tool["id"] == "merge":
                    core.merge(inputs, output, settings["password"])
                else:
                    core.images_to_pdf(inputs, output, page_size=settings["page_size"], dpi=settings["dpi"])
                outputs.append(output)
            else:
                for number, source in enumerate(inputs, 1):
                    folder = output_root / f"{number:03}_{source.stem}" if len(inputs) > 1 else output_root
                    try:
                        generated, item_notes, info = _process_one(tool, source, folder, settings, image, font)
                        outputs.extend(generated)
                        notes.extend(item_notes)
                        if info:
                            details.append(info)
                    except (ValueError, OSError, RuntimeError) as exc:
                        failures.append(f"{source.name}: {exc}")
            if not outputs:
                raise ValueError("\n".join(failures) or "No files were produced.")
            # Inputs and passwords are never retained in the result record.
            for folder in (path / "inputs", path / "watermark", path / "font"):
                if folder.exists():
                    shutil.rmtree(folder)
            archive = path / "results.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for output in outputs:
                    bundle.write(output, output.relative_to(output_root).as_posix())
            jobs[id] = dict(path=path, files=outputs, archive=archive, created=time.time())
            return jsonify(job=id, files=[dict(name=output.name, size=output.stat().st_size, url=f"/download/{id}/{number}")
                                         for number, output in enumerate(outputs)], archive=f"/download/{id}/all",
                           notes=notes, errors=failures, details=details)
        except (ValueError, OSError, RuntimeError) as exc:
            if path.exists():
                remove_job(path)
            return jsonify(error=str(exc)), 400
        except HTTPException:
            if path.exists():
                remove_job(path)
            raise
        except Exception:
            if path.exists():
                remove_job(path)
            app.logger.exception("PDF processing failed")
            return jsonify(error="This file could not be processed. Check the file and try again."), 500

    @app.get("/download/<id>/<int:index>")
    def download(id, index):
        job = jobs.get(id)
        if job is None or not 0 <= index < len(job["files"]):
            abort(404, "This download has expired. Process the file again.")
        return send_file(job["files"][index], as_attachment=True, download_name=job["files"][index].name)

    @app.get("/download/<id>/all")
    def download_all(id):
        job = jobs.get(id)
        if job is None:
            abort(404, "This download has expired. Process the file again.")
        return send_file(job["archive"], as_attachment=True, download_name="ihatepdf-results.zip")

    @app.errorhandler(HTTPException)
    def http_error(error):
        message = "Files are too large. Choose less than 256 MB per operation." if isinstance(error, RequestEntityTooLarge) else error.description
        return jsonify(error=message), error.code

    return app

