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
