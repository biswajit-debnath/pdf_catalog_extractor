// Run with: node --test tests_js/
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { ROOT, runReadPdf } = require("./run_py");

const SAMPLES = path.join(ROOT, "sample_pdfs");
const EXPECTED = path.join(__dirname, "expected");
const skip = !fs.existsSync(SAMPLES) && "sample_pdfs/ missing";

const expected = (name) =>
  JSON.parse(fs.readFileSync(path.join(EXPECTED, `${name}.json`), "utf8"));

for (const name of ["Ikat_sm", "Matisse_sm"]) {
  test(`${name}: stdout JSON matches expected`, { skip }, async () => {
    const { code, stdout } = await runReadPdf([path.join(SAMPLES, `${name}.pdf`)]);
    assert.equal(code, 0);
    assert.deepEqual(JSON.parse(stdout), expected(name));
  });

  test(`${name}: -o writes the same JSON to a file`, { skip }, async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "readpdf-"));
    const out = path.join(dir, "out.json");
    try {
      const { code } = await runReadPdf([path.join(SAMPLES, `${name}.pdf`), "-o", out]);
      assert.equal(code, 0);
      assert.deepEqual(JSON.parse(fs.readFileSync(out, "utf8")), expected(name));
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });
}

test("missing file exits non-zero with error on stderr", async () => {
  const { code, stdout, stderr } = await runReadPdf(["no_such_file.pdf"]);
  assert.notEqual(code, 0);
  assert.equal(stdout, "");
  assert.match(stderr, /^error:/);
});
