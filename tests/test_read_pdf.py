import os

import pymupdf
import pytest

import read_pdf

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "sample_pdfs")
IKAT = os.path.join(SAMPLES, "Ikat_sm.pdf")
MATISSE = os.path.join(SAMPLES, "Matisse_sm.pdf")

pytestmark = pytest.mark.skipif(not os.path.isdir(SAMPLES), reason="sample_pdfs/ missing")


@pytest.fixture(scope="module")
def ikat():
    with read_pdf.open_pdf(IKAT) as doc:
        yield doc


@pytest.fixture(scope="module")
def matisse():
    with read_pdf.open_pdf(MATISSE) as doc:
        yield doc


def test_pymupdf_version():
    assert pymupdf.__version__ == "1.28.2"


def test_page_counts(ikat, matisse):
    assert ikat.page_count == 8
    assert matisse.page_count == 8


def test_page_sizes(ikat, matisse):
    for page in ikat:
        s = read_pdf.page_size(page)
        assert (s["width"], s["height"], s["rotation"]) == (841.89, 1190.55, 0)
        assert s["area"] == pytest.approx(841.89 * 1190.55, rel=1e-4)
    for page in matisse:
        s = read_pdf.page_size(page)
        assert (s["width"], s["height"], s["rotation"]) == (828.0, 1224.0, 0)
        assert s["area"] == 828.0 * 1224.0


def test_rotated_page_swaps_size():
    doc = pymupdf.open(MATISSE)
    doc[3].set_rotation(90)  # in memory only
    s = read_pdf.page_size(doc[3])
    assert (s["width"], s["height"], s["rotation"]) == (1224.0, 828.0, 90)


def line_texts(doc, i):
    return [l["text"] for l in read_pdf.rebuild_lines(doc[i])]


def test_matisse_weight_order(matisse):
    assert line_texts(matisse, 3)[2] == (
        "Width -137 CMS | Composition - 100% Poly. | Weight - 910 GLM | Martindale - 50,000 Rubs")
    assert "Weight - 910 GLM | Martindale - 50,000 Rubs" in " ".join(line_texts(matisse, 5))
    assert "Weight - 910 GLM | Martindale - 50,000 Rubs" in " ".join(line_texts(matisse, 6))
    assert "Weight - 510 GLM | Martindale - 40,000 Rubs" in " ".join(line_texts(matisse, 4))


def test_ikat_spec_line(ikat):
    assert ("Width -137 CMS | Composition - 70% Polyester+ 16% Cott. +14% Linen | Weight - 565 GLM"
            in line_texts(ikat, 1))


def test_ikat_grid_columns_split(ikat):
    lines = line_texts(ikat, 6)
    assert lines == ["ZANT | SR. NO :- 401", "MOD | SR. NO :- 301",
                     "IKAT | SR. NO :- 101", "ABR | SR. NO :- 207"]


def test_ligatures_expanded(matisse):
    text = " ".join(line_texts(matisse, 1))
    assert "fluid lines" in text and "\ufb02" not in text


def test_line_order_top_to_bottom(matisse):
    ys = [l["bbox"][1] for l in read_pdf.rebuild_lines(matisse[3])]
    assert ys == sorted(ys)


def test_rotated_page_lines_in_displayed_space():
    # In-memory /Rotate 90: text now runs vertically, but every line bbox must
    # be in displayed-page coordinates (inside the swapped 1224x828 page).
    doc = pymupdf.open(MATISSE)
    unrotated = read_pdf.rebuild_lines(doc[3])
    doc[3].set_rotation(90)
    rotated = read_pdf.rebuild_lines(doc[3])
    assert rotated
    page_rect = doc[3].rect
    for l in rotated:
        assert pymupdf.Rect(l["bbox"]) in page_rect + (-1, -1, 1, 1)
    # same words either way
    words = lambda ls: sorted(" ".join(l["text"] for l in ls).split())
    assert words(rotated) == words(unrotated)


def big_images(doc, i):
    return [im for im in read_pdf.list_images(doc[i]) if im["area_share"] > 0.30]


@pytest.mark.parametrize("i", [1, 2, 3, 4, 5])
def test_ikat_product_pages_one_big_rotated_image(ikat, i):
    imgs = read_pdf.list_images(ikat[i])
    big = [im for im in imgs if im["area_share"] > 0.30]
    assert len(big) == 1
    assert big[0]["rotation"] == 90
    assert big[0]["area_share"] >= 0.99
    assert len(imgs) - len(big) >= 2  # logo/frame/band stay separate layers


@pytest.mark.parametrize("i", [3, 4, 5, 6])
def test_matisse_product_pages_one_big_rotated_image(matisse, i):
    imgs = read_pdf.list_images(matisse[i])
    big = [im for im in imgs if im["area_share"] > 0.30]
    assert len(big) == 1
    assert big[0]["rotation"] == 180
    assert 0.7 < big[0]["area_share"] < 0.85
    assert len(imgs) - len(big) >= 2


def test_ikat_cover_reused_and_undrawn_images(ikat):
    xrefs = [im["xref"] for im in read_pdf.list_images(ikat[0])]
    assert 23 not in xrefs            # referenced by the page, never drawn
    assert xrefs.count(24) == 2       # drawn twice -> two placements


def test_grid_pages_have_no_big_image(ikat, matisse):
    assert big_images(ikat, 6) == []
    assert big_images(matisse, 2) == []
    assert len(read_pdf.list_images(ikat[6])) >= 4
    assert len(read_pdf.list_images(matisse[2])) >= 15


def test_mask_reported(matisse):
    band = [im for im in read_pdf.list_images(matisse[3]) if im["xref"] == 406][0]
    assert band["has_mask"] and band["smask"] == 407


def test_area_share_clipped_to_page(matisse):
    for i in range(8):
        for im in read_pdf.list_images(matisse[i]):
            assert 0 <= im["area_share"] <= 1


def test_rotated_page_images_in_displayed_space():
    doc = pymupdf.open(MATISSE)
    before = max(read_pdf.list_images(doc[3]), key=lambda im: im["area_share"])
    doc[3].set_rotation(90)
    after = max(read_pdf.list_images(doc[3]), key=lambda im: im["area_share"])
    assert after["xref"] == before["xref"]
    assert after["area_share"] == pytest.approx(before["area_share"], abs=0.01)
    assert pymupdf.Rect(after["bbox"]).width == pytest.approx(pymupdf.Rect(before["bbox"]).height, abs=0.1)
    assert after["rotation"] == (before["rotation"] + 90) % 360


# ---- Seg 4: PageInfo assembly ----

def test_read_page_shape_and_json(ikat, matisse):
    import json
    for doc in (ikat, matisse):
        for page in doc:
            info = read_pdf.read_page(page)
            assert list(info) == ["page_index", "width", "height", "area", "rotation",
                                  "has_text_layer", "word_count", "lines", "images"]
            assert info["page_index"] == page.number
            assert json.loads(json.dumps(info)) == info


def test_text_layer_flag(ikat, matisse):
    assert read_pdf.read_page(ikat[7])["has_text_layer"] is False
    assert read_pdf.read_page(ikat[7])["lines"] == []
    assert read_pdf.read_page(ikat[7])["images"]       # images still reported
    assert read_pdf.read_page(matisse[3])["has_text_layer"] is True
    assert read_pdf.read_page(matisse[3])["word_count"] == 32


def test_matisse_back_cover_text_as_is(matisse):
    texts = [l["text"] for l in read_pdf.read_page(matisse[7])["lines"]]
    assert "www.nuhome.in" in texts


def test_product_page_part2_signals(ikat, matisse):
    import re
    for doc, pages in ((ikat, range(1, 6)), (matisse, range(3, 7))):
        for i in pages:
            info = read_pdf.read_page(doc[i])
            sr = [l for l in info["lines"] if re.search(r"\w+\s*\|\s*SR\. NO", l["text"])]
            assert len(sr) == 1
            spec = " ".join(l["text"] for l in info["lines"])
            assert all(k in spec for k in ("Width", "Composition", "Weight"))
            assert sum(im["area_share"] > 0.30 for im in info["images"]) == 1


def test_bad_page_does_not_stop_reading(matisse, monkeypatch):
    real = read_pdf.read_page
    def flaky(page):
        if page.number == 2:
            raise ValueError("boom")
        return real(page)
    monkeypatch.setattr(read_pdf, "read_page", flaky)
    pages = list(read_pdf.iter_pages(matisse))
    assert len(pages) == 8
    assert pages[2] == {"page_index": 2, "error": "ValueError: boom"}
    assert "lines" in pages[3]
