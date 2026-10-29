"""Run Lighthouse performance audits against the app's pages.

Uses lighthouse-python-plus to drive the Lighthouse CLI (installed locally as a
dev dependency via npm) and prints a per-page summary of scores and Core Web
Vitals. HTML/JSON reports, a summary.json and a report.html (see scripts/audit_report.py)
are written to tests/reports/lighthouse/<timestamp>/.

Examples:
    python scripts/lighthouse_audit.py
    python scripts/lighthouse_audit.py --start-server --repeats 3
    python scripts/lighthouse_audit.py --pages /library --form-factor desktop --min-score 0.9
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from statistics import mean
from uuid import uuid4

from lighthouse import LighthouseRunner
from lighthouse.report import LighthouseReport

import audit_report

ROOT_DIR = Path(__file__).resolve().parent.parent
LOCAL_LIGHTHOUSE_CLI = ROOT_DIR / "node_modules" / "lighthouse" / "cli" / "index.js"
DEFAULT_PAGES = ["/library", "/library/releases"]
DEFAULT_OUTPUT_DIR = ROOT_DIR / "tests" / "reports" / "lighthouse"

# Millisecond metrics read through LighthouseReport.timings
TIMINGS = [
    "first-contentful-paint",
    "largest-contentful-paint",
    "speed-index",
    "total-blocking-time",
    "server-response-time",
]
METRIC_LABELS = {
    "first-contentful-paint": "FCP",
    "largest-contentful-paint": "LCP",
    "speed-index": "SI",
    "total-blocking-time": "TBT",
    "server-response-time": "TTFB",
}
CLS_AUDIT = "cumulative-layout-shift"


def lighthouse_command() -> list[str]:
    if LOCAL_LIGHTHOUSE_CLI.exists():
        return ["node", str(LOCAL_LIGHTHOUSE_CLI)]
    installed = shutil.which("lighthouse")
    if installed:
        return [installed]
    sys.exit("Lighthouse CLI not found. Run `npm install` (or `npm install -g lighthouse`).")


class AppLighthouseRunner(LighthouseRunner):
    """LighthouseRunner with a CLI invocation that works on Windows and Lighthouse 10+.

    The upstream runner writes temp files to /tmp using a name containing ':'
    (invalid on Windows) and passes --emulated-form-factor, which current
    Lighthouse no longer supports, so desktop runs would silently use mobile.
    """

    def __init__(self, url: str, name: str, categories: list[str], **kwargs) -> None:
        self._name = name
        self._categories = categories
        super().__init__(url, **kwargs)

    def _run(self, url, form_factor="mobile", quiet=True, additional_settings=[]):
        self.report_name = self._name
        self.report_path = os.path.join(tempfile.gettempdir(), f"lighthouse_{uuid4().hex}")

        command = lighthouse_command() + [
            url,
            "--chrome-flags=--headless=new --no-sandbox",
            f"--only-categories={','.join(self._categories)}",
            "--output=json",
            "--output=html",
            f"--output-path={self.report_path}",
        ]
        if form_factor == "desktop":
            command.append("--preset=desktop")
        if quiet:
            command.append("--quiet")

        try:
            subprocess.run(command + additional_settings, check=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Lighthouse failed for {url} ({form_factor}), exit code {exc.returncode}")

    def _get_report(self):
        # Upstream reads the JSON with the locale encoding, which garbles text on Windows
        for extension in self._extensions():
            os.makedirs(self.output_dir, exist_ok=True)
            shutil.copy(f"{self.report_path}.report.{extension}",
                        os.path.join(self.output_dir, f"{self.report_name}.{extension}"))
        with open(f"{self.report_path}.report.json", encoding="utf-8") as report_file:
            return LighthouseReport(json.load(report_file), self.timings)

    def _extensions(self) -> list[str]:
        return {"both": ["html", "json"], "html": ["html"], "json": ["json"]}.get(self.output_type, [])


def slugify(page: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", page).strip("-") or "root"


def wait_for_server(url: str, timeout: float) -> bool:
    # urlopen also follows file:// and custom schemes, so only allow http(s)
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"Only http(s) URLs can be audited: {url}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):  # nosec B310 # nosemgrep: dynamic-urllib-use-detected
                return True
        except urllib.error.HTTPError:
            return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    return False


def start_server(base_url: str) -> subprocess.Popen:
    port = urllib.parse.urlparse(base_url).port or 8000
    command = [sys.executable, "-m", "uvicorn", "main:app", "--port", str(port)]
    env_file = ROOT_DIR / "config.env"
    if env_file.exists():
        command += ["--env-file", str(env_file)]
    print(f"Starting server: {' '.join(command)}")
    return subprocess.Popen(command, cwd=ROOT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def audit_page(url: str, page: str, form_factor: str, args, output_dir: Path) -> dict:
    scores, timings, cls_values = [], {key: [] for key in TIMINGS}, []
    category_scores = {category: [] for category in args.categories}
    failed = {}

    for run in range(1, args.repeats + 1):
        print(f"  {form_factor:<7} run {run}/{args.repeats} ...", flush=True)
        report = AppLighthouseRunner(
            url,
            name=f"{slugify(page)}_{form_factor}_run{run}",
            categories=args.categories,
            form_factor=form_factor,
            quiet=not args.verbose,
            timings=TIMINGS,
            output_type=args.output,
            output_dir=str(output_dir),
        ).report
        if report is None:
            raise RuntimeError(f"No report produced for {url} ({form_factor})")

        scores.append(report.score.get("performance") or 0)
        for category in args.categories:
            category_scores[category].append(report.score.get(category) or 0)
        for key, value in report.timings.items():
            timings[key].append(value.total_seconds() * 1000)

        perf_audits = report.audits(args.audit_threshold)["performance"]
        for audit in perf_audits.passed + perf_audits.failed:
            if audit.id == CLS_AUDIT and audit.numval is not None:
                cls_values.append(audit.numval)
        for audit in perf_audits.failed:
            failed[audit.id] = {"title": audit.title, "score": audit.score, "display": audit.display}

    return {
        "page": page,
        "url": url,
        "form_factor": form_factor,
        "runs": args.repeats,
        "performance": round(mean(scores) * 100),
        "scores": {category: round(mean(values) * 100) for category, values in category_scores.items()},
        "metrics_ms": {METRIC_LABELS[k]: round(mean(v)) for k, v in timings.items() if v},
        "cls": round(mean(cls_values), 3) if cls_values else None,
        "failed_audits": failed,
    }


def print_summary(results: list[dict], min_score: int | None, max_failed: int) -> None:
    headers = ["Page", "Device", "Perf"] + list(METRIC_LABELS.values()) + ["CLS"]
    rows = []
    for result in results:
        metrics = result["metrics_ms"]
        rows.append(
            [result["page"], result["form_factor"], str(result["performance"])]
            + [f"{metrics[label]} ms" if label in metrics else "-" for label in METRIC_LABELS.values()]
            + [str(result["cls"]) if result["cls"] is not None else "-"]
        )
    widths = [max(len(str(cell)) for cell in column) for column in zip(headers, *rows)]

    print()
    print("  ".join(header.ljust(width) for header, width in zip(headers, widths)))
    print("  ".join("-" * width for width in widths))
    for result, row in zip(results, rows):
        flag = " <" if min_score is not None and result["performance"] < min_score else ""
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)) + flag)

    for result in results:
        failed = sorted(result["failed_audits"].items(), key=lambda item: item[1]["score"] or 0)
        if not failed:
            continue
        print(f"\n{result['page']} ({result['form_factor']}) - opportunities:")
        for audit_id, audit in failed[:max_failed]:
            display = f" ({audit['display']})" if audit["display"] else ""
            print(f"  - {audit['title']}{display} [{audit_id}]")
        if len(failed) > max_failed:
            print(f"  ... and {len(failed) - max_failed} more")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Lighthouse performance audits against the app.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="App base URL (default: %(default)s)")
    parser.add_argument("--pages", nargs="+", default=DEFAULT_PAGES, help="Page paths to audit (default: %(default)s)")
    parser.add_argument("--form-factor", choices=["mobile", "desktop", "both"], default="both")
    parser.add_argument("--repeats", type=int, default=1, help="Runs per page/device, results are averaged")
    parser.add_argument("--categories", nargs="+", default=["performance"],
                        choices=["performance", "accessibility", "best-practices", "seo"])
    parser.add_argument("--output", choices=["both", "html", "json", "none"], default="both",
                        help="Lighthouse report files to keep (default: %(default)s)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--audit-threshold", type=float, default=0.9,
                        help="Audits scoring below this (0-1) are listed as opportunities")
    parser.add_argument("--max-failed", type=int, default=10, help="Opportunities to print per page/device")
    parser.add_argument("--min-score", type=int, help="Exit with code 1 if any performance score (0-100) is below this")
    parser.add_argument("--start-server", action="store_true", help="Start uvicorn for the duration of the audit")
    parser.add_argument("--verbose", action="store_true", help="Show Lighthouse CLI output")
    parser.add_argument("--no-html", action="store_true", help="Skip the report.html page and the reports index")
    args = parser.parse_args()
    if "performance" not in args.categories:
        args.categories.insert(0, "performance")
    return args


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    form_factors = ["mobile", "desktop"] if args.form_factor == "both" else [args.form_factor]
    output_dir = args.output_dir / datetime.now().strftime("%Y%m%d-%H%M%S")

    server = start_server(base_url) if args.start_server else None
    try:
        if not wait_for_server(base_url + args.pages[0], timeout=30 if server else 3):
            print(f"App is not reachable at {base_url}. Start it with `npm run startapp` or pass --start-server.")
            return 2

        results = []
        for page in args.pages:
            url = base_url + page
            print(f"Auditing {url}")
            for form_factor in form_factors:
                results.append(audit_page(url, page, form_factor, args, output_dir))
    finally:
        if server:
            server.terminate()
            server.wait(timeout=10)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print_summary(results, args.min_score, args.max_failed)
    print(f"\nReports written to {output_dir}")

    if args.min_score is not None and any(result["performance"] < args.min_score for result in results):
        print(f"FAILED: performance score below {args.min_score}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
