const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const SCRIPT = path.join(ROOT, "read_pdf.py");

function findPython() {
  if (process.env.PYTHON) return process.env.PYTHON;
  const venv = process.platform === "win32"
    ? path.join(ROOT, ".venv", "Scripts", "python.exe")
    : path.join(ROOT, ".venv", "bin", "python");
  if (fs.existsSync(venv)) return venv;
  return process.platform === "win32" ? "python" : "python3";
}

// Runs read_pdf.py in a child process; resolves { code, stdout, stderr }.
function runReadPdf(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(findPython(), [SCRIPT, ...args], { cwd: ROOT });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8").on("data", (d) => (stdout += d));
    child.stderr.setEncoding("utf8").on("data", (d) => (stderr += d));
    child.on("error", reject);
    child.on("close", (code) => resolve({ code, stdout, stderr }));
  });
}

module.exports = { ROOT, runReadPdf };
