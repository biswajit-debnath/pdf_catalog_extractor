"""Build a small, client-free PDF for the classifier integration test."""
from pathlib import Path

import pymupdf


OUTPUT = Path(__file__).parent / "fixtures" / "synthetic_catalog.pdf"
PAGE = pymupdf.Rect(0, 0, 400, 600)


def color_image(rgb):
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
    pix.clear_with(rgb)
    return pix.tobytes("png")


def add_image(page, rect, rgb=0x5577AA):
    page.insert_image(rect, stream=color_image(rgb))


def add_lines(page, lines):
    for i, line in enumerate(lines):
        page.insert_text((20, 30 + i * 20), line, fontsize=10)


def build(path=OUTPUT):
    doc = pymupdf.open()
    # Cover: a large image but no label.
    page = doc.new_page(width=400, height=600)
    add_image(page, PAGE)
    add_lines(page, ["CATALOG"])
    # Intro: 26% image and prose with a plural near-match.
    page = doc.new_page(width=400, height=600)
    add_image(page, pymupdf.Rect(180, 100, 388, 400))
    add_lines(page, ["abstract compositions and decorative prints"])
    # Grid: four separate labels and four small images.
    page = doc.new_page(width=400, height=600)
    add_lines(page, [f"Design {i} | SR. NO :- {i}" for i in range(4)])
    for i in range(4):
        add_image(page, pymupdf.Rect(20 + i * 95, 150, 100 + i * 95, 300), 0xAA7744)
    # Two product pages.
    for i in range(2):
        page = doc.new_page(width=400, height=600)
        add_lines(page, [f"Design | SR. NO :- {i + 10}",
                         "Width - 137 CMS | Composition - 100% Cotton | Weight - 500 GLM"])
        add_image(page, pymupdf.Rect(20, 100, 380, 550), 0x448866)
    # Large image without a label.
    page = doc.new_page(width=400, height=600)
    add_image(page, pymupdf.Rect(20, 100, 380, 550))
    # Label without a large image.
    page = doc.new_page(width=400, height=600)
    add_lines(page, ["Design | SR. NO :- 30"])
    # Specs without a label.
    page = doc.new_page(width=400, height=600)
    add_lines(page, ["Width - 137 CMS"])
    # Blank page and a small-image back cover.
    doc.new_page(width=400, height=600)
    page = doc.new_page(width=400, height=600)
    add_lines(page, ["BACK COVER"])
    add_image(page, pymupdf.Rect(20, 100, 120, 250))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path, garbage=4, deflate=True)
    doc.close()
    return path


if __name__ == "__main__":
    print(build())
