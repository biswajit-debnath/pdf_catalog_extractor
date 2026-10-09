"""Tests for the Part 2 rule classifier."""
import json
from pathlib import Path

import pytest

import classify
import read_pdf

SAMPLES = Path(__file__).parent.parent / "sample_pdfs"
FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_catalog.pdf"


def page(index=0, lines=(), shares=()):
    return {"page_index": index, "lines": [{"text": line} for line in lines],
            "images": [{"xref": i + 10, "area_share": share}
                       for i, share in enumerate(shares)],
            "has_text_layer": bool(lines), "word_count": sum(len(line.split()) for line in lines)}


LABEL = "Design | SR. NO :- 10"
SPECS = "Width - 137 CMS | Composition - Cotton | Weight - 500 GLM"


@pytest.mark.parametrize("line, expected", [
    ("ZANY| SR. NO :- 401", 1),
    ("Matisse | SR. NO :- 01", 1),
    ("Name | SR.NO :- 5", 1),
    ("Name / Sr. No 5", 1),
    ("Name – SR NO: 5", 1),
    ("Name — SRNO 5", 1),
    ("Name - SR No.-5", 1),
    ("Name | SR. NOTE 5", 0),
    ("SR. NO :- 5", 0),
    ("matisee - 01", 0),
    ("Width -137 CMS | Composition", 0),
    ("Matisse Decorative Prints abstract compositions", 0),
    ("One | SR. NO 1 Two | SR. NO 2", 2),
])
def test_sr_marker_variants(line, expected):
    assert len(classify._sr_marker(classify.CONFIG).findall(line)) == expected


@pytest.mark.parametrize("info, verdict, code", [
    ({"page_index": 0, "error": "ValueError: bad page"}, "uncertain", "page_read_error"),
    (page(lines=[LABEL, LABEL]), "skip", "multiple_sr_labels"),
    (page(lines=[LABEL, LABEL], shares=[0.6]), "uncertain", "multiple_sr_labels_with_large_image"),
    (page(lines=[LABEL, SPECS], shares=[0.6]), "product", "single_sr_single_large_image"),
    (page(lines=["abstract compositions"], shares=[0.26]), "skip", "no_markers"),
    (page(lines=[LABEL]), "uncertain", "sr_label_no_large_image"),
    (page(lines=[LABEL], shares=[0.6, 0.7]), "uncertain", "sr_label_multiple_large_images"),
    (page(lines=["wIdTh 137"]), "uncertain", "specs_no_sr_label"),
    (page(shares=[0.6]), "skip", "no_markers"),
])
def test_rule_rows(info, verdict, code):
    result = classify.classify_page(info)
    assert result["verdict"] == verdict
    assert result["reason"].startswith(code + ": ")
    assert result["page_index"] == info["page_index"]


def test_signals_and_boundaries():
    info = page(lines=["One | SR. NO 1 Two | SR. NO 2", "compositions WIDTH"],
                shares=[0.30, 0.31])
    signals = classify.get_signals(info)
    assert signals["sr_label_count"] == 2
    assert signals["large_images"] == [{"xref": 11, "area_share": 0.31}]
    assert signals["largest_image_share"] == 0.31
    assert signals["spec_keywords"] == ["Width"]


def test_config_controls_layout():
    config = {**classify.CONFIG, "large_image_share": 0.5,
              "sr_pattern": r"CAT\s*#\d+", "spec_keywords": ["Fiber"],
              "min_product_share": 0.2}
    info = page(lines=["CAT #7", "fiber cotton"], shares=[0.6])
    assert classify.classify_page(info, config)["verdict"] == "product"


def test_warning_cases_and_json_round_trip():
    empty = classify.classify_pdf([])
    assert empty["summary"]["warning"].endswith("skipped_with_large_image: 0")
    no_products = classify.classify_pdf([page(0, shares=[0.8])])
    assert no_products["summary"]["warning"].endswith("skipped_with_large_image: 1")
    assert no_products["summary"]["skipped_with_large_image"] == {"count": 1, "pages": [0]}
    pages = [page(i) for i in range(10)]
    pages[0] = page(0, [LABEL], [0.6])
    pages[1] = page(1, shares=[0.8])
    result = classify.classify_pdf(pages, {**classify.CONFIG, "min_product_share": 0.2})
    assert result["summary"]["warning"].endswith("skipped_with_large_image: 1")
    assert result["summary"]["product_share"] == 0.1
    assert json.loads(json.dumps(result)) == result
    assert len(result["pages"]) == 10


def test_skipped_large_image_threshold_and_review_signals():
    result = classify.classify_pdf([
        page(0, shares=[0.30]), page(1, shares=[0.3001]),
        page(2, lines=["Width - 137 CMS"], shares=[0.9]),
        page(3, lines=[LABEL], shares=[0.6]),
    ])
    assert result["summary"]["skipped_with_large_image"] == {"count": 1, "pages": [1]}
    assert result["summary"]["warning"] is None
    assert result["review"] == [{
        "page_index": 2,
        "reason": result["pages"][2]["reason"],
        "signals": result["pages"][2]["signals"],
    }]
    assert result["pages"][2]["reason"].startswith("specs_no_sr_label: ")


def test_synthetic_pdf_end_to_end():
    result = classify.classify_pdf(read_pdf.read_pdf(str(FIXTURE))["pages"])
    assert [p["verdict"] for p in result["pages"]] == [
        "skip", "skip", "skip", "product", "product", "skip",
        "uncertain", "uncertain", "skip", "skip"]
    assert result["summary"]["product"] == 2
    assert result["summary"]["skipped_with_large_image"] == {"count": 2, "pages": [0, 5]}
    assert result["summary"]["warning"] is None
    assert result["pages"][7]["reason"].startswith("specs_no_sr_label: ")
    assert result["review"] == [
        {"page_index": p["page_index"], "reason": p["reason"], "signals": p["signals"]}
        for p in result["pages"] if p["verdict"] == "uncertain"
    ]
    assert json.loads(json.dumps(result)) == result


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="sample_pdfs/ missing")
@pytest.mark.parametrize("filename, products, skips, large_skips", [
    ("Ikat_sm.pdf", [1, 2, 3, 4, 5], [0, 6, 7], [0, 7]),
    ("Matisse_sm.pdf", [3, 4, 5, 6], [0, 1, 2, 7], [0]),
])
def test_real_sample_verdicts(filename, products, skips, large_skips):
    result = classify.classify_pdf(read_pdf.read_pdf(str(SAMPLES / filename))["pages"])
    indices = lambda verdict: [p["page_index"] for p in result["pages"]
                               if p["verdict"] == verdict]
    assert indices("product") == products
    assert indices("skip") == skips
    assert indices("uncertain") == []
    assert result["review"] == []
    assert result["summary"]["skipped_with_large_image"] == {
        "count": len(large_skips), "pages": large_skips}
    assert result["summary"]["warning"] is None
