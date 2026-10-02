"""Part 1: PDF page reader.

Reads a PDF page by page and reports, per page: size, text lines rebuilt from
word positions, images actually drawn on the page, and a text-layer flag.
It does not classify, rotate images, call any LLM or write output files.
"""
import argparse
import json
import math
import os
import sys

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


def _rotation_deg(transform):
    """Clockwise angle (0/90/180/270) the stored image is turned by when drawn."""
    a, b = transform[0], transform[1]
    return round(math.degrees(math.atan2(b, a)) / 90) % 4 * 90


def list_images(page):
    """Images actually drawn on the page, in draw order, one entry per placement.

    Reports the image as stored (no pixel data is loaded or rotated). Bbox is
    in displayed-page coordinates; area_share uses the bbox clipped to the page.
    """
    smask = {item[0]: item[1] for item in page.get_images(full=True)}
    page_rect = page.rect
    page_area = page_rect.width * page_rect.height
    images = []
    for info in page.get_image_info(xrefs=True):
        bbox = pymupdf.Rect(info["bbox"])
        matrix = pymupdf.Matrix(info["transform"])
        if page.rotation:
            bbox = (bbox * page.rotation_matrix).normalize()
            matrix = matrix * page.rotation_matrix
        transform = [matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f]
        clipped = bbox & page_rect  # empty rect if fully off-page
        images.append({
            "xref": info["xref"],
            "smask": smask.get(info["xref"], 0),
            "width": info["width"],
            "height": info["height"],
            "bbox": [round(v, 2) for v in bbox],
            "area_share": round(abs(clipped) / page_area, 4),
            "transform": [round(v, 4) for v in transform],
            "rotation": _rotation_deg(transform),
            "has_mask": info["has-mask"],
        })
    return images


def read_page(page):
    """One PageInfo record (plain dict, JSON-serializable)."""
    lines = rebuild_lines(page)
    word_count = sum(len(line["text"].split()) for line in lines)
    info = {"page_index": page.number}
    info.update(page_size(page))
    info["has_text_layer"] = word_count > 0
    info["word_count"] = word_count
    info["lines"] = lines
    info["images"] = list_images(page)
    return info


def iter_pages(doc):
    """Yield PageInfo records one page at a time (no page images are loaded).

    A page that fails to read yields {"page_index", "error"} and reading goes on.
    """
    for i in range(doc.page_count):
        try:
            yield read_page(doc[i])
        except Exception as e:
            yield {"page_index": i, "error": f"{type(e).__name__}: {e}"}


def read_pdf(path):
    """Read a whole PDF into {"file", "page_count", "pages"}."""
    with open_pdf(path) as doc:
        return {
            "file": os.path.basename(path),
            "page_count": doc.page_count,
            "repaired": doc.is_repaired,  # MuPDF had to rebuild a damaged file
            "pages": list(iter_pages(doc)),
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read a PDF and report per-page info as JSON.")
    parser.add_argument("pdf", help="path to the PDF file")
    parser.add_argument("-o", "--output", help="write JSON to this file instead of stdout")
    args = parser.parse_args(argv)

    # MuPDF diagnostics go to stdout by default and would corrupt the JSON.
    pymupdf.set_messages(stream=sys.stderr)
    pymupdf.TOOLS.mupdf_display_errors(True)
    try:
        result = read_pdf(args.pdf)
    except ReadError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if result["repaired"]:
        print("warning: PDF was damaged and repaired; content may be incomplete", file=sys.stderr)
    failed = [p["page_index"] for p in result["pages"] if "error" in p]
    for p in result["pages"]:
        if "error" in p:
            print(f"warning: page {p['page_index']}: {p['error']}", file=sys.stderr)

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
