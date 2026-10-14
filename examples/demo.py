"""Generate a small local demonstration: python examples/demo.py."""

from pathlib import Path

from PIL import Image, ImageDraw
import pymupdf

from ihatepdf import core


def main() -> None:
    directory = Path(__file__).resolve().parents[1] / "output" / "demo"
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "sample.pdf"
    if source.exists():
        raise SystemExit(f"Demo already exists at {directory}. Choose a new directory or remove old demo outputs first.")
    with pymupdf.open() as doc:
        for number in range(1, 4):
            page = doc.new_page(width=595, height=842)
            page.draw_rect(pymupdf.Rect(0, 0, 595, 115), color=None, fill=(0.08, 0.18, 0.3))
            page.insert_text((40, 55), "LOCAL IhatePDF", fontsize=23, color=(1, 1, 1))
            page.insert_text((40, 88), f"Sample document - page {number}", fontsize=12, color=(0.7, 0.85, 1))
            page.insert_text((40, 165), "A simple document to try the PDF tools.", fontsize=15)
            page.insert_text((40, 205), "Merge, split, trim, rotate, crop, stamp, and protect PDFs.", fontsize=12)
            for row in range(4):
                top = 260 + row * 74
                page.draw_rect(pymupdf.Rect(40, top, 555, top + 58), color=None, fill=(0.91, 0.95, 0.98))
                page.insert_text((55, top + 33), f"Example content row {row + 1} on page {number}", fontsize=12)
            if number == 3:
                page.set_rotation(90)
        doc.set_metadata({"title": "IhatePDF demo"})
        doc.set_toc([[1, "Introduction", 1], [1, "Landscape example", 3]])
        doc.save(source)
    logo = directory / "logo.png"
    image = Image.new("RGBA", (360, 180), (0, 0, 0, 0))
    drawing = ImageDraw.Draw(image)
    drawing.rounded_rectangle((5, 5, 355, 175), radius=35, fill=(35, 100, 165, 255))
    drawing.text((120, 80), "IhatePDF", fill="white")
    image.save(logo)
    core.watermark(source, directory / "draft.pdf", text="DRAFT", font_size=48)
    core.number_pages(directory / "draft.pdf", directory / "numbered.pdf", template="Page {page} of {total}")
    core.watermark(source, directory / "branded.pdf", image=logo, opacity=0.3)
    core.edit_pages(source, directory / "trimmed.pdf", "extract", "1,last")
    core.edit_pages(source, directory / "cropped.pdf", "crop", "all", margins=(18, 18, 18, 18))
    core.pdf_to_images(directory / "numbered.pdf", directory / "previews", dpi=72)
    print(f"Demo outputs: {directory}")


if __name__ == "__main__":
    main()

