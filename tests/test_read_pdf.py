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
