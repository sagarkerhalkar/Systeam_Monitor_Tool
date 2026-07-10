
import re
import sys
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
REPORT_DIR = ROOT / "reports" / "final_v2"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_JSON = REPORT_DIR / "SECURITY_SCAN_REPORT.json"
REPORT_MD = REPORT_DIR / "SECURITY_SCAN_REPORT.md"

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "_cleanup_quarantine", "dist", "build", ".pytest_cache", "data"}
TEXT_EXTS = {".py", ".js", ".html", ".css", ".json", ".yml", ".yaml", ".md", ".ps1", ".bat", ".txt", ".env"}

PATTERNS = [
    ("possible_password_assignment", re.compile(r"(?i)\b(password|passwd|pwd)\b\s*[:=]\s*['\"][^'\"]{4,}['\"]")),
    ("possible_token_assignment", re.compile(r"(?i)\b(token|api[_-]?key|secret|client[_-]?secret)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private_key_header", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("github_token_like", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
]

findings = []
files_scanned = 0

for path in ROOT.rglob("*"):
    if path.is_dir():
        continue
    rel = path.relative_to(ROOT)
    if any(part in SKIP_DIRS for part in rel.parts):
        continue
    if path.suffix.lower() not in TEXT_EXTS:
        continue
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    files_scanned += 1
    for idx, line in enumerate(text.splitlines(), start=1):
        for name, pattern in PATTERNS:
            if pattern.search(line):
                findings.append({
                    "file": str(rel).replace("\\", "/"),
                    "line": idx,
                    "pattern": name,
                    "note": "Potential secret. Value intentionally not printed."
                })

data = {
    "time": str(datetime.now()),
    "root": str(ROOT),
    "files_scanned": files_scanned,
    "finding_count": len(findings),
    "findings": findings,
}

REPORT_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")

md = [
    "# Security Scan Report",
    "",
    f"Time: {data['time']}",
    f"Files scanned: {files_scanned}",
    f"Findings: {len(findings)}",
    "",
    "Values are not printed to avoid leaking secrets.",
    ""
]
if findings:
    md.append("| File | Line | Pattern | Note |")
    md.append("|---|---:|---|---|")
    for f in findings:
        md.append(f"| {f['file']} | {f['line']} | {f['pattern']} | {f['note']} |")
else:
    md.append("No high-confidence secret patterns found.")

REPORT_MD.write_text("\n".join(md), encoding="utf-8")
print(f"Security scan completed. Findings: {len(findings)}")
print(f"Report: {REPORT_MD}")
sys.exit(0)
