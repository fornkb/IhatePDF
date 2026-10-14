from io import BytesIO
import json
from pathlib import Path
import time
import zipfile

import pymupdf
import pytest

from ihatepdf.web import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path / "jobs")
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def process(client, app, tool, paths, options=None, **extra):
    return client.post("/api/process", data=dict(tool=tool, options=json.dumps(options or {}),
                       files=[(BytesIO(path.read_bytes()), path.name) for path in paths], **extra),
                       headers={"X-IhatePDF-Token": app.config["CSRF_TOKEN"]})


def pdf_result(client, response, index=0):
    assert response.status_code == 200, response.json
    download = client.get(response.json["files"][index]["url"])
    assert download.status_code == 200
    assert "attachment" in download.headers["Content-Disposition"]
    return pymupdf.open(stream=download.data, filetype="pdf")


def test_homepage_has_all_tools_and_assets(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"PowerPoint to PDF" in response.data and b"Page numbers" in response.data
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/api/status").json["tools"] == 19
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("tool,options,expected", [
    ("extract", {"pages": "2,last"}, [2, 4]),
    ("delete", {"pages": "2-3"}, [1, 4]),
    ("reorder", {"pages": "4,1,1"}, [4, 1, 1]),
])
def test_web_page_operations(client, app, sample, tool, options, expected):
    response = process(client, app, tool, [sample], options)
    with pdf_result(client, response) as doc:
        assert doc.page_count == len(expected)
        for page, number in zip(doc, expected):
            assert f"Sample page {number}" in page.get_text()


def test_merge_preserves_upload_order(client, app, sample, tmp_path):
    other = tmp_path / "other.pdf"
    with pymupdf.open() as doc:
        doc.new_page().insert_text((40, 40), "FIRST IN MERGE")
        doc.save(other)
    with pdf_result(client, process(client, app, "merge", [other, sample])) as doc:
        assert doc.page_count == 5
        assert "FIRST IN MERGE" in doc[0].get_text()


def test_split_zip_and_repeated_filenames(client, app, sample):
    response = process(client, app, "split", [sample, sample], {"split_mode": "chunks", "every": 3})
    assert response.status_code == 200
    assert len(response.json["files"]) == 4
    bundle = client.get(response.json["archive"])
    with zipfile.ZipFile(BytesIO(bundle.data)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) == 4
        with pymupdf.open(stream=archive.read(names[1]), filetype="pdf") as doc:
            assert doc.page_count == 1


def test_custom_split_ranges(client, app, sample):
    response = process(client, app, "split", [sample], {"split_mode": "ranges", "ranges": "4,2;1"})
    with pdf_result(client, response) as doc:
        assert doc.page_count == 2 and "Sample page 4" in doc[0].get_text()


def test_rotate_and_crop(client, app, sample):
    with pdf_result(client, process(client, app, "rotate", [sample], {"angle": "270", "pages": "2"})) as doc:
        assert doc[1].rotation == 270 and doc[0].rotation == 0
    with pdf_result(client, process(client, app, "crop", [sample], {"left": 10, "right": 20, "top": 30, "bottom": 40})) as doc:
        assert doc[0].rect.width == 390 and doc[0].rect.height == 525


def test_images_and_text(client, app, image, sample):
    with pdf_result(client, process(client, app, "images-to-pdf", [image, image], {"page_size": "original", "dpi": 160})) as doc:
        assert doc.page_count == 2 and doc[0].rect.width == 288
    response = process(client, app, "pdf-to-images", [sample], {"pages": "2,4", "image_format": "jpg", "dpi": 72})
    assert response.status_code == 200
    assert len(response.json["files"]) == 2
    assert client.get(response.json["files"][0]["url"]).data.startswith(b"\xff\xd8")
    response = process(client, app, "text", [sample], {"pages": "2,4"})
    text = client.get(response.json["files"][0]["url"]).data.decode()
    assert "Sample page 2" in text and "Sample page 1" not in text


def test_watermarks_and_numbering(client, app, sample, image):
    with pdf_result(client, process(client, app, "watermark", [sample], {"text": "CONFIDENTIAL", "font_size": 24})) as doc:
        assert "CONFIDENTIAL" in doc[0].get_text()
    response = process(client, app, "watermark", [sample], {"watermark_type": "image"}, watermark_image=(BytesIO(image.read_bytes()), "logo.png"))
    with pdf_result(client, response) as doc:
        assert doc[0].get_images()
    with pdf_result(client, process(client, app, "number", [sample], {"start": 8, "template": "Page {page}"})) as doc:
        assert "Page 8" in doc[0].get_text()


def test_compression_download(client, app, sample):
    response = process(client, app, "compress", [sample])
    with pdf_result(client, response) as doc:
        assert "Sample page 1" in doc[0].get_text()
    assert "bytes" in response.json["notes"][0]


def test_encryption_and_unlock(client, app, sample, tmp_path):
    response = process(client, app, "encrypt", [sample], {"new_password": "secret", "confirm_password": "secret"})
    download = client.get(response.json["files"][0]["url"])
    protected = tmp_path / "protected.pdf"
    protected.write_bytes(download.data)
    with pymupdf.open(protected) as doc:
        assert doc.needs_pass
    with pdf_result(client, process(client, app, "unlock", [protected], {"password": "secret"})) as doc:
        assert not doc.needs_pass and doc.page_count == 4
    response = process(client, app, "encrypt", [sample], {"new_password": "one", "confirm_password": "two"})
    assert response.status_code == 400 and "match" in response.json["error"]


def test_inspection_is_renderable_and_downloadable(client, app, sample):
    response = process(client, app, "inspect", [sample])
    assert response.status_code == 200
    info = response.json["details"][0]
    assert info["pages"] == 4 and info["file"] == "source.pdf"
    assert info["metadata"]["title"] == "IhatePDF test"
    downloaded = json.loads(client.get(response.json["files"][0]["url"]).data)
    assert downloaded["pages"] == 4


def test_partial_batch_results_are_kept(client, app, sample, tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"invalid PDF")
    response = process(client, app, "extract", [sample, broken], {"pages": "1"})
    with pdf_result(client, response) as doc:
        assert doc.page_count == 1
    assert len(response.json["errors"]) == 1


def test_inputs_removed_and_results_expire(client, app, sample):
    response = process(client, app, "extract", [sample], {"pages": "1"})
    job = app.extensions["pdf_jobs"][response.json["job"]]
    assert not (job["path"] / "inputs").exists()
    job["created"] = time.time() - 4000
    assert client.get(response.json["files"][0]["url"]).status_code == 404
    assert not job["path"].exists()


def test_failed_job_cleans_up(client, app, sample):
    response = process(client, app, "delete", [sample], {"pages": "all"})
    assert response.status_code == 400
    assert list(app.config["WORK_ROOT"].iterdir()) == []


@pytest.mark.parametrize("options", [{"angle": "45"}, {"angle": "NaN"}, {"pages": [1, 2]}])
def test_invalid_settings_are_rejected(client, app, sample, options):
    response = process(client, app, "rotate", [sample], options)
    assert response.status_code == 400


def test_local_request_protection_and_upload_limits(client, app, sample):
    assert client.post("/api/process").status_code == 403
    assert client.post("/api/process", headers={"X-IhatePDF-Token": app.config["CSRF_TOKEN"], "Origin": "https://other.example"}).status_code == 403
    assert client.get("/", headers={"Host": "other.example"}).status_code == 400
    app.config["MAX_CONTENT_LENGTH"] = 100
    response = process(client, app, "merge", [sample])
    assert response.status_code == 413


def test_filename_traversal_is_sanitized(client, app, sample):
    response = client.post("/api/process", data={"tool": "inspect", "files": (BytesIO(sample.read_bytes()), "../../outside.pdf")}, headers={"X-IhatePDF-Token": app.config["CSRF_TOKEN"]})
    assert response.status_code == 200
    assert response.json["details"][0]["file"] == "outside.pdf"
    assert client.get("/download/unknown/0").status_code == 404


@pytest.mark.parametrize("tool,filename", [("word-to-pdf", "document.docx"), ("ppt-to-pdf", "slides.pptx"), ("office-to-pdf", "sheet.xlsx")])
def test_office_uploads_have_actionable_dependency_error(client, app, sample, monkeypatch, tool, filename):
    monkeypatch.setattr("ihatepdf.office.powerpoint_available", lambda: False)
    monkeypatch.setattr("ihatepdf.office.find_libreoffice", lambda explicit=None: None)
    response = client.post("/api/process", data={"tool": tool, "files": (BytesIO(b"office file"), filename)}, headers={"X-IhatePDF-Token": app.config["CSRF_TOKEN"]})
    assert response.status_code == 400 and "LibreOffice" in response.json["error"]

