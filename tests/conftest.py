from pathlib import Path

import pymupdf
import pytest
from PIL import Image


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    path = tmp_path / "source.pdf"
    with pymupdf.open() as doc:
        for number in range(1, 5):
            page = doc.new_page(width=420, height=595)
            page.insert_text((30, 50), f"Sample page {number}", fontsize=20)
            page.draw_rect(pymupdf.Rect(30, 80, 390, 400), color=(0.2, 0.4, 0.7))
        doc.set_metadata({"title": "IhatePDF test", "author": "IhatePDF"})
        doc.set_toc([[1, "First chapter", 1], [1, "Second chapter", 3]])
        doc[0].insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(30, 50, 180, 65), "uri": "https://example.com"})
        doc.save(path)
    return path


@pytest.fixture
def image(tmp_path: Path) -> Path:
    path = tmp_path / "photo.png"
    Image.new("RGB", (640, 320), "#326ea8").save(path)
    return path

