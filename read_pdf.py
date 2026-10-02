"""Part 1: PDF page reader.

Reads a PDF page by page and reports, per page: size, text lines rebuilt from
word positions, images actually drawn on the page, and a text-layer flag.
It does not classify, rotate images, call any LLM or write output files.
"""
import pymupdf


class ReadError(Exception):
    """The PDF could not be opened or read."""


def open_pdf(path):
    """Open a PDF, or raise ReadError with a readable message."""
    try:
        doc = pymupdf.open(path)
    except FileNotFoundError:
        raise ReadError(f"file not found: {path}")
    except Exception as e:  # MuPDF raises FileDataError / RuntimeError for bad data
        raise ReadError(f"cannot open {path}: {e}")
    if not doc.is_pdf:
        doc.close()
        raise ReadError(f"not a PDF: {path}")
    if doc.needs_pass:
        doc.close()
        raise ReadError(f"encrypted, password required: {path}")
    return doc


def page_size(page):
    """Width/height/area of the displayed page (rotation applied), in points."""
    r = page.rect
    return {
        "width": round(r.width, 2),
        "height": round(r.height, 2),
        "area": round(r.width * r.height, 2),
        "rotation": page.rotation,
    }
