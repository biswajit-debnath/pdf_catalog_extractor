# Part 1 — PDF Page Reader: Plan

## Context

Part 1 of a low-cost pipeline (read → classify → extract swatch → LLM fields → validate → write) that turns
~100-page fabric catalog PDFs into one folder per product. Part 1 only **reads and reports**: per page, its
size, text lines rebuilt from word positions, the images actually drawn on it, and whether a text layer exists.
Later parts consume this output, so the schema must be stable, flat, and JSON-serializable.

Repo today: only `README.md`. Samples: `sample_pdfs/Ikat_sm.pdf`, `sample_pdfs/Matisse_sm.pdf` (8 pages each).

---

## 1. Research findings (checked 2026-10-01)

### Library choice: PyMuPDF 1.28.2

| Item | Finding |
|---|---|
| Version | **1.28.2** (uploaded 2026-08-06; bundles MuPDF 1.28.2). Previous: 1.28.0 (2026-06-29), 1.27.2.3. |
| Install / import | `pip install pymupdf` → `import pymupdf`. Legacy `import fitz` still works but is discouraged (clashes with an unrelated `fitz` package on PyPI). |
| Python | `requires_python >=3.10`; ships `cp310-abi3` wheels incl. `win_amd64`, so it installs as a binary on the local Python 3.14.4. |
| License | **AGPL-3.0 or Artifex commercial** (see Open question 1). |
| Verified | Wheel unpacked into a scratch dir and run read-only against both samples; every API below behaved as documented. |

**APIs used (all from the current docs):**

| Need | API | Notes |
|---|---|---|
| Page size | `page.rect` (= `page.bound()`) | Reflects `/Rotate`. All *other* coordinates (words, image bboxes) are for the **unrotated** page; convert with `page.rotation_matrix`. |
| Words + positions | `page.get_text("words", flags=...)` → `(x0, y0, x1, y1, word, block_no, line_no, word_no)` | Words split on whitespace. Default flags `TEXTFLAGS_WORDS` include `TEXT_PRESERVE_LIGATURES` and `TEXT_MEDIABOX_CLIP` (chars outside the mediabox are dropped). |
| Placed images | `page.get_image_info(xrefs=True)` → dicts with `bbox`, `width`, `height`, `transform`, `has-mask`, `xref` | Reports **exactly** the images drawn on the page (inline images too, `xref=0`), each placement separately, **without loading image bytes** (low memory). Includes images inside Form XObjects. |
| Soft-mask xref | `page.get_images(full=True)` → `(xref, smask, w, h, ...)` | Lists images *referenced* by the page's resources, not necessarily drawn. Used only to look up `smask` for an xref. |
| Text layer exists | `len(words) > 0` | No dedicated API exists. |

**Alternatives considered:**
- **pdfplumber 0.11.10 / pdfminer.six 20260107 (MIT):** a workable alternative. It has `extract_words` and `page.images` (bbox + `srcsize`), but it is pure Python and much slower on image-heavy 100-page catalogs (pdfplumber's own README says so). Getting an xref and placement matrix comparable to PyMuPDF's is also clumsier, and later parts (swatch extraction) need PyMuPDF-style xref/pixmap access anyway. **Rejected** unless the AGPL is a blocker.
- **pypdf 6.19.0 (BSD):** `page.images` lists referenced images with no placement rect. Word positions need a hand-written visitor. **Rejected.**

### Pitfalls, and what the samples actually showed

- **Odd reading order.** On Matisse p3–p6 the raw stream is `… Weight -` / `GLM | Martindale …` / `910`, but all three spans share y0/y1 (1039.92–1062.32), so clustering by word position fixes it.
  - **Columns.** On the grid pages, labels in different columns sit on the same y. Ikat p6 has `ZANT | SR. NO :- 401` and `MOD | SR. NO :- 301` at y=599.8. A pure y-cluster would merge them into one line, so **we also split a row at large horizontal gaps**.
  - **Gap threshold.** Across both samples the largest gap inside a real line is 0.48× line height; column gaps are far larger. A threshold of **2.0× line height** is safe.
- **Rotated pages.** Both samples have `/Rotate 0`. For `rotation != 0`, word and image bboxes are mapped through `page.rotation_matrix`, so all output coordinates match the displayed page (`page.rect`).
- **Rotated images (stored vs. displayed).** `transform` shows it.
  - Ikat swatch: `(0, h, -w, 0, …)`, i.e. 90° clockwise; stored 1545×1092, shown portrait.
  - Matisse swatch: `(-w, 0, 0, -h, …)`, i.e. 180°.
  - Part 1 reports the transform plus a derived `rotation` and never rotates pixels.
- **Images placed multiple times.** On Ikat p0, xref 24 is drawn twice; both placements are reported, as two entries with the same xref.
- **Referenced but not drawn.** On Ikat p0, xref 23 is in the page resources but never drawn. `get_image_info` correctly omits it; `get_images` would have wrongly included it.
- **Inline images.** These come back with `xref=0`. We report them with `xref: 0` (none appear in the samples).
- **Masks.** Logo bands carry soft masks (e.g. Matisse xref 406 → smask 407). We report `has_mask` and `smask`, and never merge mask or overlay layers into the swatch. Logo, frame and info band are separate entries.
- **Bbox overshoot.** Some bboxes slightly exceed the page (e.g. `-0.3`, `1190.9`, logo at `y=-14`). `area_share` uses the bbox clipped to the page.
- **Ligatures.** Matisse p1 contains `ﬂ` / `ﬁ` (U+FB02 / U+FB01). We clear `TEXT_PRESERVE_LIGATURES` so they expand to `fl` / `fi`, which keyword matching downstream needs.
- **Windows console.** Printing `ﬂ` crashed on cp1252 stdout. The CLI reconfigures stdout to UTF-8.
- **Hidden / odd text.** Matisse p7's text layer has `www.nuhome.in`, reported as-is. Ikat p7 (back cover) has **no text at all** (0 words, 0 fonts), so `has_text_layer=false`.
- **Large images on non-product pages.** Not a reader problem, but relevant for Part 2: the Ikat cover (0.985 share), Ikat back cover (1.0) and Matisse cover (0.67) each also have one image over 30%.

**Sources:**
- PyPI JSON for [PyMuPDF](https://pypi.org/pypi/PyMuPDF/json), [pdfplumber](https://pypi.org/pypi/pdfplumber/json), [pypi](https://pypi.org/pypi/pypdf/json) (pypdf) and [pdfminer.six](https://pypi.org/pypi/pdfminer.six/json).
- [PyMuPDF installation](https://pymupdf.readthedocs.io/en/latest/installation.html).
- PyMuPDF docs source on GitHub `main`: [page.rst](https://github.com/pymupdf/PyMuPDF/blob/main/docs/page.rst) (`get_image_info`, `get_image_rects`, `rect`, `rotation_matrix`), [document.rst](https://github.com/pymupdf/PyMuPDF/blob/main/docs/document.rst) (`get_page_images` note: "not the list of images that are actually displayed"), [app3.rst](https://github.com/pymupdf/PyMuPDF/blob/main/docs/app3.rst) (coordinates are for the unrotated page), [textpage.rst](https://github.com/pymupdf/PyMuPDF/blob/main/docs/textpage.rst) (`extractWORDS`), [vars.rst](https://github.com/pymupdf/PyMuPDF/blob/main/docs/vars.rst) (text flags).
- [pdfplumber README](https://github.com/jsvine/pdfplumber).
- [pypdf "Extract Images" docs](https://github.com/py-pdf/pypdf/blob/main/docs/user/extract-images.md).

---

## 2. PageInfo schema

Top-level output of the CLI:

```json
{
  "file": "Matisse_sm.pdf",
  "page_count": 8,
  "pages": [ PageInfo, ... ]
}
```

One PageInfo (real values from Matisse page index 3):

```json
{
  "page_index": 3,
  "width": 828.0,
  "height": 1224.0,
  "area": 1013472.0,
  "rotation": 0,
  "has_text_layer": true,
  "word_count": 32,
  "lines": [
    {"text": "matisse", "bbox": [630.8, 21.96, 774.98, 77.95]},
    {"text": "Matisse | SR. NO :- 01", "bbox": [322.37, 1002.87, 505.93, 1028.07]},
    {"text": "Width -137 CMS | Composition - 100% Poly. | Weight - 910 GLM | Martindale - 50,000 Rubs",
     "bbox": [62.43, 1039.92, 765.75, 1062.32]},
    {"text": "07", "bbox": [39.05, 1168.8, 63.7, 1198.19]},
    {"text": "go to shade - 1 thumbnail", "bbox": [609.26, 1171.92, 790.88, 1191.52]}
  ],
  "images": [
    {"xref": 404, "smask": 0, "width": 1566, "height": 2114,
     "bbox": [37.96, 111.91, 789.96, 1127.1], "area_share": 0.7533,
     "transform": [-751.92, 0.0, 0.0, -1015.15, 789.96, 1127.1], "rotation": 180, "has_mask": false},
    {"xref": 405, "smask": 0, "width": 319, "height": 148,
     "bbox": [23.03, -10.31, 264.03, 101.5], "area_share": 0.0243,
     "transform": [241.0, 0.0, 0.0, 111.81, 23.03, -10.31], "rotation": 0, "has_mask": false},
    {"xref": 406, "smask": 407, "width": 1650, "height": 518,
     "bbox": [43.07, 25.79, 266.07, 95.8], "area_share": 0.0154,
     "transform": [223.0, 0.0, 0.0, 70.01, 43.07, 25.79], "rotation": 0, "has_mask": true}
  ]
}
```

Field rules:
- **Coordinates:**
  - All coordinates are PDF points, origin top-left, y down, in the *displayed* page space.
  - bbox is `[x0, y0, x1, y1]`, rounded to 2 decimal places.
- **`lines`:**
  - Ordered top-to-bottom, then left-to-right.
  - `text` is the words joined by single spaces.
  - `bbox` is the union of the word bboxes.
- **`images`:**
  - Listed in **draw order**, so later entries are drawn on top.
  - `xref=0` means an inline image.
  - `width` and `height` are the stored pixel size.
  - `area_share` = area(bbox ∩ page) / page area, rounded to 4 decimal places.
  - `rotation` is the clockwise angle, rounded to 0/90/180/270, by which the *stored* image is turned when drawn. It is derived as `atan2(b, a)` from the transform. Mirroring isn't classified, but it is visible in `transform`.
- **`has_text_layer`:** `word_count > 0`. It is also true for invisible text such as OCR layers; that text is reported as-is.
- **Failed page:** the record becomes `{"page_index": i, "error": "<message>"}` and reading continues.

---

## 3. Work segments

Files: `read_pdf.py` (module + CLI, target ~180–230 lines), `tests/test_read_pdf.py`, `requirements.txt`,
`requirements-dev.txt`, `.gitignore`, `plan/part1-plan.md`.

### Seg 1 — Setup, open PDF, page dimensions (~40 lines)
- **Goal:** a venv with pinned PyMuPDF, a PDF opener, and page dimensions.
- **Approach:**
  - `python -m venv .venv`, then `pip install -r requirements-dev.txt`.
    - `requirements.txt` holds `pymupdf==1.28.2`.
    - `requirements-dev.txt` holds `-r requirements.txt` and `pytest`.
  - `.gitignore` covers `.venv/`, `__pycache__/` and `out/`.
  - `open_pdf(path)` returns a `pymupdf.Document`, or raises `ReadError` with a clear message (details in Seg 5).
  - `page_size(page)` returns width, height, area and rotation from `page.rect` and `page.rotation`.
- **Expected:** Ikat 841.89×1190.55; Matisse 828×1224; all rotation 0.
- **Verify:** print the sizes for all 16 pages, plus `pymupdf.__version__ == "1.28.2"`.

### Seg 2 — Word extraction and line rebuilding (~50 lines)
- **Goal:** `rebuild_lines(page) -> list[{"text", "bbox"}]`.
- **Approach:**
  1. Read words with flags `TEXTFLAGS_WORDS & ~TEXT_PRESERVE_LIGATURES`. If `page.rotation`, map each bbox through `page.rotation_matrix`.
  2. Sort by (y-center, x0). A word joins the current row if `|cy - row_cy| <= 0.5 * min(h, row_h)` (`LINE_Y_TOLERANCE = 0.5`); otherwise it starts a new row.
  3. Sort each row by x0. Split it into separate lines wherever the gap to the previous word is more than `COLUMN_GAP = 2.0` × the row's tallest word height.
  4. Join words with spaces, union the bboxes, and order lines by (row y, x0).
- **Expected:**
  - Matisse p3: `Width -137 CMS | Composition - 100% Poly. | Weight - 910 GLM | Martindale - 50,000 Rubs`.
  - Ikat p6: 4 separate `… | SR. NO :- …` lines.
  - Matisse p1: `fluid`, not `ﬂuid`.
- **Verify:** print the lines for Ikat p1, p6 and Matisse p1, p3, p7. Add tests for the 910 order and the grid split.

### Seg 3 — Placed images with area share (~40 lines)
- **Goal:** `list_images(page) -> list[dict]`, in draw order.
- **Approach:**
  - `page.get_image_info(xrefs=True)` gives the placements.
  - A `{xref: smask}` map from `page.get_images(full=True)` fills in `smask`.
  - Bbox (and transform, if the page is rotated) go through `rotation_matrix`; then compute the clipped area share and the derived rotation.
  - No pixel data is loaded.
- **Expected:**
  - Ikat p1–p5: one image at 1.0 share, rotation 90, plus logos and band below 5%.
  - Matisse p3–p6: one image at 0.75–0.80, rotation 180.
  - Ikat p0: xref 23 absent, xref 24 listed twice.
  - Grids: Ikat p6 has 4 images around 0.17; Matisse p2 has 15 images around 0.03.
- **Verify:**
  - Print the image tables for all pages.
  - Visually check the rotation convention once: render Ikat p1 and Matisse p3, save the stored swatch pixmaps to a scratch dir, and confirm that the stored image turned by `rotation` clockwise matches the page.

### Seg 4 — PageInfo assembly, text-layer flag, JSON (~30 lines)
- **Goal:** `read_page(page) -> dict` and `iter_pages(doc)`, a generator that handles one page at a time.
- **Approach:**
  - Combine Segs 1–3 and add `has_text_layer` and `word_count`.
  - All values are plain floats, ints and strings, so `json.dumps` works with no custom encoder.
- **Expected:** Ikat p7 has `has_text_layer: false` and `lines: []`. Every page round-trips through `json.dumps`.
- **Verify:** dump Matisse p3 and Ikat p7 as JSON and show them.

### Seg 5 — CLI and error handling (~45 lines)
- **Goal:** `python read_pdf.py FILE.pdf [-o OUT.json]`, using argparse.
- **Approach:**
  - **Output:** JSON with `indent=2` and `ensure_ascii=False`. Stdout is reconfigured to UTF-8 (Windows cp1252 fix).
  - **Missing, corrupt or not-a-document file:** catch `pymupdf.FileDataError` / `RuntimeError`, write a one-line message to stderr, exit 1.
  - **Not a PDF:** checked with `doc.is_pdf`. Error and exit 1.
  - **Encrypted:** if `doc.needs_pass` is true (MuPDF has already tried the empty password), report "encrypted, password required" and exit 1. Files that are owner-password-only open and read normally.
  - **Page failure:** record `{"page_index", "error"}`, warn on stderr, and continue. Exit 0 if every page read, exit 2 if any page failed.
- **Expected:** valid JSON for all 8 Matisse pages; clean error messages for a garbage file and an encrypted file.
- **Verify:** run on both samples; run on a garbage-bytes file and on an AES-encrypted copy made in a temp dir.

### Seg 6 — Tests against the samples (~120 lines, pytest)
Tests added in each segment, collected in `tests/test_read_pdf.py`. They skip if `sample_pdfs/` is missing.
- **Page counts and sizes:** 8 pages each; sizes as in Seg 1.
- **Matisse 910 order:** the p3 spec line contains `Weight - 910 GLM | Martindale`. p5 and p6 have the same; p4 has `Weight - 510 GLM`.
- **Product pages** (Ikat 1–5, Matisse 3–6):
  - Exactly one image with `area_share > 0.30`, with rotation 90 (Ikat) or 180 (Matisse).
  - At least two other images on the page (logo and band kept separate).
  - One line matching `\w+\s*\|\s*SR\. NO`.
  - One line containing Width, Composition and Weight.
- **Ikat p1 exact spec line:** `Width -137 CMS | Composition - 70% Polyester+ 16% Cott. +14% Linen | Weight - 565 GLM`.
- **Grids:**
  - Ikat p6: 4 SR. NO lines and no image over 0.30.
  - Matisse p2: 15 thumbnail images around 0.03 and no image over 0.30.
- **Ikat p0:** xref 23 not reported; xref 24 reported twice.
- **Back covers:**
  - Ikat p7: `has_text_layer` false and no lines.
  - Matisse p7: lines include `www.nuhome.in` (reported as-is).
- **Rotated page:** open Matisse in memory, `set_rotation(90)` on p3 (not saved). Width and height swap, and the spec line still reads correctly.
- **CLI:** run via subprocess on Matisse; the output parses as JSON with 8 pages; the garbage file and the encrypted file exit non-zero with a message.
- **Verify:** `python -m pytest -q`; all green.

---

## 4. Edge cases

**Handled:**
- **Pages with no text layer** (scanned pages, or the Ikat back cover): `has_text_layer=false`, `lines=[]`. Images are still listed.
- **Several images per page:** all placements are reported in draw order.
- **One image placed several times** on a page: each placement is reported.
- **Images reused across pages:** each page reports its own placements; the xref is the same, which lets later parts deduplicate.
- **Rotated pages** (`/Rotate`): all coordinates are mapped to the displayed space.
- **Rotated or flipped placement of a stored image:** reported via `transform` and `rotation`, never applied.
- **Inline images:** reported with `xref: 0`.
- **Soft masks:** reported via `has_mask` and `smask`.
- **Bboxes overshooting the page:** clipped for `area_share`; the raw bbox is kept.
- **Corrupt, encrypted or non-PDF input:** a clear error and a non-zero exit.
- **One bad page:** recorded as an error; the remaining pages are still read.

**Not handled (out of scope):**
- **OCR** for scanned pages.
- **Vertical or rotated text runs within an unrotated page:** words come out with tall, narrow bboxes and form their own lines.
- **Right-to-left scripts.**
- **Multi-column paragraph reflow:** columns are split into separate lines, not merged into paragraphs.
- **Detecting hidden or covered text** (e.g. Matisse p7): reported as-is.
- **Vector graphics** (frames drawn as paths): not listed.
- **Images fully off-page:** still listed, with `area_share` 0.
- **Password-protected PDFs:** no password option is offered.

---

## 5. Open questions

1. **License.** PyMuPDF is AGPL-3.0 (or commercial). That's fine for an internal pipeline, but it matters if this ships in a product or a network service. Is it acceptable? The fallback is pdfplumber (MIT), which is slower and would need a different image/xref approach.
2. **Column split.** Rows are split into separate lines at gaps over 2× line height. Without this, Part 2 would count 2 SR. NO lines on the Ikat grid instead of 4. OK?
3. **Image `rotation` and `transform`.** These are derived facts, not a rotation of pixels. They save Part 3 from recomputing them. OK to include?
4. **Ligature expansion** (`ﬂ` → `fl`). I recommend it for downstream keyword matching. OK?
5. **Output shape.** One JSON document per PDF, not JSON Lines. For 100 pages it is a few hundred KB, and it's easy to read by eye. OK?
6. **Sample PDFs in git.** They are about 10 MB and the tests depend on them. Commit them, or keep them untracked?
