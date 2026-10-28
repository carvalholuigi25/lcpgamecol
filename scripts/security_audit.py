"""Run security audits (Bandit, Semgrep and pip-audit) against the codebase.

Bandit checks the Python sources for common security issues; Semgrep runs
registry rulesets (Python, FastAPI, secrets, ...) across Python, JS and HTML;
pip-audit checks the installed Python dependencies for known vulnerabilities.
Findings from all tools are normalised to a single severity scale and printed
as one summary. Raw tool output and a summary.json are written to
tests/reports/security/<timestamp>/.

Examples:
    python scripts/security_audit.py
    python scripts/security_audit.py --tools bandit --min-severity medium
    python scripts/security_audit.py --tools pip-audit --requirements requirements.txt
    python scripts/security_audit.py --fail-on high
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT_DIR / "tests" / "reports" / "security"
REQUIREMENTS_FILE = ROOT_DIR / "requirements.txt"
DEFAULT_TARGETS = ["."]
DEFAULT_SEMGREP_CONFIGS = ["p/python", "p/fastapi", "p/security-audit", "p/secrets", "p/javascript"]
EXCLUDES = [
    ".venv", "node_modules", "__pycache__", ".pytest_cache", ".git",
    "mycoverage", "tests/reports", "public/styles/css",
]
# Test code is full of asserts and fixture secrets, so it is skipped unless --include-tests
TEST_DIRS = ["tests"]

SEVERITIES = ["low", "medium", "high"]
# Semgrep severities mapped onto Bandit's low/medium/high scale
SEMGREP_SEVERITY = {"INFO": "low", "WARNING": "medium", "ERROR": "high"}
# pip-audit reports no severity; a published vulnerability in a dependency is treated as high
PIP_AUDIT_SEVERITY = "high"


def tool_command(name: str) -> list[str] | None:
    """Prefer the tool installed next to the running interpreter (the venv)."""
    scripts_dir = Path(sys.executable).parent
    for candidate in (scripts_dir / f"{name}.exe", scripts_dir / name):
        if candidate.exists():
            return [str(candidate)]
    installed = shutil.which(name)
    return [installed] if installed else None


def utf8_env() -> dict:
    # Both tools print/read files with the locale encoding on Windows otherwise
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def run_bandit(args, output_dir: Path) -> dict:
    command = tool_command("bandit")
    if command is None:
        return {"tool": "bandit", "error": "Bandit not found. Run `pip install bandit`."}

    report_path = output_dir / "bandit.json"
    excludes = EXCLUDES + ([] if args.include_tests else TEST_DIRS)
    command += [
        "-r", *args.targets,
        "-x", ",".join(f"./{path}" for path in excludes),
        "-f", "json",
        "-o", str(report_path),
        "-q",
    ]
    print(f"Running Bandit on {', '.join(args.targets)} ...", flush=True)
    # Bandit exits 1 when it finds issues, so only a missing report means failure
    completed = subprocess.run(command, cwd=ROOT_DIR, env=utf8_env(), capture_output=True, text=True)
    if not report_path.exists():
        return {"tool": "bandit", "error": f"Bandit failed (exit {completed.returncode}): {completed.stderr.strip()}"}

    report = json.loads(report_path.read_text(encoding="utf-8"))
    findings = [
        {
            "tool": "bandit",
            "severity": issue["issue_severity"].lower(),
            "confidence": issue["issue_confidence"].lower(),
            "rule": f"{issue['test_id']} {issue['test_name']}",
            "file": relative_path(issue["filename"]),
            "line": issue["line_number"],
            "message": issue["issue_text"],
            "cwe": (issue.get("issue_cwe") or {}).get("id"),
        }
        for issue in report.get("results", [])
    ]
    errors = [f"{relative_path(error['filename'])}: {error['reason']}" for error in report.get("errors", [])]
    return {"tool": "bandit", "findings": findings, "errors": errors}


def run_semgrep(args, output_dir: Path) -> dict:
    command = tool_command("semgrep")
    if command is None:
        return {"tool": "semgrep", "error": "Semgrep not found. Run `pip install semgrep`."}

    report_path = output_dir / "semgrep.json"
    command += ["scan", "--json", f"--output={report_path}", "--metrics=off", "--quiet"]
    for config in args.semgrep_configs:
        command += ["--config", config]
    for path in EXCLUDES:
        command += ["--exclude", path]
    for path in [] if args.include_tests else TEST_DIRS:
        command += ["--exclude", path]
    command += args.targets

    print(f"Running Semgrep ({', '.join(args.semgrep_configs)}) ...", flush=True)
    # Semgrep exits 1 when blocking findings exist; >1 is a real error
    completed = subprocess.run(command, cwd=ROOT_DIR, env=utf8_env(), capture_output=True, text=True)
    if completed.returncode > 1 or not report_path.exists():
        detail = completed.stderr.strip().splitlines()[-1:] or [""]
        return {"tool": "semgrep", "error": f"Semgrep failed (exit {completed.returncode}): {detail[0]}"}

    report = json.loads(report_path.read_text(encoding="utf-8"))
    findings = []
    for result in report.get("results", []):
        extra = result.get("extra", {})
        metadata = extra.get("metadata", {})
        cwe = metadata.get("cwe")
        findings.append({
            "tool": "semgrep",
            "severity": SEMGREP_SEVERITY.get(extra.get("severity", "").upper(), "low"),
            "confidence": str(metadata.get("confidence", "")).lower() or None,
            "rule": result["check_id"].rsplit(".", 1)[-1],
            "rule_id": result["check_id"],
            "file": relative_path(result["path"]),
            "line": result["start"]["line"],
            "message": " ".join(extra.get("message", "").split()),
            "cwe": cwe[0] if isinstance(cwe, list) and cwe else cwe,
        })
    errors = [error.get("message", str(error)).strip() for error in report.get("errors", [])]
    return {"tool": "semgrep", "findings": findings, "errors": errors}


def run_pip_audit(args, output_dir: Path) -> dict:
    command = tool_command("pip-audit")
    if command is None:
        return {"tool": "pip-audit", "error": "pip-audit not found. Run `pip install pip-audit`."}

    report_path = output_dir / "pip-audit.json"
    command += ["--format", "json", f"--output={report_path}", "--progress-spinner", "off"]
    if args.requirements:
        command += ["--requirement", str(args.requirements)]
        source = f"{args.requirements}"
    else:
        source = "installed packages"
    # Audit the interpreter running this script, not whichever venv pip-audit guesses
    env = {**utf8_env(), "PIPAPI_PYTHON_LOCATION": sys.executable}

    print(f"Running pip-audit on {source} ...", flush=True)
    # pip-audit exits 1 when vulnerabilities are found, so only a missing report means failure
    completed = subprocess.run(command, cwd=ROOT_DIR, env=env, capture_output=True, text=True)
    if not report_path.exists():
        detail = completed.stderr.strip().splitlines()[-1:] or [""]
        return {"tool": "pip-audit", "error": f"pip-audit failed (exit {completed.returncode}): {detail[0]}"}

    report = json.loads(report_path.read_text(encoding="utf-8"))
    requirement_lines = requirement_line_numbers(args.requirements or REQUIREMENTS_FILE)
    findings, errors, seen = [], [], set()
    for dependency in report.get("dependencies", []):
        if "skip_reason" in dependency:
            errors.append(f"{dependency['name']}: {dependency['skip_reason']}")
            continue
        line = requirement_lines.get(normalize_package(dependency["name"]))
        for vuln in dependency.get("vulns", []):
            # pip-audit can list the same advisory twice when it comes from several sources
            if (dependency["name"], vuln["id"]) in seen:
                continue
            seen.add((dependency["name"], vuln["id"]))
            fixes = ", ".join(vuln.get("fix_versions", [])) or "no fix available"
            aliases = [alias for alias in vuln.get("aliases", []) if alias.startswith("CVE-")]
            findings.append({
                "tool": "pip-audit",
                "severity": PIP_AUDIT_SEVERITY,
                "confidence": None,
                "rule": " ".join([vuln["id"], *aliases]),
                # Transitive dependencies aren't listed in requirements.txt
                "file": relative_path(str(args.requirements or REQUIREMENTS_FILE)) if line else "(indirect)",
                "line": line,
                "message": f"{dependency['name']} {dependency['version']} is vulnerable (fixed in: {fixes})",
                "cwe": None,
            })
    return {"tool": "pip-audit", "findings": findings, "errors": errors}


def normalize_package(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_line_numbers(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    lines = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if match:
            lines[normalize_package(match.group(1))] = number
    return lines


def relative_path(path: str) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return Path(path).as_posix()


def severity_rank(severity: str) -> int:
    return SEVERITIES.index(severity) if severity in SEVERITIES else 0


def print_summary(results: list[dict], findings: list[dict], max_findings: int) -> None:
    headers = ["Tool", "High", "Medium", "Low", "Status"]
    rows = []
    for result in results:
        counts = Counter(finding["severity"] for finding in result.get("findings", []))
        status = "error" if "error" in result else (f"{len(result['errors'])} warnings" if result["errors"] else "ok")
        rows.append([result["tool"], str(counts["high"]), str(counts["medium"]), str(counts["low"]), status])
    widths = [max(len(str(cell)) for cell in column) for column in zip(headers, *rows)]

    print()
    print("  ".join(header.ljust(width) for header, width in zip(headers, widths)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)))

    for result in results:
        if "error" in result:
            print(f"\n{result['tool']}: {result['error']}")

    if not findings:
        return
    print(f"\nFindings ({len(findings)}):")
    for finding in findings[:max_findings]:
        cwe = f" CWE-{finding['cwe']}" if isinstance(finding["cwe"], int) else ""
        location = f"{finding['file']}:{finding['line']}" if finding["line"] else finding["file"]
        print(f"  [{finding['severity'].upper():<6}] {location}  "
              f"{finding['tool']}:{finding['rule']}{cwe}")
        print(f"           {finding['message']}")
    if len(findings) > max_findings:
        print(f"  ... and {len(findings) - max_findings} more (see summary.json)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Bandit, Semgrep and pip-audit security audits.")
    parser.add_argument("--tools", nargs="+", choices=["bandit", "semgrep", "pip-audit"],
                        default=["bandit", "semgrep", "pip-audit"])
    parser.add_argument("--targets", nargs="+", default=DEFAULT_TARGETS,
                        help="Paths to scan, relative to the project root (default: %(default)s)")
    parser.add_argument("--semgrep-configs", nargs="+", default=DEFAULT_SEMGREP_CONFIGS,
                        help="Semgrep rulesets or local rule files (default: %(default)s)")
    parser.add_argument("--requirements", type=Path,
                        help="Have pip-audit check this requirements file instead of the installed packages")
    parser.add_argument("--include-tests", action="store_true", help="Also scan the tests/ directory")
    parser.add_argument("--min-severity", choices=SEVERITIES, default="low",
                        help="Hide findings below this severity (default: %(default)s)")
    parser.add_argument("--fail-on", choices=SEVERITIES,
                        help="Exit with code 1 if any finding is at or above this severity")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-findings", type=int, default=50, help="Findings to print (default: %(default)s)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir / datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    runners = {"bandit": run_bandit, "semgrep": run_semgrep, "pip-audit": run_pip_audit}
    results = [runners[tool](args, output_dir) for tool in args.tools]

    all_findings = [finding for result in results for finding in result.get("findings", [])]
    min_rank = severity_rank(args.min_severity)
    findings = sorted(
        (finding for finding in all_findings if severity_rank(finding["severity"]) >= min_rank),
        key=lambda finding: (-severity_rank(finding["severity"]), finding["file"], finding["line"] or 0),
    )
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "targets": args.targets,
        "tools": {
            result["tool"]: {key: value for key, value in result.items() if key not in ("tool", "findings")}
            for result in results
        },
        "counts": dict(Counter(finding["severity"] for finding in findings)),
        "findings": findings,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print_summary(results, findings, args.max_findings)
    print(f"\nReports written to {output_dir}")

    if args.fail_on and any(severity_rank(finding["severity"]) >= severity_rank(args.fail_on) for finding in all_findings):
        print(f"FAILED: findings at or above {args.fail_on} severity")
        return 1
    if any("error" in result for result in results):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
