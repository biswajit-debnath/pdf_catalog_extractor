# PDF Catalog Extractor

This project is building a pipeline that turns fabric catalog PDFs into product swatch images and metadata. **Parts 1 and 2 are complete:** it can read pages and classify them. Image extraction, metadata generation, validation, and product folders are planned for later parts.

## What works now

- `read_pdf.py` reads each PDF page into JSON: page size, reconstructed text lines, placed images (including each image's xref and page-area share), and text-layer information. A failed page is reported as an error record without stopping the rest of the PDF.
- `classify.py` uses those page records to assign every page `product`, `skip`, or `uncertain`. It prints a page table by default, or a JSON result containing `pages`, `summary`, and the `review` list. Rules and thresholds are in the `CONFIG` dict at the top of the file.
- Pages marked `uncertain` go into the review list. A low or zero product-page share sets `summary.warning`. Classification does not extract images or write output files.

The full rule table, decisions, and known edge cases are in [`docs/part2-plan.md`](docs/part2-plan.md). The Part 1 reader design is in [`docs/part1-plan.md`](docs/part1-plan.md).

## Setup (PowerShell)

From the repository root, with Python 3.10 or newer installed:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For tests, install the development requirements instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`requirements.txt` pins PyMuPDF 1.28.2. The classifier itself uses only the Python standard library.

## Run

The repository includes a small synthetic PDF that can be used immediately:

```powershell
.\.venv\Scripts\python.exe classify.py tests\fixtures\synthetic_catalog.pdf
```

To classify a local catalog, pass its path:

```powershell
.\.venv\Scripts\python.exe classify.py sample_pdfs\Matisse_sm.pdf
.\.venv\Scripts\python.exe classify.py sample_pdfs\Ikat_sm.pdf
```

The table shows the zero-based `page` index, verdict, reason code, SR. NO label count, and largest image's page-area share. The last line gives the product/skip/uncertain counts and any warning. Use `--json` to get the full result, including each product page's `signals.large_images[0].xref` for the later extraction step:

```powershell
.\.venv\Scripts\python.exe classify.py sample_pdfs\Matisse_sm.pdf --json
```

To inspect Part 1's raw page records or save them to a file:

```powershell
.\.venv\Scripts\python.exe read_pdf.py sample_pdfs\Matisse_sm.pdf
.\.venv\Scripts\python.exe read_pdf.py sample_pdfs\Matisse_sm.pdf -o matisse_output.json
```

`sample_pdfs/` is local and is not included in the repository. Put your own PDFs there or pass any PDF path. The local sample directory and `*_output.json` files are gitignored. Do not commit client PDFs or their extracted output.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The classifier tests use hand-built page records and `tests/fixtures/synthetic_catalog.pdf`. Tests that require local real samples skip when `sample_pdfs/` is absent. To regenerate the synthetic PDF:

```powershell
.\.venv\Scripts\python.exe tests\make_fixtures.py
```

There are also Node.js tests for the Part 1 CLI (Node.js required):

```powershell
node --test tests_js/
```
