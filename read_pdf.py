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


# Words whose vertical centers differ by less than this fraction of the
# (smaller) word height are on the same row.
LINE_Y_TOLERANCE = 0.5
# A horizontal gap wider than this many line-heights starts a new line (columns).
COLUMN_GAP = 2.0
# Default word flags, minus ligature preservation so "ﬂ" comes out as "fl".
WORD_FLAGS = pymupdf.TEXTFLAGS_WORDS & ~pymupdf.TEXT_PRESERVE_LIGATURES


def _word_boxes(page):
    """(x0, y0, x1, y1, text) per word, in displayed-page coordinates."""
    out = []
    for w in page.get_text("words", flags=WORD_FLAGS):
        r = pymupdf.Rect(w[:4])
        if page.rotation:
            r = (r * page.rotation_matrix).normalize()
        out.append((r.x0, r.y0, r.x1, r.y1, w[4]))
    return out


def _make_line(words):
    return {
        "text": " ".join(w[4] for w in words),
        "bbox": [round(v, 2) for v in (
            min(w[0] for w in words), min(w[1] for w in words),
            max(w[2] for w in words), max(w[3] for w in words))],
    }


def rebuild_lines(page):
    """Text lines rebuilt from word positions, top-to-bottom, left-to-right."""
    words = sorted(_word_boxes(page), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    rows = []  # each row: [center_y, height, [words]]
    for w in words:
        cy, h = (w[1] + w[3]) / 2, w[3] - w[1]
        if rows and abs(cy - rows[-1][0]) <= LINE_Y_TOLERANCE * min(h, rows[-1][1]):
            rows[-1][2].append(w)
        else:
            rows.append([cy, h, [w]])

    lines = []
    for _, _, row in rows:
        row.sort(key=lambda w: w[0])
        height = max(w[3] - w[1] for w in row)
        current = [row[0]]
        for prev, w in zip(row, row[1:]):
            if w[0] - prev[2] > COLUMN_GAP * height:
                lines.append(current)
                current = []
            current.append(w)
        lines.append(current)
    return [_make_line(ws) for ws in lines]
