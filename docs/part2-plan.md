# Part 2 — Rule Classifier: Plan

## Context

Pipeline: read → **classify** → extract swatch → LLM fields → validate → write → CLI.
Part 2 takes Part 1's PageInfo records and gives every page one verdict: `product`, `skip` or `uncertain`.
It touches no pixels, calls no LLM and writes no files. Deliverables: `classify.py` (module plus a small
`__main__`, target ~120–150 lines), `tests/test_classify.py`, `tests/make_fixtures.py`, this doc.

**Status: implemented and verified.**

---

## 1. Research findings (checked 2026-10-03)

### What Part 1 actually produces (read from `read_pdf.py`, `docs/part1-plan.md`, tests, and real output)

Everything Part 2 needs is already in PageInfo. **No change to Part 1 is proposed.**

| Needed by Part 2 | Where in PageInfo |
|---|---|
| Text lines to look for `Name \| SR. NO` and spec keywords | `lines[].text` (words rebuilt per row, split at column gaps) |
| Largest image share | `images[].area_share` (bbox clipped to the page, 4 decimals) |
| Which image to extract later (Part 3) | `images[].xref`, plus `bbox`, `rotation`, `page_index` |
| Failed page | `{"page_index", "error"}` record, with none of the other keys |

### Real data, all 16 pages (Part 1 output, read locally)

`lines` are the exact strings; "big" is images with `area_share > 0.30`.

| Page | Lines (abridged) | Largest image shares |
|---|---|---|
| Ikat p0 cover | `IKAT` | 0.985 (xref 22) |
| Ikat p1–p5 | `ZANY\| SR. NO :- 401` (p1, note: no space before the pipe), `MOD \| SR. NO :- 301`, `IKAT \| SR. NO :- 101`, `ABR \| SR. NO :- 207`, `ABR \| SR. NO :- 202`, then `Width -137 CMS \| Composition - … \| Weight - …` | 1.0 / 1.0 / 0.9999 / 1.0 / 0.9999 |
| Ikat p6 grid (2×2) | 4 separate lines `ZANT \| SR. NO :- 401`, `MOD \| …`, `IKAT \| …`, `ABR \| …` | 0.1686, 0.1685, 0.1683, 0.1682 |
| Ikat p7 back cover | **none** (`has_text_layer: false`) | 0.9998 |
| Matisse p0 cover | `matisse`, `Decorative Prints` | 0.6696 |
| Matisse p1 intro | `matisse`, `Decorative Prints`, 12 lines of prose | **0.2643**, 0.1518 |
| Matisse p2 grid | `matisee - 01`, `henry - 101`, … (14 labels) | 0.0337 max (17 images) |
| Matisse p3–p6 | `Matisse \| SR. NO :- 01`, `Henry \| SR. NO :- 101`, `Matisse \| SR. NO :- 02`, `Matisse \| SR. NO :- 03`, then `Width -137 CMS \| Composition - 100% Poly. \| Weight - 910 GLM \| Martindale - …` | 0.7532, 0.7746, 0.7533, 0.7991 |
| Matisse p7 back cover | `matisse`, `Natural Fibers II`, `www.nuhome.in` | 0.1655 |

### Two findings that differ from the brief (see Open questions 1 and 2)

1. **Matisse p1 (intro) has no image over 30%.** Its largest image is 0.2643. Under the rules as written
   ("no large image and no spec keywords" → skip) it is **skip, not uncertain**. The brief's "uncertain" is
   what you get only if "Composition" is matched as a plain substring, because the prose contains
   "abstract *compositions*". With a word-boundary match (recommended), it is skip.
2. **Matisse p2 (the 14-label grid) contains no `SR. NO` text at all.** Its labels are `matisee - 01`,
   `henry - 101`. So it is not caught by "several SR. NO labels"; it is skip via the second rule
   (no large image, no spec keywords): largest image is 0.034. The outcome (skip) matches the brief, the reason
   code differs (`no_large_image_no_specs`, not `multiple_sr_labels`). I did not add a second grid pattern because
   the brief says not to depend on the typos and the label shape (`word - number`) is far too generic.

### Stdlib / environment

- Python **3.14.4**, pytest **9.1.1**, pymupdf **1.28.2** (pinned). Nothing new is needed: Part 2 uses `re`,
  `json`, `argparse` only. No new dependency, no `requirements*.txt` change.
- `re` docs ([docs.python.org/3/library/re.html](https://docs.python.org/3/library/re.html), read 2026-10-03):
  the 3.13/3.14 changes (positional `flags` deprecated in `re.split`/`re.sub`; `\z` added; `\B` on empty input)
  do not affect us. We only use `re.compile(pattern, re.IGNORECASE)`, `.findall` and `.search`.
- Dataclasses are not needed: plain dicts keep the output JSON-serializable and hand-editable, as CLAUDE.md asks.

### Regex robustness

Candidate marker (compiled with `re.IGNORECASE`), tested in a scratch script against real and invented lines:

```
[\w.]\s*[|/–—-]\s*SR\.?\s*NO\b
```

| Input | Match? | Why |
|---|---|---|
| `ZANY\| SR. NO :- 401` (real, no space before pipe) | yes | `\s*` around the separator |
| `Matisse \| SR. NO :- 01` (real) | yes | |
| `Name \| SR.NO :- 5`, `Sr. No 5`, `SR NO: 5`, `SRNO 5`, `SR No.-5` | yes | `\.?` and `\s*` between `SR` and `NO`; ignore case |
| `Name - SR. NO 5` (hyphen/dash separator) | yes | separator class `\| / – — -` |
| `Name \| SR. NOTE 5` | **no** | `\b` after `NO` |
| `SR. NO :- 5` with no name before it | **no** | needs a name char and a separator before `SR` (this is the `Name \| SR. NO` form) |
| `matisee - 01`, `Width -137 CMS \| Composition` | no | |

Matches are counted with `findall` per line, not one per line, so two labels that Part 1 failed to split into
separate lines (gap under 2× line height) still count as two.

Keyword matching: `\b(Width|Composition|Weight)\b`, case-insensitive. Word boundaries matter: a plain substring
test finds "Composition" in the Matisse intro prose ("compositions").

---

## 2. Verdict rules and output schema

### Signals (all measured, none interpreted)

- `sr_label_count`: number of `sr_pattern` matches across all lines.
- `large_images`: placements with `area_share > large_image_share`, as `[{"xref", "area_share"}]`.
  Counted per placement, so one big image drawn twice counts as two (conservative: goes to review).
- `largest_image_share`: max `area_share` over all images (0.0 if none). Shown even when below the threshold.
- `spec_keywords`: which of the configured keywords appear (in config order).
- `has_text_layer`, `word_count`: copied from PageInfo, for debugging scanned pages.

### Rules (first match wins)

| # | Condition | Verdict | Reason code |
|---|---|---|---|
| 0 | PageInfo has `error` | uncertain | `page_read_error` |
| 1 | SR labels ≥ 2 and no large image | skip | `multiple_sr_labels` |
| 1b | SR labels ≥ 2 and a large image (proposed refinement, Q4) | uncertain | `multiple_sr_labels_with_large_image` |
| 2 | SR labels = 1 and large images = 1 | **product** | `single_sr_single_large_image` |
| 3 | SR labels = 0, large images = 0, no spec keyword | skip | `no_large_image_no_specs` |
| 4 | SR labels = 1, large images = 0 | uncertain | `sr_label_no_large_image` |
| 5 | SR labels = 1, large images ≥ 2 | uncertain | `sr_label_multiple_large_images` |
| 6 | SR labels = 0, spec keyword found | uncertain | `specs_no_sr_label` |
| 7 | SR labels = 0, large images ≥ 1, no spec keyword | uncertain | `large_image_no_sr_label` |

Rule 3 applies only when there is **no** SR label. The brief lists "one SR. NO but no large image" as uncertain,
and a page with one label and no image would otherwise also match the skip rule; label wins, so the page
goes to review, not dropped. Rules 4–7 plus 1b are the "anything else" bucket, split so a reviewer can see why.
Every combination of (labels 0/1/≥2) × (large 0/1/≥2) × (keywords yes/no) is covered; rule 7 is the fall-through.

### `classify_page(page_info, config=CONFIG)` output

```json
{
  "page_index": 3,
  "verdict": "product",
  "reason": "single_sr_single_large_image: 1 SR. NO label and 1 image covering 75% of the page",
  "signals": {
    "sr_label_count": 1,
    "large_images": [{"xref": 404, "area_share": 0.7532}],
    "largest_image_share": 0.7532,
    "spec_keywords": ["Width", "Composition", "Weight"],
    "has_text_layer": true,
    "word_count": 32
  }
}
```

`reason` is `"<code>: <sentence>"` (e.g. `multiple_sr_labels: found 14`); split on the first `": "` for the code.
Two small additions to the brief's schema: `page_index` (so results stand alone in lists) and
`large_images[].xref` (what Part 3 needs). Everything is JSON-serializable.

### `classify_pdf(page_infos, config=CONFIG)` output

```json
{
  "pages": [ /* one classify_page result per page, in page order */ ],
  "summary": {"total": 8, "product": 5, "skip": 1, "uncertain": 2,
              "product_share": 0.625, "warning": null},
  "review": [{"page_index": 0, "reason": "large_image_no_sr_label: 1 image covers 98% of the page, no SR. NO"}]
}
```

`review` lists every uncertain page with its reason, ready for Part 6 to write `review.json`. Nothing is
dropped: every input page appears in `pages` exactly once, in exactly one verdict.

**Fail-loud:** `summary.warning` is a string (never raises) when there are zero pages, zero product pages, or
`product_share < min_product_share` (default 0.10). Otherwise `null`. The CLI part decides whether to stop.

### Config (top of module, the only place to edit for a new layout)

```python
CONFIG = {
    "large_image_share": 0.30,
    "sr_pattern": r"[\w.]\s*[|/–—-]\s*SR\.?\s*NO\b",   # compiled with re.IGNORECASE
    "spec_keywords": ["Width", "Composition", "Weight"],
    "min_product_share": 0.10,    # below this fraction of product pages -> warning
}
```

### Predicted verdicts on the real samples (scratch run, same rules, 2026-10-03)

| Page | Verdict | Reason code |
|---|---|---|
| Ikat p0 cover | uncertain | `large_image_no_sr_label` |
| Ikat p1–p5 | **product** ×5 | `single_sr_single_large_image` |
| Ikat p6 grid | skip | `multiple_sr_labels` (4) |
| Ikat p7 back cover | uncertain | `large_image_no_sr_label` (no text layer at all) |
| Matisse p0 cover | uncertain | `large_image_no_sr_label` |
| Matisse p1 intro | **skip** (brief says uncertain, Q1) | `no_large_image_no_specs` |
| Matisse p2 grid | skip | `no_large_image_no_specs` (Q2) |
| Matisse p3–p6 | **product** ×4 | `single_sr_single_large_image` |
| Matisse p7 back cover | skip | `no_large_image_no_specs` |

**9/9 product pages, zero false positives.** Totals: Ikat 5 product / 1 skip / 2 uncertain; Matisse 4 / 3 / 1.
Summary share 5/8 and 4/8, far above the 10% warning floor.

**Covers and back covers (as requested):** a cover with a big background image and no SR. NO label is
**uncertain** (`large_image_no_sr_label`): Ikat p0, Ikat p7, Matisse p0. Matisse p7 has no big image, so it is
**skip**. None can be product, because product needs an SR. NO label. The 30% rule alone would fire on every
cover; it is the label requirement that keeps them out. Cost: covers land in the review list. That is
deliberate, since silently skipping is worse than one extra look, but see Q4 if you want covers quieter.

---

## 3. Work segments

Order is fixed. After each: run on both real samples, show real output, state pass/fail, stop on failure.

### Seg 1 — Config and SR. NO regex (~15 lines + tests)
- **Goal:** `CONFIG` dict and the compiled marker, proven on real lines.
- **Approach:** put `CONFIG` at the top of `classify.py`; a tiny helper compiles `sr_pattern` with `re.IGNORECASE`.
- **Expected:** every real `Name | SR. NO :- n` line (9 product pages plus 4 grid lines) matches exactly once;
  the Matisse grid labels, spec lines and prose never match; the variant table in section 1 behaves as listed.
- **Verify:** run the regex over all 16 real PageInfo records and print match counts per page; unit-test the variants.
- **Size:** small.

### Seg 2 — Signal extraction (~25 lines)
- **Goal:** `get_signals(page_info, config) -> dict` as in the schema.
- **Approach:** `findall` over `lines[].text`; filter `images` by `area_share`; keyword set with word boundaries;
  `.get()` defaults so an error record yields empty signals, not a crash.
- **Expected:** Matisse p3 → 1 label, large image xref 404 at 0.7532, three keywords; Ikat p6 → 4 labels, none large;
  Matisse p1 → no keywords (not "Composition"), largest 0.2643.
- **Verify:** print the signals dict for all 16 pages.
- **Size:** small.

### Seg 3 — Verdict rules and reason codes (~30 lines)
- **Goal:** `classify_page(page_info, config=CONFIG)`.
- **Approach:** the first-match table above, as an if-chain with one reason string per branch (code + sentence
  built from the signals).
- **Expected:** the prediction table above.
- **Verify:** print the per-page verdict for both samples; assert 9 product, none of cover/back/grid/intro among them.
- **Size:** small.

### Seg 4 — Batch helper, summary, fail-loud, review list (~25 lines)
- **Goal:** `classify_pdf(page_infos, config=CONFIG)`.
- **Approach:** map `classify_page` over the pages, count verdicts, compute `product_share`, set `warning`,
  collect `review`. Accepts the `pages` list from `read_pdf.read_pdf(...)`.
- **Expected:** Ikat 5/1/2, Matisse 4/3/1, `warning: null`, review lists Ikat 0 and 7, Matisse 0.
  A synthetic all-skip input sets `warning`.
- **Verify:** print both summaries as JSON; `json.dumps` round-trips.
- **Size:** small.

### Seg 5 — Tests (~110 lines of tests, plus a ~50-line fixture generator)
- **Goal:** tests that run anywhere, plus optional local real-sample tests.
- **Approach:**
  - **Unit tests on hand-built PageInfo dicts** cover every rule row, the regex variants, the keyword boundary
    ("compositions" must not count), an error record, the warning cases, and JSON-serializability. They need no PDF.
  - **`tests/make_fixtures.py`** builds `tests/fixtures/synthetic_catalog.pdf` with PyMuPDF (solid-colour images,
    no client content): cover (full-page image), intro (one 26% image plus prose), grid (4 labels plus 4 small
    images), two product pages, a big image with no SR. NO, an SR. NO with no big image, specs with no SR. NO,
    a no-text page, a back cover. One end-to-end test runs `read_pdf.read_pdf` → `classify_pdf` on it.
  - **Real-sample tests** (`pytest.mark.skipif` on missing `sample_pdfs/`): 9/9 products at the expected indices,
    Ikat p6 and Matisse p2 skip, Matisse p1 not product, covers/back covers not product.
- **Expected:** all green; with `sample_pdfs/` renamed, the real-sample tests skip and the rest pass.
- **Verify:** `python -m pytest -q` both ways.
- **Size:** medium (the largest segment, but mostly data).

### Seg 6 — `__main__` verdict table (~20 lines)
- **Goal:** `python classify.py FILE.pdf` prints one row per page, then the summary and any warning.
- **Approach:** `argparse`, `read_pdf.read_pdf`, `classify_pdf`; columns: page, verdict, reason code, labels,
  largest share. UTF-8 stdout like Part 1. `--json` prints the full result instead. Exit 0 normally; a missing
  or bad PDF reuses Part 1's `ReadError` handling (exit 1). It does **not** stop on `warning`; it prints it to stderr.
- **Expected:** a readable table for each sample.
- **Verify:** run on both real PDFs and paste the tables into the final report.
- **Size:** small.

---

## 4. Edge cases

**Handled:**
- Spacing, case and separator variants of `SR. NO` (section 1).
- Two labels merged into one line by Part 1 (counted by `findall`).
- Name typos and differing names between grid and product page (the name is never compared).
- Printed page numbers differing from PDF indices (only `page_index` is used).
- Text-layer differences, e.g. Matisse back cover hidden text: only measured text is used; the page has no big
  image and no keywords, so it is skip regardless.
- Cover / back cover with a full-page image (≥30%): not product, since no label; uncertain (review).
- Scanned page with no text layer: no labels, so a big image gives `large_image_no_sr_label` (uncertain, not lost).
- Page that failed to read in Part 1: uncertain `page_read_error`.
- Tiny images (logos, bands, thumbnails): below 30%, ignored for the large-image count.
- Grid with large thumbnails (Ikat 2×2 at 17%): fine up to 30%; a 1×1 "grid" would be uncertain, not product,
  unless it also has exactly one label.
- Empty input or zero product pages: `warning` set.

**Not handled (out of scope):**
- **OCR** for scanned catalogs: with no text there is no label, so every page ends in review, and the warning fires.
- **Different marker in a new catalog:** the SR. NO count is 0, nothing is product, `warning` fires. Fix by editing
  `sr_pattern` in config.
- **Two products on one page:** gives two labels. Skip as written, or uncertain with the 1b refinement (Q4).
  Never product.
- **A product whose swatch is under 30% of the page** (e.g. a small swatch on a white page): uncertain, not product.
  Lower `large_image_share` for such a catalog. The Matisse intro at 0.2643 shows how close real pages sit to 30%.
- **One large image drawn twice** (two placements of the same xref): counted as 2, so uncertain.
- **Inline large image (`xref: 0`):** classified product normally; Part 3 must handle extraction by bbox.
- **A real label in an image only** (text baked into pixels): invisible to the classifier.
- **Name check:** a label with an empty name before the separator will not match.

---

## 5. Open questions

1. **Matisse p1 (intro): skip, not uncertain.** Its largest image is 26.4%, under 30%, and the prose has no spec
   keyword (the "compositions" hit is a plain-substring artifact). By your rules it is skip. Options:
   (a) **accept skip** and update the expectation (recommended; an intro page with no label and no specs is not a
   product, and either verdict satisfies "never product"); (b) lower the threshold to 0.25, which makes it uncertain
   but only by a 1.4-point margin; (c) add a rule sending text-heavy pages with an image to review.
2. **Matisse p2 (14-label grid) has no `SR. NO` text.** It is skip via `no_large_image_no_specs`, not
   `multiple_sr_labels`. Fine with that? (Recommended: yes.)
3. **Keyword matching:** word-boundary, case-insensitive, and **any one** keyword counts as "has specs" (so a
   partial spec page is reviewed, not skipped). OK? (Recommended: yes.)
4. **Rule 1b:** several labels plus a large image → uncertain instead of skip, so a two-products-on-a-page layout
   isn't silently skipped. Does not change any real-sample result. Include? (Recommended: yes.) Related: covers
   currently go to review (3 of 16 pages on the samples); say so if you want a quieter rule for them.
5. **Warning floor:** `min_product_share = 0.10`. Real samples are 50–63%. OK, or should it be higher?
6. **Fixture PDF:** commit the small generated `tests/fixtures/synthetic_catalog.pdf` (a few KB, solid colours),
   or generate it at test time into a temp dir and commit only the generator? (Recommended: commit both, so the
   test file is inspectable.)
7. **Repo hygiene (not Part 2, needs your OK):** `sample_pdfs/` is untracked but **not** in `.gitignore`, and the
   untracked `ikat_output.json` / `matisse_output.json` contain text from client PDFs. CLAUDE.md says these must be
   gitignored. Proposed one-line additions to `.gitignore`: `sample_pdfs/` and `*_output.json`. Also, Part 1's
   existing tests read the real samples (they skip when absent), which CLAUDE.md's new rule discourages; I would
   leave them as they are and make all Part 2 tests synthetic-first.
8. **Part 1 changes:** none proposed. (Stated here so you can veto that conclusion.)

---

## 6. What Part 3 will need from the verdicts

For each `product` page: `page_index` and `signals.large_images[0]["xref"]` (exactly one entry by construction).
Part 3 looks up the rest (bbox, `rotation`, `transform`, `smask`) in the same page's PageInfo by `page_index`
and xref, because Part 2 deliberately doesn't copy them.

---

## 7. Implementation notes (2026-10-09)

- Built `classify.py` (128 lines) with the config, regex and signal helper, ordered rule table, batch summary and review list, and CLI. The output schemas and reason codes follow section 2.
- Added unit tests for every rule row, marker variants, two markers on one line, case-insensitive keyword matching and the `compositions` boundary, error records, warning cases, config overrides, and JSON round-tripping.
- Added `tests/make_fixtures.py` and committed-ready `tests/fixtures/synthetic_catalog.pdf` (8,682 bytes) for the end-to-end test. The fixture contains no client content.
- Real sample results matched the predicted table: Ikat 5 product / 1 skip / 2 uncertain; Matisse 4 / 3 / 1. All nine expected product pages were found with zero false positives.
- Pytest with the samples present: 64 passed. With `sample_pdfs/` temporarily renamed and restored: 26 passed, 38 skipped. The existing Part 1 tests were left unchanged.
- Added `sample_pdfs/` and `*_output.json` to `.gitignore`. No client PDFs or generated real-sample JSON were added.
- Tests needed to run outside the restricted filesystem sandbox because pytest-created temporary directories were inaccessible inside it. No implementation rule or threshold changed for this.

---

## Change 1 — Skip unmarked covers and surface large skipped images (implemented)

This section supersedes the earlier rule 3, rule 7, cover predictions, summary and review examples, and related edge-case descriptions above. The earlier sections remain as the record of the original Part 2 implementation.

### Research and decisions

- Checked the current `classify.py`, `tests/test_classify.py`, and the Part 1 PageInfo contract. `get_signals` already provides the label count, keyword list, `largest_image_share`, and large-image placements needed here. `classify_pdf` already builds the summary and review list. Part 1 and the fixture generator need no change.
- Local environment remains Python 3.14.4, PyMuPDF 1.28.2, and pytest 9.1.1. No new API or dependency is needed.
- Q1: accept Matisse p1 as skip. Q2: Matisse p2 skips without a second grid pattern. Q3: keyword matching remains case-insensitive, word-boundary, and any one keyword counts. Q4: keep rule 1b. Q5: keep `min_product_share` at 0.10. Q6: keep both the generator and synthetic PDF committed. Q8: no Part 1 changes. The earlier Q7 repository hygiene change is already implemented.
- The existing first-match order is retained. New rule 3 is `sr_label_count == 0 and not spec_keywords`, regardless of image count, with `skip` and reason code `no_markers`. It precedes rule 6. Remove rule 7 because every zero-label page has either no keywords (rule 3) or keywords (rule 6).

### Work segments

After each implementation segment, run both real PDFs, show their output, state PASS or FAIL against its expected result, and run the pytest suite. Stop on a failure.

1. **Rule change (small).** Replace rule 3's condition and reason code in `classify_page`; remove the rule 7 fallback. Keep rules 0, 1, 1b, 2, 4, 5, and 6 unchanged and in order. **Expected:** Ikat pages 0 and 7 and Matisse page 0 become `skip/no_markers`; Matisse pages 1, 2, and 7 also use `no_markers`. Product pages, Ikat p6, and `specs_no_sr_label` remain as before. **Verify:** run the classifier table on both samples and the rule-row tests.
2. **Batch diagnostics (small).** Add `summary.skipped_with_large_image` as `{"count": n, "pages": [...]}`. Include only skipped pages whose `signals.largest_image_share` is strictly greater than `config["large_image_share"]`; preserve page order and use zero-based `page_index`. Append the count to warning text when product count is zero or product share is below `min_product_share` (including an empty input's zero-product warning). Add the full `signals` dict to each review entry. **Expected:** Ikat diagnostic is `{"count": 2, "pages": [0, 7]}`; Matisse is `{"count": 1, "pages": [0]}`; both warnings remain null and both review lists are empty. **Verify:** run both PDFs and check JSON summary/review output, including an all-skip input with a large image.
3. **Tests and CLI verification (small).** Update every affected unit, synthetic, and real-sample assertion; add checks for large-image boundary, warning count, full review signals, and a synthetic page with spec keywords but no SR. NO. Do not change the fixture PDF or generator unless an existing fixture fails to cover the requested case. The CLI table code needs no change because it prints the reason code from each result. **Expected:** Ikat products 1–5, skips 0/6/7, zero uncertain; Matisse products 3–6, skips 0/1/2/7, zero uncertain. The synthetic specs-only page stays `uncertain/specs_no_sr_label`. **Verify:** pytest with samples present and absent, then print both real verdict tables.

### Edge cases

- **Handled by Change 1:** full-page covers without SR. NO or spec keywords now skip, regardless of image size. The diagnostic makes those skipped large-image pages visible in the summary. A page with any configured spec keyword and no SR. NO remains uncertain even if it has no large image. An error record remains uncertain. A skip at exactly the threshold is excluded from `skipped_with_large_image` because the comparison is strict `>`.
- **Still not handled:** OCR, different catalog marker without a config edit, two products on one page, small product swatches, duplicate large-image placements, inline-image extraction, labels baked into pixels, and empty names. As a deliberate tradeoff of Change 1, an unmarked product page with no visible spec keyword also skips; a low-product warning includes the count of skipped pages with large images for diagnosis.

### Open questions

None for this change. The requested outputs and earlier Q1–Q6/Q8 decisions are fixed above.

### Implementation notes (2026-10-09)

- Replaced rule 3 with `no_markers` regardless of image size and removed rule 7. Rules 0, 1, 1b, 2, 4, 5, and 6 kept their verdicts and reason codes.
- Added `summary.skipped_with_large_image`, appended its count to zero/low-product warnings, and included full signals in review entries. The comparison uses strict `>` against the configured threshold.
- Real results: Ikat 5 product / 3 skip / 0 uncertain, skipped-large pages `[0, 7]`; Matisse 4 / 4 / 0, skipped-large page `[0]`. Review lists are empty. The synthetic specs-only page remains uncertain.
- Verification: 65 pytest tests passed with real samples present; 27 passed and 38 skipped with `sample_pdfs/` temporarily absent. Both CLI verdict tables matched the expected page indices and reason codes. The fixture and Part 1 files were unchanged.
