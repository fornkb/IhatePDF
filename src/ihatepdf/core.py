"""PDF operations. No network calls or subprocesses are used here."""

from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
import math

from PIL import Image, ImageOps
import pymupdf as pdf

from .output import atomic_write, validate_outputs
from .pages import parse_pages


@contextmanager
def open_pdf(path: Path, password: str | None = None) -> Iterator[pdf.Document]:
    if not path.is_file():
        raise ValueError(f"Input file not found: {path}.")
    with pdf.open(path) as doc:
        if not doc.is_pdf:
            raise ValueError(f"Expected a PDF: {path}.")
        if doc.needs_pass and (password is None or not doc.authenticate(password)):
            raise ValueError("Input PDF password is required or incorrect. Enter the correct password in the settings.")
        if not doc.page_count:
            raise ValueError(f"The PDF has no pages: {path}.")
        yield doc


def save_pdf(doc: pdf.Document, output: Path, *, force: bool = False, **options) -> None:
    settings = dict(garbage=4, deflate=True, encryption=pdf.PDF_ENCRYPT_NONE)
    settings.update(options)
    atomic_write(output, lambda staged: doc.save(staged, **settings), force=force)


def merge(inputs: list[Path], output: Path, password: str | None = None, force: bool = False) -> None:
    validate_outputs([output], inputs, force)
    with pdf.open() as result:
        toc = []
        for path in inputs:
            with open_pdf(path, password) as source:
                offset = result.page_count
                result.insert_pdf(source)
                for level, title, page in source.get_toc():
                    toc.append([level, title, page + offset if page > 0 else page])
                if offset == 0:
                    result.set_metadata(source.metadata)
        if toc:
            result.set_toc(toc)
        save_pdf(result, output, force=force)


def edit_pages(input: Path, output: Path, command: str, pages: str, *, password=None,
               force=False, angle=90, margins=(0, 0, 0, 0)) -> None:
    validate_outputs([output], [input], force)
    with open_pdf(input, password) as doc:
        chosen = parse_pages(pages, doc.page_count, duplicates=command == "reorder")
        if command in {"extract", "reorder"}:
            doc.select(chosen)
        elif command == "delete":
            remaining = [i for i in range(doc.page_count) if i not in set(chosen)]
            if not remaining:
                raise ValueError("Deleting all pages would produce an empty PDF.")
            doc.select(remaining)
        elif command == "rotate":
            if angle % 90:
                raise ValueError("Rotation must be a multiple of 90 degrees.")
            for index in chosen:
                page = doc[index]
                page.set_rotation((page.rotation + angle) % 360)
        elif command == "crop":
            if any(not math.isfinite(v) or v < 0 for v in margins):
                raise ValueError("Crop margins must be finite, nonnegative numbers.")
            left, top, right, bottom = margins
            for index in chosen:
                page = doc[index]
                # Crop relative to the current visible, unrotated crop box.
                box = page.cropbox
                cropped = pdf.Rect(box.x0 + left, box.y0 + top, box.x1 - right, box.y1 - bottom)
                if cropped.is_empty:
                    raise ValueError(f"Crop margins remove all of page {index + 1}.")
                page.set_cropbox(cropped)
        else:
            raise ValueError(f"Unknown page operation: {command}.")
        save_pdf(doc, output, force=force)


def split(input: Path, output_dir: Path, *, ranges: str | None = None, every: int = 1,
          password=None, force=False, protected_inputs=()) -> list[Path]:
    with open_pdf(input, password) as source:
        if ranges is not None:
            groups = [parse_pages(spec, source.page_count) for spec in ranges.split(";")]
        else:
            if every < 1:
                raise ValueError("Pages per chunk must be at least 1.")
            groups = [list(range(i, min(i + every, source.page_count)))
                      for i in range(0, source.page_count, every)]
        outputs = [output_dir / f"{input.stem}_part_{i:03}.pdf" for i in range(1, len(groups) + 1)]
        validate_outputs(outputs, [input, *protected_inputs], force)
        for indices, output in zip(groups, outputs):
            # Select from a full copy so internal links and bookmarks get remapped.
            with pdf.open(stream=source.tobytes(encryption=pdf.PDF_ENCRYPT_NONE), filetype="pdf") as part:
                part.select(indices)
                save_pdf(part, output, force=force)
    return outputs


def images_to_pdf(inputs: list[Path], output: Path, *, page_size="a4", dpi=150, force=False) -> None:
    validate_outputs([output], inputs, force)
    if dpi < 1:
        raise ValueError("Image DPI must be positive.")
    with pdf.open() as doc:
        for path in inputs:
            with Image.open(path) as original:
                image = ImageOps.exif_transpose(original).convert("RGB")
                data = BytesIO()
                image.save(data, format="PNG")
                if page_size == "original":
                    width, height = image.width * 72 / dpi, image.height * 72 / dpi
                else:
                    width, height = pdf.paper_size(page_size)
                    if image.width > image.height:
                        width, height = height, width
                page = doc.new_page(width=width, height=height)
                page.insert_image(page.rect, stream=data.getvalue(), keep_proportion=True)
        save_pdf(doc, output, force=force)


def pdf_to_images(input: Path, output_dir: Path, *, pages="all", image_format="png",
                  dpi=150, quality=85, password=None, force=False, protected_inputs=()) -> list[Path]:
    if not 1 <= dpi <= 1200:
        raise ValueError("Resolution must be between 1 and 1200 DPI.")
    if not 1 <= quality <= 100:
        raise ValueError("Image quality must be between 1 and 100.")
    with open_pdf(input, password) as doc:
        chosen = parse_pages(pages, doc.page_count)
        outputs = [output_dir / f"{input.stem}_page_{i + 1:03}.{image_format}" for i in chosen]
        validate_outputs(outputs, [input, *protected_inputs], force)
        for index, output in zip(chosen, outputs):
            pix = doc[index].get_pixmap(dpi=dpi, colorspace=pdf.csRGB, alpha=False)
            def write(staged, pix=pix):
                if image_format == "png":
                    pix.save(staged)
                else:
                    pix.pil_save(staged, format="JPEG", quality=quality)
            atomic_write(output, write, force=force)
    return outputs


def extract_text(input: Path, output: Path, *, pages="all", password=None, force=False) -> bool:
    validate_outputs([output], [input], force)
    with open_pdf(input, password) as doc:
        texts = [doc[i].get_text(sort=True).rstrip() for i in parse_pages(pages, doc.page_count)]
    atomic_write(output, lambda staged: staged.write_text("\n\f\n".join(texts) + "\n", encoding="utf-8"), force=force)
    return any(t.strip() for t in texts)


def compress(input: Path, output: Path, *, quality: int | None = None, dpi=150,
             password=None, force=False) -> tuple[int, int]:
    validate_outputs([output], [input], force)
    with open_pdf(input, password) as doc:
        if quality is not None:
            if not 1 <= quality <= 100 or not 36 <= dpi <= 1200:
                raise ValueError("Quality must be 1-100 and image DPI must be 36-1200.")
            doc.rewrite_images(dpi_threshold=dpi + 1, dpi_target=dpi, quality=quality)
        save_pdf(doc, output, force=force, use_objstms=1)
    return input.stat().st_size, output.stat().st_size


def protect(input: Path, output: Path, *, new_password: str, owner_password: str | None = None,
            password=None, force=False) -> None:
    if not new_password:
        raise ValueError("The new password cannot be empty.")
    if len(new_password.encode("utf-8")) > 40 or (owner_password and len(owner_password.encode("utf-8")) > 40):
        raise ValueError("PDF passwords must be at most 40 UTF-8 bytes.")
    validate_outputs([output], [input], force)
    with open_pdf(input, password) as doc:
        save_pdf(doc, output, force=force, encryption=pdf.PDF_ENCRYPT_AES_256,
                 user_pw=new_password, owner_pw=owner_password or new_password)


def unlock(input: Path, output: Path, *, password=None, force=False) -> None:
    validate_outputs([output], [input], force)
    with open_pdf(input, password) as doc:
        save_pdf(doc, output, force=force)


def _stamp_text(page, text: str, *, size: float, y: float, color, opacity=1.0, font_file=None) -> None:
    if font_file is None:
        try:
            text.encode("latin-1")
        except UnicodeEncodeError as exc:
            raise ValueError("Upload a suitable TTF/OTF font for this text.") from exc
    rect = pdf.Rect(12, y, page.rect.width - 12, y + size * 2.8)
    result = page.insert_textbox(rect, text, fontsize=size, fontname="custom" if font_file else "helv",
                                 fontfile=str(font_file) if font_file else None, align=1,
                                 color=color, fill_opacity=opacity)
    if result < 0:
        raise ValueError(f"Text does not fit page {page.number + 1}. Reduce the font size or shorten the text.")


def watermark(input: Path, output: Path, *, text=None, image: Path | None = None,
              pages="all", opacity=0.2, font_size=40, font_file=None, password=None, force=False) -> None:
    if (text is None) == (image is None):
        raise ValueError("Choose a text watermark or an image watermark.")
    if text is not None and not text.strip():
        raise ValueError("Watermark text cannot be empty.")
    if not 0 < opacity <= 1 or not math.isfinite(font_size) or font_size <= 0:
        raise ValueError("Opacity must be greater than 0 and at most 1; font size must be positive.")
    validate_outputs([output], [input] + ([image] if image else []) + ([font_file] if font_file else []), force)
    image_data = None
    if image:
        with Image.open(image) as original:
            rgba = ImageOps.exif_transpose(original).convert("RGBA")
            rgba.putalpha(rgba.getchannel("A").point(lambda alpha: round(alpha * opacity)))
            stream = BytesIO()
            rgba.save(stream, format="PNG")
            image_data = stream.getvalue()
    with open_pdf(input, password) as doc:
        for index in parse_pages(pages, doc.page_count):
            page = doc[index]
            page.remove_rotation()
            if image_data:
                page.insert_image(pdf.Rect(page.rect.width * 0.2, page.rect.height * 0.2,
                                  page.rect.width * 0.8, page.rect.height * 0.8), stream=image_data)
            else:
                _stamp_text(page, text, size=font_size, y=max(12, page.rect.height / 2 - font_size),
                            color=(0.4, 0.4, 0.4), opacity=opacity, font_file=font_file)
        save_pdf(doc, output, force=force)


def number_pages(input: Path, output: Path, *, pages="all", start=1, position="bottom",
                 template="{page} / {total}", font_size=11, font_file=None, password=None, force=False) -> None:
    if not math.isfinite(font_size) or font_size <= 0:
        raise ValueError("Font size must be positive.")
    validate_outputs([output], [input] + ([font_file] if font_file else []), force)
    with open_pdf(input, password) as doc:
        for offset, index in enumerate(parse_pages(pages, doc.page_count)):
            try:
                label = template.format(page=start + offset, total=doc.page_count, original=index + 1)
            except (KeyError, IndexError, ValueError, AttributeError) as exc:
                raise ValueError("Invalid template. Use {page}, {total}, and/or {original}.") from exc
            page = doc[index]
            page.remove_rotation()
            y = 12 if position == "top" else page.rect.height - font_size * 2.8 - 12
            if y < 0:
                raise ValueError("Page is too small for this font size.")
            _stamp_text(page, label, size=font_size, y=y, color=(0.15, 0.15, 0.15), font_file=font_file)
        save_pdf(doc, output, force=force)


def inspect_pdf(input: Path, password=None) -> dict:
    if not input.is_file():
        raise ValueError(f"Input file not found: {input}.")
    with pdf.open(input) as doc:
        if not doc.is_pdf:
            raise ValueError(f"Expected a PDF: {input}.")
        encrypted = bool(doc.needs_pass or doc.metadata and doc.metadata.get("encryption"))
        locked = bool(doc.needs_pass)
        if locked and password is not None:
            if not doc.authenticate(password):
                raise ValueError("Incorrect password.")
            locked = False
        info = dict(file=str(input.resolve()), bytes=input.stat().st_size, pages=doc.page_count,
                    encrypted=encrypted, locked=locked)
        if not locked:
            info.update(metadata=doc.metadata, page_sizes=[dict(page=i + 1, width_pt=p.rect.width,
                        height_pt=p.rect.height, rotation=p.rotation) for i, p in enumerate(doc)])
    return info

