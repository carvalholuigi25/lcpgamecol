"""Run the test suite with coverage and print a readable, colored report.

Usage:
    python mycoverage/coverage_report.py                  # run tests + terminal report
    python mycoverage/coverage_report.py --html --open    # also build mycoverage/htmlcov/ and open it
    python mycoverage/coverage_report.py --fail-under 90  # exit 1 if total < 90%
    python mycoverage/coverage_report.py --no-run         # report on existing mycoverage/.coverage
    python mycoverage/coverage_report.py -- -k auth -x    # extra args after -- go to pytest
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

COVERAGE_DIR = Path(__file__).resolve().parent
ROOT = COVERAGE_DIR.parent
CONFIG = COVERAGE_DIR / ".coveragerc"
BAR_WIDTH = 20

# --- colors -----------------------------------------------------------------

USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
if os.name == "nt":
    os.system("")  # enables ANSI escape sequences in the Windows console
    sys.stdout.reconfigure(encoding="utf-8")


def paint(text, *codes):
    if not USE_COLOR or not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


BOLD, DIM = "1", "2"
RED, GREEN, YELLOW, CYAN, MAGENTA, GOLD = "31", "32", "33", "36", "35", "38;5;214"


def grade_color(percent, target):
    if percent == 100:
        return GOLD
    else:
        if (percent - 30) >= target:
            return GREEN
        if (percent - 40) >= target:
            return YELLOW
        if (percent - 50) >= target:
            return CYAN
        if (percent - 60) >= target:
            return MAGENTA
    return RED


# --- data -------------------------------------------------------------------


def run_tests(pytest_args):
    command = [
        sys.executable, "-m", "pytest",
        "--cov", f"--cov-config={CONFIG}",
        "--cov-report=",  # silence pytest-cov's own table; we draw ours
        *pytest_args,
    ]
    print(paint("▶ " + " ".join(command[1:]), DIM), flush=True)
    return subprocess.run(command, check=False, cwd=ROOT).returncode


def load_report():
    """Export the .coverage data to JSON and return it as a dict."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "coverage.json"
        subprocess.run(
            [sys.executable, "-m", "coverage", "json", "-q",
             f"--rcfile={CONFIG}", "-o", str(out)],
            cwd=ROOT, check=True,
        )
        return json.loads(out.read_text(encoding="utf-8"))


def build_html():
    subprocess.run(
        [sys.executable, "-m", "coverage", "html", "-q", f"--rcfile={CONFIG}"],
        cwd=ROOT, check=True,
    )
    return COVERAGE_DIR / "htmlcov" / "index.html"


def compact_ranges(lines):
    """[1, 2, 3, 7, 9, 10] -> '1-3, 7, 9-10'"""
    if not lines:
        return ""
    ranges, start, prev = [], lines[0], lines[0]
    for line in lines[1:]:
        if line != prev + 1:
            ranges.append((start, prev))
            start = line
        prev = line
    ranges.append((start, prev))
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)


# --- rendering --------------------------------------------------------------


def bar(percent, color):
    filled = round(percent / 100 * BAR_WIDTH)
    return paint("█" * filled, color) + paint("░" * (BAR_WIDTH - filled), DIM)


def truncate(text, width, keep_end=True):
    if len(text) <= width:
        return text
    return "…" + text[-(width - 1):] if keep_end else text[:width - 1] + "…"


def render(report, target, sort_key):
    files = report["files"]
    rows = []
    for name, info in files.items():
        s = info["summary"]
        rows.append({
            "name": name.replace("\\", "/"),
            "stmts": s["num_statements"],
            "miss": s["missing_lines"],
            "branches": s.get("num_branches", 0),
            "partial": s.get("num_partial_branches", 0),
            "percent": s["percent_covered"],
            "missing": compact_ranges(info["missing_lines"]),
        })

    sorters = {
        "name": lambda r: r["name"],
        "cover": lambda r: r["percent"],
        "miss": lambda r: -r["miss"],
    }
    rows.sort(key=sorters[sort_key])

    name_w = min(max([len(r["name"]) for r in rows] + [4]), 40)
    header = (f"  {'File':<{name_w}}  {'Stmts':>5}  {'Miss':>4}  "
              f"{'Branch':>6}  {'Cover':>6}  {'':<{BAR_WIDTH}}  Missing")
    rule = paint("─" * (len(header) + 12), DIM)

    title = " COVERAGE REPORT "
    print()
    print(paint("╭" + "─" * (len(title) + 2) + "╮", CYAN))
    print(paint("│ ", CYAN) + paint(title, BOLD, CYAN) + paint(" │", CYAN))
    print(paint("╰" + "─" * (len(title) + 2) + "╯", CYAN))
    print()
    print(paint(header, BOLD))
    print(rule)

    for r in rows:
        color = grade_color(r["percent"], target)
        branch = f"{r['partial']}/{r['branches']}" if r["branches"] else "-"
        if r["missing"]:
            missing = paint(truncate(r["missing"], 40, keep_end=False), MAGENTA)
        elif r["partial"]:
            missing = paint(f"{r['partial']} partial branch(es)", YELLOW)
        else:
            missing = paint("✓", GREEN)
        print(
            f"  {truncate(r['name'], name_w):<{name_w}}  {r['stmts']:>5}  "
            f"{paint(f'{r['miss']:>4}', RED) if r['miss'] else paint(f'{0:>4}', DIM)}  "
            f"{branch:>6}  {paint(f'{r['percent']:5.1f}%', BOLD, color)}  "
            f"{bar(r['percent'], color)}  {missing}"
        )

    totals = report["totals"]
    total_pct = totals["percent_covered"]
    color = grade_color(total_pct, target)
    print(rule)
    t_branch = f"{totals.get('num_partial_branches', 0)}/{totals.get('num_branches', 0)}"
    print(
        paint(f"  {'TOTAL':<{name_w}}", BOLD) + f"  {totals['num_statements']:>5}  "
        f"{totals['missing_lines']:>4}  {t_branch:>6}  "
        f"{paint(f'{total_pct:5.1f}%', BOLD, color)}  {bar(total_pct, color)}"
    )
    print()
    print(paint("  Branch column = partially covered / total branches", DIM))
    return total_pct


# --- main -------------------------------------------------------------------


def main():
    argv = sys.argv[1:]
    pytest_args = []
    if "--" in argv:
        split = argv.index("--")
        argv, pytest_args = argv[:split], argv[split + 1:]

    parser = argparse.ArgumentParser(description="Pretty coverage report for lcpgamecol.")
    parser.add_argument("--fail-under", type=float, default=40,
                        help="minimum total coverage %% (default: 40)")
    parser.add_argument("--sort", choices=["name", "cover", "miss"], default="cover",
                        help="row order (default: cover, lowest first)")
    parser.add_argument("--html", action="store_true", help="also build mycoverage/htmlcov/")
    parser.add_argument("--open", action="store_true", help="open the HTML report (implies --html)")
    parser.add_argument("--no-run", action="store_true", help="skip tests, use existing mycoverage/.coverage")
    args = parser.parse_args(argv)

    tests_code = 0
    if not args.no_run:
        tests_code = run_tests(pytest_args)
    if not (COVERAGE_DIR / ".coverage").exists():
        print(paint("✗ No .coverage data found — run without --no-run first.", RED, BOLD))
        return 2

    total = render(load_report(), args.fail_under, args.sort)

    if args.html or args.open:
        index = build_html()
        print(paint(f"  📄 HTML report: {index}", CYAN))
        if args.open:
            webbrowser.open(index.as_uri())

    passed = total >= args.fail_under
    verdict = (paint(f"  ✔ {total:.1f}% ≥ {args.fail_under:g}% target", GREEN, BOLD) if passed
               else paint(f"  ✘ {total:.1f}% < {args.fail_under:g}% target", RED, BOLD))
    print(verdict)
    if tests_code:
        print(paint(f"  ✘ pytest exited with code {tests_code}", RED, BOLD))
    print()

    return tests_code or (0 if passed else 1)


if __name__ == "__main__":
    sys.exit(main())
