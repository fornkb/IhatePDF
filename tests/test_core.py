from pathlib import Path

from PIL import Image
import pymupdf
import pytest

from ihatepdf import core

from ihatepdf.output import atomic_write, validate_outputs
from ihatepdf.pages import parse_pages


@pytest.mark.parametrize("spec,expected", [
    ("1-3,5,last", [0, 1, 2, 4, 5]), ("last-4", [5, 4, 3]),
    ("odd", [0, 2, 4]), ("even", [1, 3, 5]), ("1,1,2", [0, 1]),
    ("ALL", list(range(6))), (" 2 - 4 ", [1, 2, 3]),
])
def test_page_selections(spec, expected):
    assert parse_pages(spec, 6) == expected


@pytest.mark.parametrize("spec", ["0", "7", "2-8", "", "1,", "banana", "-1"])
def test_invalid_selections(spec):
    with pytest.raises(ValueError):
        parse_pages(spec, 6)


def test_reorder_can_duplicate_pages():
    assert parse_pages("2,1,2", 3, duplicates=True) == [1, 0, 1]


def test_merge_preserves_content_bookmarks_links(sample, tmp_path):
    output = tmp_path / "merged.pdf"
    core.merge([sample, sample], output)
    with pymupdf.open(output) as doc:
        assert doc.page_count == 8
        assert "Sample page 1" in doc[4].get_text()
        assert doc.get_toc()[-1] == [1, "Second chapter", 7]
        assert doc[0].get_links()[0]["uri"] == "https://example.com"
        assert doc.metadata["title"] == "IhatePDF test"


@pytest.mark.parametrize("operation,pages,expected", [
    ("extract", "2,last", [2, 4]), ("delete", "2-3", [1, 4]),
    ("reorder", "4-2,1,1", [4, 3, 2, 1, 1]),
])
def test_page_edits(sample, tmp_path, operation, pages, expected):
    output = tmp_path / "edited.pdf"
    core.edit_pages(sample, output, operation, pages)
    with pymupdf.open(output) as doc:
        assert doc.page_count == len(expected)
        for page, number in zip(doc, expected):
            assert f"Sample page {number}" in page.get_text()
        assert doc.metadata["title"] == "IhatePDF test"


def test_cannot_delete_every_page(sample, tmp_path):
    output = tmp_path / "empty.pdf"
    with pytest.raises(ValueError, match="empty"):
        core.edit_pages(sample, output, "delete", "all")
    assert not output.exists()


def test_rotation_and_crop(sample, tmp_path):
    rotated = tmp_path / "rotated.pdf"
    cropped = tmp_path / "cropped.pdf"
    core.edit_pages(sample, rotated, "rotate", "2", angle=-90)
    core.edit_pages(rotated, cropped, "crop", "2", margins=(10, 20, 30, 40))
    with pymupdf.open(cropped) as doc:
        assert doc[0].rotation == 0
        assert doc[1].rotation == 270
        assert doc[1].cropbox.width == 380
        assert doc[1].cropbox.height == 535


@pytest.mark.parametrize("margins", [(500, 0, 0, 0), (-1, 0, 0, 0), (float("nan"), 0, 0, 0)])
def test_invalid_crop_is_not_published(sample, tmp_path, margins):
    output = tmp_path / "invalid.pdf"
    with pytest.raises(ValueError):
        core.edit_pages(sample, output, "crop", "all", margins=margins)
    assert not output.exists()


def test_split_ranges_and_chunks(sample, tmp_path):
    outputs = core.split(sample, tmp_path / "ranges", ranges="1-2;4,3")
    with pymupdf.open(outputs[1]) as doc:
        assert doc.page_count == 2
        assert "Sample page 4" in doc[0].get_text()
    chunks = core.split(sample, tmp_path / "chunks", every=3)
    with pymupdf.open(chunks[1]) as doc:
        assert doc.page_count == 1


def test_split_preflights_all_collisions(sample, tmp_path):
    directory = tmp_path / "parts"
    directory.mkdir()
    (directory / "source_part_002.pdf").write_bytes(b"existing")
    with pytest.raises(ValueError, match="exists"):
        core.split(sample, directory)
    assert not (directory / "source_part_001.pdf").exists()


def test_images_to_pdf_and_image_exports(image, sample, tmp_path):
    output = tmp_path / "images.pdf"
    core.images_to_pdf([image, image], output, page_size="original", dpi=160)
    with pymupdf.open(output) as doc:
        assert doc.page_count == 2
        assert doc[0].rect.width == 288
        assert doc[0].rect.height == 144
    for fmt in ("png", "jpg"):
        outputs = core.pdf_to_images(sample, tmp_path / fmt, pages="2,4", image_format=fmt, dpi=72)
        assert len(outputs) == 2
        with Image.open(outputs[0]) as exported:
            assert exported.size == (420, 595)
            assert exported.format == ("JPEG" if fmt == "jpg" else "PNG")


def test_text_only_requested_pages(sample, tmp_path):
    output = tmp_path / "text.txt"
    assert core.extract_text(sample, output, pages="2,4")
    text = output.read_text(encoding="utf-8")
    assert "Sample page 2" in text and "Sample page 4" in text
    assert "Sample page 1" not in text


def test_password_round_trip(sample, tmp_path):
    locked = tmp_path / "locked.pdf"
    unlocked = tmp_path / "unlocked.pdf"
    core.protect(sample, locked, new_password="test-secret")
    assert core.inspect_pdf(locked)["locked"]
    assert core.inspect_pdf(locked, "test-secret")["encrypted"]
    with pytest.raises(ValueError, match="incorrect"):
        core.unlock(locked, unlocked, password="wrong")
    core.unlock(locked, unlocked, password="test-secret")
    with pymupdf.open(unlocked) as doc:
        assert not doc.needs_pass
        assert doc.page_count == 4


def test_encrypted_split(sample, tmp_path):
    locked = tmp_path / "locked.pdf"
    core.protect(sample, locked, new_password="secret")
    outputs = core.split(locked, tmp_path / "parts", password="secret")
    assert len(outputs) == 4
    with pymupdf.open(outputs[0]) as doc:
        assert "Sample page 1" in doc[0].get_text()


def test_watermark_numbers_and_rotation(sample, image, tmp_path):
    rotated = tmp_path / "rotated.pdf"
    marked = tmp_path / "marked.pdf"
    numbered = tmp_path / "numbered.pdf"
    core.edit_pages(sample, rotated, "rotate", "2", angle=90)
    core.watermark(rotated, marked, text="DRAFT", pages="2", font_size=30)
    core.number_pages(marked, numbered, template="Page {page} of {total}")
    with pymupdf.open(numbered) as doc:
        assert "DRAFT" not in doc[0].get_text()
        assert "DRAFT" in doc[1].get_text()
        assert "Page 2 of 4" in doc[1].get_text()
        assert doc[1].rect.width == 595
        assert doc[1].rect.height == 420
    core.watermark(sample, tmp_path / "image-marked.pdf", image=image)
    with pymupdf.open(tmp_path / "image-marked.pdf") as doc:
        assert doc[0].get_images()


def test_text_too_large_does_not_publish(sample, tmp_path):
    output = tmp_path / "huge.pdf"
    with pytest.raises(ValueError, match="fit"):
        core.watermark(sample, output, text="Very long watermark " * 20, font_size=80)
    assert not output.exists()


def test_compression_preserves_text_and_shrinks_image_pdf(tmp_path):
    image = tmp_path / "noise.png"
    # Deterministic noise provides a meaningful lossy compression test.
    import random
    rng = random.Random(42)
    Image.frombytes("RGB", (600, 600), rng.randbytes(600 * 600 * 3)).save(image)
    source = tmp_path / "image.pdf"
    core.images_to_pdf([image], source)
    with pymupdf.open(source) as doc:
        doc[0].insert_text((30, 50), "Keep searchable text")
        doc.save(tmp_path / "source.pdf")
    for quality in (None, 50):
        output = tmp_path / f"compressed-{quality}.pdf"
        before, after = core.compress(tmp_path / "source.pdf", output, quality=quality)
        with pymupdf.open(output) as doc:
            assert "Keep searchable text" in doc[0].get_text()
        if quality:
            assert after < before * 0.6


def test_source_and_existing_outputs_are_protected(sample, tmp_path):
    original = sample.read_bytes()
    with pytest.raises(ValueError, match="input"):
        core.unlock(sample, sample, force=True)
    assert sample.read_bytes() == original
    output = tmp_path / "existing.pdf"
    output.write_bytes(b"sentinel")
    with pytest.raises(ValueError, match="exists"):
        core.unlock(sample, output)
    assert output.read_bytes() == b"sentinel"
    core.unlock(sample, output, force=True)
    with pymupdf.open(output) as doc:
        assert doc.page_count == 4


def test_atomic_failure_preserves_existing_file(tmp_path):
    output = tmp_path / "existing.pdf"
    output.write_bytes(b"original")
    def fail(staged):
        staged.write_bytes(b"partial")
        raise ValueError("failed")
    with pytest.raises(ValueError):
        atomic_write(output, fail, force=True)
    assert output.read_bytes() == b"original"
    assert not list(tmp_path.glob(".ihatepdf-*"))


def test_atomic_write_refuses_racing_writer(tmp_path):
    output = tmp_path / "out.txt"
    def write(staged):
        staged.write_text("ours")
        output.write_text("other writer")
    with pytest.raises(FileExistsError):
        atomic_write(output, write)
    assert output.read_text() == "other writer"


