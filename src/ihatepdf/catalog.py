"""The tool catalog drives both the browser interface and request validation."""


def field(name, label, type="text", default="", **extra):
    return dict(name=name, label=label, type=type, default=default, **extra)


PAGES = field("pages", "Pages", default="all", hint="Use 1-5,8,last,odd,even or all. Numbers start at 1.")
FONT = field("font_size", "Font size", "number", 40, min=1, max=200, step=1)


def tool(id, title, description, category, icon, action, fields=None, **extra):
    return dict(id=id, title=title, description=description, category=category, icon=icon,
                action=action, fields=fields or [], **extra)


TOOLS = [
    tool("merge", "Merge PDF", "Bring multiple PDFs together, in the order you choose.", "Organize", "merge", "Merge PDFs", combine=True),
    tool("split", "Split PDF", "Separate pages, create chunks, or choose your own ranges.", "Organize", "split", "Split PDF", [
        field("split_mode", "Split by", "select", "pages", choices=[["pages", "Every page"], ["chunks", "Pages per file"], ["ranges", "Custom ranges"]]),
        field("every", "Pages per file", "number", 1, min=1, max=10000, when={"split_mode": "chunks"}),
        field("ranges", "Page ranges", default="1-3;4-last", hint="Separate files with semicolons.", when={"split_mode": "ranges"}),
    ]),
    tool("extract", "Trim PDF", "Keep just the pages you need and leave the rest behind.", "Organize", "trim", "Trim PDF", [PAGES]),
    tool("delete", "Delete pages", "Remove selected pages from your document.", "Organize", "delete", "Delete pages", [PAGES]),
    tool("reorder", "Reorder pages", "Set a new page order. Repeat pages if you need to.", "Organize", "reorder", "Reorder pages", [field("pages", "New page order", default="last-1", hint="List every page to keep. Example: 3,1,2 or last-1 to reverse.")]),
    tool("rotate", "Rotate PDF", "Turn all pages or a selection to the right angle.", "Organize", "rotate", "Rotate PDF", [PAGES, field("angle", "Clockwise rotation", "select", "90", choices=[["90", "90°"], ["180", "180°"], ["270", "270°"], ["-90", "90° counterclockwise"]])]),
    tool("crop", "Crop PDF", "Trim the visible margins of your pages.", "Organize", "crop", "Crop PDF", [PAGES, *[field(side, side.title() + " margin", "number", 18, min=0, step=1, hint="Points · 72 pt = 1 inch") for side in ("left", "top", "right", "bottom")]]),
    tool("images-to-pdf", "Images to PDF", "Turn your photos and images into one tidy PDF.", "Convert", "image", "Create PDF", [
        field("page_size", "Page size", "select", "a4", choices=[["a4", "A4"], ["letter", "Letter"], ["original", "Original image size"]]),
        field("dpi", "Image DPI", "number", 150, min=1, max=1200, when={"page_size": "original"}),
    ], combine=True, input="images"),
    tool("pdf-to-images", "PDF to images", "Save each page as a crisp PNG or JPG image.", "Convert", "image", "Export images", [PAGES,
        field("image_format", "Format", "select", "png", choices=[["png", "PNG"], ["jpg", "JPG"]]),
        field("dpi", "Resolution", "number", 150, min=1, max=1200, hint="DPI · higher values give larger images"),
        field("quality", "JPEG quality", "number", 85, min=1, max=100, when={"image_format": "jpg"}),
    ]),
    tool("word-to-pdf", "Word to PDF", "Convert Word documents into easy-to-share PDFs.", "Convert", "word", "Convert to PDF", input="word", office=True),
    tool("ppt-to-pdf", "PowerPoint to PDF", "Save your presentation as a PDF, slide by slide.", "Convert", "slides", "Convert to PDF", input="ppt", office=True),
    tool("office-to-pdf", "Office to PDF", "Convert spreadsheets and other Office documents.", "Convert", "office", "Convert to PDF", input="office", office=True),
    tool("text", "Extract text", "Save the text already in your PDF as a text file.", "Convert", "text", "Extract text", [PAGES]),
    tool("compress", "Compress PDF", "Make PDFs lighter with the quality you choose.", "Enhance", "compress", "Compress PDF", [
        field("compression", "Compression", "select", "lossless", choices=[["lossless", "Lossless optimization"], ["lossy", "Smaller images"]]),
        field("quality", "Image quality", "number", 65, min=1, max=100, when={"compression": "lossy"}),
        field("dpi", "Target image DPI", "number", 150, min=36, max=1200, when={"compression": "lossy"}),
    ]),
    tool("watermark", "Watermark", "Add a subtle text label or your own image.", "Enhance", "watermark", "Add watermark", [PAGES,
        field("watermark_type", "Watermark", "select", "text", choices=[["text", "Text"], ["image", "Image"]]),
        field("text", "Watermark text", default="DRAFT", when={"watermark_type": "text"}),
        dict(FONT, when={"watermark_type": "text"}),
        field("opacity", "Opacity", "number", 0.2, min=0.01, max=1, step=0.05, hint="0.01 is subtle · 1 is solid"),
    ]),
    tool("number", "Page numbers", "Add clean, consistent numbering to your document.", "Enhance", "number", "Number pages", [PAGES,
        field("start", "Start at", "number", 1, min=1, max=100000),
        field("position", "Position", "select", "bottom", choices=[["bottom", "Bottom"], ["top", "Top"]]),
        field("template", "Number format", default="{page} / {total}", hint="Use {page}, {total} and {original}."), dict(FONT, default=11),
    ]),
    tool("encrypt", "Protect PDF", "Add a password to open your PDF.", "Security", "lock", "Protect PDF", [
        field("new_password", "New opening password", "password", required=True),
        field("confirm_password", "Confirm password", "password", required=True),
        field("owner_password", "Owner password", "password", hint="Optional · leave blank to use the opening password"),
    ]),
    tool("unlock", "Unlock PDF", "Remove password protection using the correct password.", "Security", "unlock", "Unlock PDF"),
    tool("inspect", "PDF details", "Check pages, dimensions, metadata and protection.", "Enhance", "info", "Inspect PDF"),
]

for item in TOOLS:
    if item.get("office"):
        item["fields"] = [field("timeout", "Conversion timeout", "number", 120, min=1, max=600, hint="Seconds")]

TOOL_MAP = {item["id"]: item for item in TOOLS}

