#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Create a responsive HTML dashboard from a Coverage.py JSON report.

Usage:
  bash coverage-report.sh [input.json] [output.html]

Defaults:
  input.json   mycoverage/coverage.json
  output.html  mycoverage/coverage-report.html

Generate the input report first, for example:
  python -m coverage json --rcfile=mycoverage/.coveragerc -o mycoverage/coverage.json
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if (( $# > 2 )); then
  usage >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
input="${1:-$script_dir/coverage.json}"
output="${2:-$script_dir/coverage-report.html}"

if [[ ! -f "$input" ]]; then
  printf 'Error: coverage JSON not found: %s\n' "$input" >&2
  printf 'Generate it with: python -m coverage json -o %q\n' "$input" >&2
  exit 1
fi

python_command="${PYTHON:-python3}"
if ! command -v "$python_command" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    python_command=python
  else
    printf 'Error: Python 3 is required to render the report.\n' >&2
    exit 1
  fi
fi

python_input="$input"
python_output="$output"
if [[ "$python_command" == *.exe ]]; then
  if command -v wslpath >/dev/null 2>&1; then
  python_input="$(wslpath -w "$input")"
  python_output="$(wslpath -w "$output")"
  elif command -v cygpath >/dev/null 2>&1; then
  python_input="$(cygpath -w "$input")"
  python_output="$(cygpath -w "$output")"
  else
  printf 'Error: cannot convert shell paths for Windows Python (wslpath/cygpath not found).\n' >&2
  exit 1
  fi
fi

"$python_command" - "$python_input" "$python_output" <<'PY'
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def compact_ranges(lines):
    if not lines:
        return "—"

    lines = sorted(set(lines))
    ranges = []
    start = previous = lines[0]
    for line in lines[1:]:
        if line != previous + 1:
            ranges.append((start, previous))
            start = line
        previous = line
    ranges.append((start, previous))
    return ", ".join(
        str(first) if first == last else f"{first}–{last}"
        for first, last in ranges
    )


def percentage(value):
    return max(0.0, min(100.0, float(value or 0)))


def coverage_class(value):
    if value == 100:
        return "highgold"
    if value >= 70 and value < 100:
        return "high"
    if value >= 50 and value < 70:
        return "medium"
    return "low"


source, destination = map(Path, sys.argv[1:3])
try:
    report = json.loads(source.read_text(encoding="utf-8"))
    summaries = report["totals"]
    files = report["files"]
except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
    print(f"Error: invalid Coverage.py JSON report ({error}).", file=sys.stderr)
    raise SystemExit(1)

rows = []
for name, info in sorted(files.items()):
    summary = info.get("summary", {})
    covered = percentage(summary.get("percent_covered", 0))
    statements = int(summary.get("num_statements", 0))
    missed = int(summary.get("missing_lines", 0))
    branches = int(summary.get("num_branches", 0))
    covered_branches = int(summary.get("covered_branches", 0))
    branch_percent = (
        percentage(100 * covered_branches / branches) if branches else None
    )
    safe_name = html.escape(str(name), quote=True)
    rows.append(
        f"""<tr data-name="{safe_name.lower()}" data-coverage="{covered:.3f}"
                data-missed="{missed}">
          <td class="file-cell"><span class="file-icon" aria-hidden="true">⌘</span>
              <span title="{safe_name}">{safe_name}</span></td>
          <td class="coverage-cell">
            <div class="coverage-value {coverage_class(covered)}">{covered:.1f}%</div>
            <div class="meter" role="img" aria-label="{covered:.1f}% coverage">
              <span class="{coverage_class(covered)}" style="width:{covered:.3f}%"></span>
            </div>
          </td>
          <td data-label="Statements">{statements:,}</td>
          <td data-label="Missing">{missed:,}</td>
          <td data-label="Branches">{
              f"{covered_branches:,} / {branches:,}" if branches else "—"
          }</td>
          <td class="missing-lines" data-label="Missing lines">{
              html.escape(compact_ranges(info.get("missing_lines", [])))
          }</td>
        </tr>"""
    )

total_coverage = percentage(summaries.get("percent_covered", 0))
total_statements = int(summaries.get("num_statements", 0))
covered_statements = int(summaries.get("covered_lines", 0))
missing_statements = int(summaries.get("missing_lines", 0))
total_branches = int(summaries.get("num_branches", 0))
covered_branches = int(summaries.get("covered_branches", 0))
branch_coverage = (
    f"{100 * covered_branches / total_branches:.1f}%"
    if total_branches
    else "N/A"
)
generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Coverage report</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172033;
      --muted: #68738a;
      --line: #e7eaf1;
      --surface: #fff;
      --canvas: #f5f7fb;
      --accent: #6258e8;
      --gold: #FFD700;
      --green: #138a62;
      --yellow: #b77913;
      --red: #d2495a;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--canvas); color: var(--ink); }}
    .shell {{ width: min(1180px, calc(100% - 40px)); margin: 0 auto; padding: 42px 0 56px; }}
    .topline {{ display: flex; align-items: center; gap: 12px; color: var(--accent); font-size: .78rem; font-weight: 750; letter-spacing: .11em; text-transform: uppercase; }}
    .topline::before {{ content: ""; width: 9px; height: 9px; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 5px #6258e81c; }}
    h1 {{ margin: 12px 0 8px; font-size: clamp(2rem, 5vw, 3.25rem); letter-spacing: -.055em; line-height: 1.05; }}
    .subtitle {{ margin: 0; color: var(--muted); }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 30px 0 26px; }}
    .card {{ min-width: 0; padding: 20px; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; box-shadow: 0 8px 24px #19213a08; }}
    .card-label {{ color: var(--muted); font-size: .78rem; font-weight: 650; }}
    .card-value {{ margin-top: 8px; font-size: clamp(1.45rem, 3vw, 2rem); font-weight: 760; letter-spacing: -.04em; }}
    .card-note {{ margin-top: 5px; color: var(--muted); font-size: .78rem; }}
    .hero {{ display: flex; align-items: center; justify-content: space-between; gap: 22px; padding: 22px 24px; }}
    .hero .card-value {{ font-size: 2.15rem; }}
    .hero-meter {{ width: min(46%, 410px); height: 12px; overflow: hidden; background: #eceef6; border-radius: 99px; }}
    .hero-meter span {{ display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #7166f5, #23b68a, var(--gold)); }}
    .toolbar {{ display: flex; align-items: center; justify-content: space-between; gap: 14px; margin: 30px 0 14px; }}
    h2 {{ margin: 0; font-size: 1.18rem; letter-spacing: -.02em; }}
    .search {{ width: min(330px, 100%); padding: 11px 14px; color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: 10px; font: inherit; outline: none; }}
    .search:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px #6258e81e; }}
    .table-wrap {{ overflow: hidden; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; box-shadow: 0 8px 24px #19213a08; }}
    table {{ width: 100%; border-collapse: collapse; text-align: left; }}
    th {{ padding: 13px 16px; color: var(--muted); background: #fafbfe; font-size: .7rem; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; white-space: nowrap; }}
    th button {{ padding: 0; color: inherit; background: none; border: 0; font: inherit; letter-spacing: inherit; text-transform: inherit; cursor: pointer; }}
    td {{ padding: 15px 16px; border-top: 1px solid var(--line); font-size: .88rem; vertical-align: middle; }}
    tbody tr:hover {{ background: #fafaff; }}
    .file-cell {{ max-width: 310px; font-weight: 650; }}
    .file-cell span:last-child {{ display: inline-block; max-width: 270px; overflow: hidden; text-overflow: ellipsis; vertical-align: middle; white-space: nowrap; }}
    .file-icon {{ margin-right: 8px; color: #9aa3b6; }}
    .coverage-cell {{ min-width: 125px; }}
    .coverage-value {{ margin-bottom: 7px; font-weight: 750; }}
    .highgold {{ color: var(--gold); }} .high {{ color: var(--green); }} .medium {{ color: var(--yellow); }} .low {{ color: var(--red); }}
    .meter {{ height: 6px; overflow: hidden; background: #edf0f5; border-radius: 99px; }}
    .meter span {{ display: block; height: 100%; border-radius: inherit; }}
    .meter span.highgold {{ background: var(--gold); }} .meter span.high {{ background: var(--green); }} .meter span.medium {{ background: #e4a333; }} .meter span.low {{ background: var(--red); }}
    .missing-lines {{ max-width: 230px; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .76rem; }}
    .empty {{ display: none; padding: 32px; color: var(--muted); text-align: center; }}
    footer {{ margin-top: 18px; color: var(--muted); font-size: .75rem; text-align: right; }}
    @media (max-width: 850px) {{
      .summary {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .table-wrap {{ overflow-x: auto; }}
      table {{ min-width: 760px; }}
    }}
    @media (max-width: 560px) {{
      .shell {{ width: min(100% - 26px, 1180px); padding: 28px 0 36px; }}
      .summary {{ gap: 10px; margin: 20px 0; }}
      .card {{ padding: 15px; border-radius: 13px; }}
      .hero {{ align-items: flex-start; flex-direction: column; gap: 14px; }}
      .hero-meter {{ width: 100%; }}
      .toolbar {{ align-items: stretch; flex-direction: column; }}
      .search {{ width: 100%; }}
    }}
    @media (prefers-reduced-motion: no-preference) {{
      .card, .table-wrap {{ animation: rise .45s ease both; }}
      @keyframes rise {{ from {{ opacity: 0; transform: translateY(7px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <div class="topline">Code quality</div>
    <h1>Coverage report</h1>
    <p class="subtitle">A clear view of what your tests exercise and where coverage can improve.</p>

    <section class="summary" aria-label="Coverage summary">
      <article class="card hero">
        <div><div class="card-label">Overall coverage</div>
          <div class="card-value {coverage_class(total_coverage)}">{total_coverage:.1f}%</div>
          <div class="card-note">Across {len(files):,} files</div></div>
        <div class="hero-meter" role="img" aria-label="{total_coverage:.1f}% overall coverage">
          <span style="width:{total_coverage:.3f}%"></span></div>
      </article>
      <article class="card"><div class="card-label">Statements covered</div>
        <div class="card-value">{covered_statements:,} <span style="color:#9aa3b6;font-size:.95rem;font-weight:550">/ {total_statements:,}</span></div>
        <div class="card-note">{missing_statements:,} statements missed</div></article>
      <article class="card"><div class="card-label">Branch coverage</div>
        <div class="card-value">{branch_coverage}</div>
        <div class="card-note">{covered_branches:,} of {total_branches:,} branches covered</div></article>
    </section>

    <section aria-labelledby="files-heading">
      <div class="toolbar"><h2 id="files-heading">File breakdown</h2>
        <input class="search" id="filter" type="search" placeholder="Filter files…" aria-label="Filter files"></div>
      <div class="table-wrap"><table>
        <thead><tr>
          <th><button type="button" data-sort="name">File ↕</button></th>
          <th><button type="button" data-sort="coverage">Coverage ↕</button></th>
          <th>Statements</th><th><button type="button" data-sort="missed">Missing ↕</button></th>
          <th>Branches</th><th>Missing lines</th>
        </tr></thead>
        <tbody id="files">{"".join(rows)}</tbody>
      </table><div class="empty" id="empty">No files match your filter.</div></div>
    </section>
    <footer>Generated {generated} · Source: {html.escape(source.name, quote=True)}</footer>
  </main>
  <script>
    const body = document.querySelector("#files");
    const filter = document.querySelector("#filter");
    const empty = document.querySelector("#empty");
    const rows = () => Array.from(body.rows);
    filter.addEventListener("input", () => {{
      const query = filter.value.trim().toLowerCase();
      let visible = 0;
      rows().forEach(row => {{
        const show = row.dataset.name.includes(query);
        row.hidden = !show;
        if (show) visible++;
      }});
      empty.style.display = visible ? "none" : "block";
    }});
    document.querySelectorAll("[data-sort]").forEach(button => {{
      let ascending = true;
      button.addEventListener("click", () => {{
        const key = button.dataset.sort;
        const field = key === "name" ? "name" : key === "coverage" ? "coverage" : "missed";
        const sorted = rows().sort((a, b) => {{
          const left = a.dataset[field], right = b.dataset[field];
          const result = key === "name" ? left.localeCompare(right) : Number(left) - Number(right);
          return ascending ? result : -result;
        }});
        sorted.forEach(row => body.appendChild(row));
        ascending = !ascending;
      }});
    }});
  </script>
</body>
</html>
"""

try:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
except OSError as error:
    print(f"Error: could not write {destination}: {error}", file=sys.stderr)
    raise SystemExit(1)

print(f"Responsive coverage report written to {destination}")
PY
