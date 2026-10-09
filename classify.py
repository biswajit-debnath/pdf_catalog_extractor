"""Classify Part 1 PageInfo records with deterministic catalog rules."""
import argparse
import json
import re
import sys


CONFIG = {
    "large_image_share": 0.30,
    "sr_pattern": r"[\w.]\s*[|/–—-]\s*SR\.?\s*NO\b",
    "spec_keywords": ["Width", "Composition", "Weight"],
    "min_product_share": 0.10,
}


def _sr_marker(config):
    """Compile the configured name/separator/SR. NO marker."""
    return re.compile(config["sr_pattern"], re.IGNORECASE)


def get_signals(page_info, config=CONFIG):
    """Measure only the page features used by the rule table."""
    lines = [line.get("text", "") for line in page_info.get("lines", [])]
    marker = _sr_marker(config)
    sr_count = sum(len(marker.findall(line)) for line in lines)
    images = page_info.get("images", [])
    threshold = config["large_image_share"]
    large = [
        {"xref": image["xref"], "area_share": image["area_share"]}
        for image in images if image.get("area_share", 0) > threshold
    ]
    keywords = [
        keyword for keyword in config["spec_keywords"]
        if any(re.search(r"\b" + re.escape(keyword) + r"\b", line, re.IGNORECASE)
               for line in lines)
    ]
    return {
        "sr_label_count": sr_count,
        "large_images": large,
        "largest_image_share": max((image.get("area_share", 0) for image in images), default=0.0),
        "spec_keywords": keywords,
        "has_text_layer": page_info.get("has_text_layer", False),
        "word_count": page_info.get("word_count", 0),
    }


def classify_page(page_info, config=CONFIG):
    """Give a PageInfo record one verdict and a readable reason."""
    signals = get_signals(page_info, config)
    labels = signals["sr_label_count"]
    large = len(signals["large_images"])
    specs = bool(signals["spec_keywords"])
    if "error" in page_info:
        verdict, code, sentence = "uncertain", "page_read_error", page_info["error"]
    elif labels >= 2 and large == 0:
        verdict, code, sentence = "skip", "multiple_sr_labels", f"found {labels} SR. NO labels and no large image"
    elif labels >= 2 and large >= 1:
        verdict, code, sentence = "uncertain", "multiple_sr_labels_with_large_image", f"found {labels} SR. NO labels and {large} large image(s)"
    elif labels == 1 and large == 1:
        share = signals["large_images"][0]["area_share"]
        verdict, code, sentence = "product", "single_sr_single_large_image", f"1 SR. NO label and 1 image covering {share:.0%} of the page"
    elif labels == 0 and not specs:
        verdict, code, sentence = "skip", "no_markers", "no SR. NO label or spec keyword"
    elif labels == 1 and large == 0:
        verdict, code, sentence = "uncertain", "sr_label_no_large_image", "1 SR. NO label but no large image"
    elif labels == 1 and large >= 2:
        verdict, code, sentence = "uncertain", "sr_label_multiple_large_images", f"1 SR. NO label and {large} large images"
    elif labels == 0 and specs:
        verdict, code, sentence = "uncertain", "specs_no_sr_label", f"spec keyword(s) {', '.join(signals['spec_keywords'])} but no SR. NO label"
    return {"page_index": page_info["page_index"], "verdict": verdict,
            "reason": f"{code}: {sentence}", "signals": signals}


def classify_pdf(page_infos, config=CONFIG):
    """Classify all pages, count verdicts, and collect pages needing review."""
    pages = [classify_page(page, config) for page in page_infos]
    total = len(pages)
    counts = {verdict: sum(page["verdict"] == verdict for page in pages)
              for verdict in ("product", "skip", "uncertain")}
    share = counts["product"] / total if total else 0.0
    skipped_large = [page["page_index"] for page in pages
                     if page["verdict"] == "skip"
                     and page["signals"]["largest_image_share"] > config["large_image_share"]]
    if total == 0:
        warning = "no pages to classify"
    elif counts["product"] == 0:
        warning = "no product pages found"
    elif share < config["min_product_share"]:
        warning = f"product share {share:.1%} is below {config['min_product_share']:.1%}"
    else:
        warning = None
    if warning and (counts["product"] == 0 or share < config["min_product_share"]):
        warning += f"; skipped_with_large_image: {len(skipped_large)}"
    summary = {"total": total, **counts, "product_share": share,
               "skipped_with_large_image": {"count": len(skipped_large), "pages": skipped_large},
               "warning": warning}
    review = [{"page_index": page["page_index"], "reason": page["reason"],
               "signals": page["signals"]}
              for page in pages if page["verdict"] == "uncertain"]
    return {"pages": pages, "summary": summary, "review": review}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Classify PDF catalog pages.")
    parser.add_argument("pdf", help="path to the PDF file")
    parser.add_argument("--json", action="store_true", help="print the full JSON result")
    args = parser.parse_args(argv)
    import read_pdf
    read_pdf.pymupdf.set_messages(stream=sys.stderr)
    read_pdf.pymupdf.TOOLS.mupdf_display_errors(True)
    try:
        source = read_pdf.read_pdf(args.pdf)
    except read_pdf.ReadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    result = classify_pdf(source["pages"])
    sys.stdout.reconfigure(encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("page  verdict    reason code                         labels  largest share")
        for page in result["pages"]:
            signals = page["signals"]
            code = page["reason"].split(": ", 1)[0]
            print(f"{page['page_index']:>4}  {page['verdict']:<9}  {code:<35}"
                  f" {signals['sr_label_count']:>3}      {signals['largest_image_share']:.4f}")
        print("summary: " + json.dumps(result["summary"], ensure_ascii=False))
    if result["summary"]["warning"]:
        print("warning: " + result["summary"]["warning"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
