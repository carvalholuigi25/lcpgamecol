"""Generate HTML pages from the Lighthouse and security audit results.

Reads the summary.json that scripts/lighthouse_audit.py and
scripts/security_audit.py write to tests/reports/<kind>/<timestamp>/ and writes:

    tests/reports/<kind>/<timestamp>/report.html   one page per audit run
    tests/reports/index.html                       every run, newest first, with trends

The pages are self-contained (inline CSS, no scripts from the network), so they
can be opened from disk or attached to a CI run. Both audit scripts call this
module after each run; run it directly to rebuild older runs.

Examples:
    python scripts/audit_report.py
    python scripts/audit_report.py --kind security --run 20261028-095205 --open
    python scripts/audit_report.py --reports-dir tests/reports --open
"""

import argparse
import json
import re
import sys
import webbrowser
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = ROOT_DIR / "tests" / "reports"
KINDS = ["lighthouse", "security"]
RUN_PATTERN = re.compile(r"^\d{8}-\d{6}$")
REPORT_FILE = "report.html"
INDEX_FILE = "index.html"

# Lighthouse's own score bands
SCORE_BANDS = [(90, "good"), (50, "average"), (0, "poor")]
# (good up to, poor from) for each metric, from web.dev's Core Web Vitals guidance
METRIC_THRESHOLDS = {
    "FCP": (1800, 3000),
    "LCP": (2500, 4000),
    "SI": (3400, 5800),
    "TBT": (200, 600),
    "TTFB": (800, 1800),
    "CLS": (0.1, 0.25),
}
METRIC_NAMES = {
    "FCP": "First Contentful Paint",
    "LCP": "Largest Contentful Paint",
    "SI": "Speed Index",
    "TBT": "Total Blocking Time",
    "TTFB": "Server response time",
    "CLS": "Cumulative Layout Shift",
}
SEVERITIES = ["high", "medium", "low"]

STYLES = """
:root {
  color-scheme: light dark;
  --paper: #f4f5ef; --surface: #fffefa; --ink: #202823; --muted: #687268; --line: #dfe4da;
  --good: #1d7a4f; --good-soft: #e1f0e6; --average: #a96a00; --average-soft: #fbefd6;
  --poor: #c0392b; --poor-soft: #f8e1dd; --accent: #245f48;
  --sans: "Segoe UI", system-ui, -apple-system, sans-serif; --mono: ui-monospace, "Cascadia Mono", Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #151d1c; --surface: #202a28; --ink: #edf4f0; --muted: #a6b4ad; --line: #3a4944;
    --good: #6fcf97; --good-soft: #1f3a2c; --average: #f2c14e; --average-soft: #3d3420;
    --poor: #ff8a7a; --poor-soft: #45261f; --accent: #78b89a;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.5 var(--sans); }
main { max-width: 1120px; margin: 0 auto; padding: 32px 16px 64px; }
a { color: var(--accent); }
h1 { margin: 0 0 4px; font-size: 1.9rem; }
h2 { margin: 40px 0 12px; font-size: 1.25rem; }
h3 { margin: 0 0 8px; font-size: 1rem; }
.kicker { margin: 0; color: var(--muted); font: 500 0.75rem var(--mono); letter-spacing: 0.08em; text-transform: uppercase; }
.meta { color: var(--muted); }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.card { padding: 16px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
.card .value { font-size: 2rem; font-weight: 700; line-height: 1.1; }
.card .label { color: var(--muted); font-size: 0.85rem; }
.scores { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 10px; }
.gauge { display: grid; justify-items: center; gap: 4px; width: 76px; text-align: center; font-size: 0.75rem; color: var(--muted); }
.gauge svg { width: 56px; height: 56px; }
.gauge text { font: 700 15px var(--sans); fill: currentColor; }
.gauge-track { stroke: var(--line); }
.good { color: var(--good); } .average { color: var(--average); } .poor { color: var(--poor); }
.pill { display: inline-block; padding: 1px 9px; border-radius: 999px; font: 600 0.75rem var(--mono); text-transform: uppercase; }
.pill.good, .pill.low { background: var(--good-soft); color: var(--good); }
.pill.average, .pill.medium { background: var(--average-soft); color: var(--average); }
.pill.poor, .pill.high { background: var(--poor-soft); color: var(--poor); }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 9px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { color: var(--muted); font: 600 0.75rem var(--mono); letter-spacing: 0.05em; text-transform: uppercase; white-space: nowrap; }
tr:last-child td { border-bottom: 0; }
td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
code { font: 0.85rem var(--mono); overflow-wrap: break-word; }
ul.plain { margin: 0; padding-left: 18px; }
.empty { padding: 18px; border: 1px dashed var(--line); border-radius: 10px; color: var(--muted); }
.bar { display: inline-block; height: 8px; border-radius: 4px; background: currentColor; vertical-align: middle; }
.trend { display: block; width: 100%; max-width: 640px; height: 120px; }
.trend polyline { fill: none; stroke: var(--accent); stroke-width: 2; }
.trend circle { fill: var(--accent); }
.trend line { stroke: var(--line); }
.trend text { fill: var(--muted); font: 11px var(--mono); }
footer { margin-top: 48px; color: var(--muted); font-size: 0.8rem; }
"""


# --- helpers -------------------------------------------------------------------


def run_time(run_name: str) -> datetime:
    return datetime.strptime(run_name, "%Y%m%d-%H%M%S")


def format_run(run_name: str) -> str:
    return run_time(run_name).strftime("%d %b %Y, %H:%M")


def score_band(score: float | None) -> str:
    if score is None:
        return ""
    return next(band for minimum, band in SCORE_BANDS if score >= minimum)


def metric_band(label: str, value: float | None) -> str:
    if value is None or label not in METRIC_THRESHOLDS:
        return ""
    good, poor = METRIC_THRESHOLDS[label]
    return "good" if value <= good else "average" if value < poor else "poor"


def format_metric(label: str, value: float | None) -> str:
    if value is None:
        return "–"
    if label == "CLS":
        return f"{value:.3f}"
    return f"{value / 1000:.2f} s" if value >= 1000 else f"{round(value)} ms"


def gauge(score: float | None, label: str) -> str:
    # A ring filled in proportion to the 0-100 score, coloured by Lighthouse's bands
    radius, circumference = 24, 150.8
    filled = 0 if score is None else circumference * score / 100
    band = score_band(score)
    text = "–" if score is None else str(round(score))
    return (
        f'<div class="gauge"><svg viewBox="0 0 56 56" role="img" aria-label="{escape(label)}: {text}">'
        f'<circle class="gauge-track" cx="28" cy="28" r="{radius}" fill="none" stroke-width="5"/>'
        f'<circle class="{band}" cx="28" cy="28" r="{radius}" fill="none" stroke="currentColor" stroke-width="5" '
        f'stroke-dasharray="{filled:.1f} {circumference}" stroke-linecap="round" transform="rotate(-90 28 28)"/>'
        f'<text class="{band}" x="28" y="33" text-anchor="middle">{text}</text></svg>'
        f"<span>{escape(label)}</span></div>"
    )


def trend_chart(points: list[tuple[str, float]], label: str, maximum: float | None = None) -> str:
    """Line chart of (run name, value) pairs, oldest first."""
    if len(points) < 2:
        return ""
    width, height, pad = 640, 120, 24
    top = maximum if maximum is not None else max(value for _, value in points) or 1
    step = (width - 2 * pad) / (len(points) - 1)
    coords = [
        (pad + index * step, height - pad - (value / top) * (height - 2 * pad))
        for index, (_, value) in enumerate(points)
    ]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3"><title>{escape(format_run(run))}: {value:g}</title></circle>'
        for (x, y), (run, value) in zip(coords, points)
    )
    return (
        f'<svg class="trend" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">'
        f'<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}"/>'
        f'<text x="{pad}" y="14">{escape(label)}</text>'
        f'<text x="{pad}" y="{height - 6}">{escape(format_run(points[0][0]))}</text>'
        f'<text x="{width - pad}" y="{height - 6}" text-anchor="end">{escape(format_run(points[-1][0]))}</text>'
        f"<polyline points=\"{polyline}\"/>{dots}</svg>"
    )


def page(title: str, kicker: str, body: str, back_link: str | None = None) -> str:
    back = f'<p><a href="{escape(back_link)}">← All audit runs</a></p>' if back_link else ""
    generated = datetime.now().strftime("%d %b %Y, %H:%M")
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n<style>{STYLES}</style>\n</head>\n<body>\n<main>\n"
        f'{back}<p class="kicker">{escape(kicker)}</p>\n<h1>{escape(title)}</h1>\n{body}\n'
        f"<footer>Generated by scripts/audit_report.py on {generated}.</footer>\n</main>\n</body>\n</html>\n"
    )


def table(headers: list[str], rows: list[str]) -> str:
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def link(href: str, text: str) -> str:
    return f'<a href="{escape(quote(href))}">{escape(text)}</a>'


def load_summary(run_dir: Path):
    path = run_dir / "summary.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def list_runs(reports_dir: Path, kind: str) -> list[Path]:
    """Run directories with a summary.json, oldest first."""
    kind_dir = reports_dir / kind
    if not kind_dir.is_dir():
        return []
    return sorted(
        path for path in kind_dir.iterdir()
        if path.is_dir() and RUN_PATTERN.match(path.name) and (path / "summary.json").exists()
    )


# --- lighthouse ----------------------------------------------------------------


def lighthouse_scores(result: dict) -> dict[str, float]:
    # Older summaries only stored the performance score
    return result.get("scores") or {"performance": result.get("performance")}


def lighthouse_stats(results: list[dict]) -> dict:
    performance = [result["performance"] for result in results if result.get("performance") is not None]
    return {
        "pages": len({result["page"] for result in results}),
        "audits": len(results),
        "average": round(sum(performance) / len(performance)) if performance else None,
        "worst": min(performance) if performance else None,
    }


def lighthouse_report(run_dir: Path, results: list[dict]) -> str:
    stats = lighthouse_stats(results)
    runs = max((result.get("runs", 1) for result in results), default=1)
    body = [
        f'<p class="meta">{stats["pages"]} page(s), {stats["audits"]} audit(s), '
        f"results averaged over {runs} run(s) each.</p>",
        '<div class="cards">',
        f'<div class="card"><div class="value {score_band(stats["average"])}">{stats["average"] if stats["average"] is not None else "–"}</div>'
        '<div class="label">Average performance score</div></div>',
        f'<div class="card"><div class="value {score_band(stats["worst"])}">{stats["worst"] if stats["worst"] is not None else "–"}</div>'
        '<div class="label">Lowest performance score</div></div>',
        "</div>",
        "<h2>Scores</h2>",
        '<div class="cards">',
    ]
    for result in results:
        gauges = "".join(
            gauge(score, category.replace("-", " ").capitalize())
            for category, score in lighthouse_scores(result).items()
        )
        body.append(
            f'<div class="card"><h3>{escape(result["page"])}</h3>'
            f'<div class="label">{escape(result["form_factor"])}</div><div class="scores">{gauges}</div></div>'
        )
    body.append("</div>")

    body.append("<h2>Metrics</h2>")
    rows = []
    for result in results:
        metrics = {**result.get("metrics_ms", {}), "CLS": result.get("cls")}
        cells = "".join(
            f'<td class="num"><span class="{metric_band(label, metrics.get(label))}">'
            f"{format_metric(label, metrics.get(label))}</span></td>"
            for label in METRIC_NAMES
        )
        rows.append(f"<tr><td><code>{escape(result['page'])}</code></td><td>{escape(result['form_factor'])}</td>{cells}</tr>")
    body.append(table(["Page", "Device", *METRIC_NAMES.values()], rows))

    body.append("<h2>Opportunities</h2>")
    any_opportunities = False
    for result in results:
        failed = sorted(result.get("failed_audits", {}).items(), key=lambda item: item[1].get("score") or 0)
        if not failed:
            continue
        any_opportunities = True
        items = "".join(
            f'<li><span class="pill {score_band((audit.get("score") or 0) * 100)}">{round((audit.get("score") or 0) * 100)}</span> '
            f'{escape(audit["title"])}{" — " + escape(audit["display"]) if audit.get("display") else ""} '
            f'<code class="meta">{escape(audit_id)}</code></li>'
            for audit_id, audit in failed
        )
        body.append(f'<div class="card"><h3>{escape(result["page"])} · {escape(result["form_factor"])}</h3>'
                    f'<ul class="plain">{items}</ul></div><br>')
    if not any_opportunities:
        body.append('<p class="empty">No audits scored below the threshold.</p>')

    raw_reports = sorted(path.name for path in run_dir.glob("*.html") if path.name != REPORT_FILE)
    if raw_reports:
        body.append("<h2>Full Lighthouse reports</h2>")
        body.append('<ul class="plain">' + "".join(f"<li>{link(name, name)}</li>" for name in raw_reports) + "</ul>")

    return page(f"Lighthouse audit · {format_run(run_dir.name)}", "Performance audit", "\n".join(body), f"../../{INDEX_FILE}")


# --- security ------------------------------------------------------------------


def advisory_link(rule: str) -> str:
    """Link pip-audit advisory ids to OSV, leave rule names as text."""
    parts = []
    for part in rule.split():
        if re.match(r"^(GHSA|PYSEC|CVE|OSV)-", part):
            parts.append(link(f"https://osv.dev/vulnerability/{part}", part))
        else:
            parts.append(escape(part))
    return " ".join(parts)


def security_stats(summary: dict) -> dict:
    counts = {severity: 0 for severity in SEVERITIES}
    for finding in summary.get("findings", []):
        counts[finding.get("severity", "low")] = counts.get(finding.get("severity", "low"), 0) + 1
    failed_tools = [name for name, tool in summary.get("tools", {}).items() if tool.get("error")]
    return {"counts": counts, "total": sum(counts.values()), "failed_tools": failed_tools}


def security_report(run_dir: Path, summary: dict) -> str:
    stats = security_stats(summary)
    targets = ", ".join(summary.get("targets", [])) or "."
    body = [f'<p class="meta">Scanned <code>{escape(targets)}</code>.</p>', '<div class="cards">']
    bands = {"high": "poor", "medium": "average", "low": "good"}
    for severity in SEVERITIES:
        count = stats["counts"][severity]
        body.append(
            f'<div class="card"><div class="value {bands[severity] if count else ""}">{count}</div>'
            f'<div class="label">{severity.capitalize()} severity</div></div>'
        )
    body.append("</div>")

    body.append("<h2>Tools</h2>")
    rows = []
    for name, tool in summary.get("tools", {}).items():
        if tool.get("error"):
            status = f'<span class="pill high">error</span> {escape(tool["error"])}'
        elif tool.get("errors"):
            warnings = "".join(f"<li>{escape(str(error))}</li>" for error in tool["errors"])
            status = f'<span class="pill medium">{len(tool["errors"])} warnings</span><ul class="plain">{warnings}</ul>'
        else:
            status = '<span class="pill low">ok</span>'
        raw = run_dir / f"{name}.json"
        rows.append(f"<tr><td>{escape(name)}</td><td>{status}</td>"
                    f"<td>{link(raw.name, raw.name) if raw.exists() else '–'}</td></tr>")
    body.append(table(["Tool", "Status", "Raw output"], rows))

    body.append("<h2>Findings</h2>")
    findings = summary.get("findings", [])
    if not findings:
        body.append('<p class="empty">No findings at or above the minimum severity.</p>')
    else:
        rows = []
        for finding in findings:
            location = finding["file"] + (f":{finding['line']}" if finding.get("line") else "")
            cwe = finding.get("cwe")
            cwe_cell = (link(f"https://cwe.mitre.org/data/definitions/{cwe}.html", f"CWE-{cwe}")
                        if isinstance(cwe, int) else escape(str(cwe or "–")))
            rows.append(
                f'<tr><td><span class="pill {escape(finding["severity"])}">{escape(finding["severity"])}</span></td>'
                f"<td><code>{escape(location)}</code></td>"
                f"<td>{escape(finding['tool'])}<br><code>{advisory_link(finding['rule'])}</code></td>"
                f"<td>{escape(finding['message'])}</td><td>{cwe_cell}</td></tr>"
            )
        body.append(table(["Severity", "Location", "Rule", "Message", "CWE"], rows))

    return page(f"Security audit · {format_run(run_dir.name)}", "Security audit", "\n".join(body), f"../../{INDEX_FILE}")


# --- index ---------------------------------------------------------------------


def index_page(reports_dir: Path) -> str:
    body = []

    lighthouse_runs = [(run, load_summary(run)) for run in list_runs(reports_dir, "lighthouse")]
    lighthouse_runs = [(run, results) for run, results in lighthouse_runs if isinstance(results, list)]
    body.append("<h2>Lighthouse</h2>")
    if not lighthouse_runs:
        body.append('<p class="empty">No Lighthouse runs yet. Run <code>npm run lighthouse</code>.</p>')
    else:
        points = [(run.name, stats["average"]) for run, results in lighthouse_runs
                  if (stats := lighthouse_stats(results))["average"] is not None]
        body.append(trend_chart(points, "Average performance score", maximum=100))
        rows = []
        for run, results in reversed(lighthouse_runs):
            stats = lighthouse_stats(results)
            pages = ", ".join(sorted({result["page"] for result in results}))
            average = stats["average"]
            rows.append(
                f"<tr><td>{link(f'lighthouse/{run.name}/{REPORT_FILE}', format_run(run.name))}</td>"
                f"<td><code>{escape(pages)}</code></td>"
                f'<td class="num"><span class="{score_band(average)}"><span class="bar" style="width:{average or 0}px"></span> {average if average is not None else "–"}</span></td>'
                f'<td class="num"><span class="{score_band(stats["worst"])}">{stats["worst"] if stats["worst"] is not None else "–"}</span></td></tr>'
            )
        body.append(table(["Run", "Pages", "Average performance", "Lowest"], rows))

    security_runs = [(run, load_summary(run)) for run in list_runs(reports_dir, "security")]
    security_runs = [(run, summary) for run, summary in security_runs if isinstance(summary, dict)]
    body.append("<h2>Security</h2>")
    if not security_runs:
        body.append('<p class="empty">No security runs yet. Run <code>npm run security</code>.</p>')
    else:
        points = [(run.name, security_stats(summary)["total"]) for run, summary in security_runs]
        body.append(trend_chart(points, "Findings per run"))
        rows = []
        for run, summary in reversed(security_runs):
            stats = security_stats(summary)
            counts = "".join(
                f'<td class="num"><span class="pill {severity}">{stats["counts"][severity]}</span></td>'
                if stats["counts"][severity] else '<td class="num">0</td>'
                for severity in SEVERITIES
            )
            failed = ", ".join(stats["failed_tools"]) or "–"
            rows.append(
                f"<tr><td>{link(f'security/{run.name}/{REPORT_FILE}', format_run(run.name))}</td>"
                f"{counts}<td>{escape(', '.join(summary.get('tools', {})))}</td><td>{escape(failed)}</td></tr>"
            )
        body.append(table(["Run", "High", "Medium", "Low", "Tools", "Tools that failed"], rows))

    return page("Audit reports", "lcpgamecol / audits", "\n".join(body))


# --- writing -------------------------------------------------------------------


def write_run_report(kind: str, run_dir: Path) -> Path | None:
    """Write report.html for one run directory and return its path."""
    summary = load_summary(run_dir)
    if kind == "lighthouse" and isinstance(summary, list):
        html = lighthouse_report(run_dir, summary)
    elif kind == "security" and isinstance(summary, dict):
        html = security_report(run_dir, summary)
    else:
        return None
    path = run_dir / REPORT_FILE
    path.write_text(html, encoding="utf-8")
    return path


def write_index(reports_dir: Path = DEFAULT_REPORTS_DIR) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / INDEX_FILE
    path.write_text(index_page(reports_dir), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate HTML pages from audit results.")
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR,
                        help="Folder holding the lighthouse/ and security/ runs (default: %(default)s)")
    parser.add_argument("--kind", choices=[*KINDS, "all"], default="all")
    parser.add_argument("--run", help="Only rebuild this run (its timestamp folder name, e.g. 20261028-095205)")
    parser.add_argument("--latest", action="store_true", help="Only rebuild the latest run of each kind")
    parser.add_argument("--open", action="store_true", help="Open the result in the browser")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    kinds = KINDS if args.kind == "all" else [args.kind]
    written = []
    for kind in kinds:
        runs = list_runs(args.reports_dir, kind)
        if args.run:
            runs = [run for run in runs if run.name == args.run]
        elif args.latest:
            runs = runs[-1:]
        for run in runs:
            path = write_run_report(kind, run)
            if path:
                written.append(path)
                print(f"Wrote {path}")

    if args.run and not written:
        print(f"No {' or '.join(kinds)} run named {args.run} in {args.reports_dir}")
        return 1

    index = write_index(args.reports_dir)
    print(f"Wrote {index}")
    if args.open:
        target = written[0] if args.run and written else index
        webbrowser.open(target.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
