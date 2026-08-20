#!/usr/bin/env python3
"""Pre-submission check. Run `make verify` before you push.

Checks what is *committed*, because that is all the grader can see. Large local
artifacts (the GGUF weights, the runtime binaries) are gitignored by design, so
their absence is reported as information, never as a failure -- otherwise this
script could never pass on a fresh clone, which is exactly what the grader does.

Exit 0 means your repo is ready. Exit 1 prints the checklist of what is missing.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import labkit  # noqa: E402

MIN_SCREENSHOTS = 5

# Placeholders left behind by the REFLECTION template.
TEMPLATE_MARKERS = [
    r"<Họ Tên>",
    r"<A20-K1 / A20-K2",
    r"<YYYY-MM-DD>",
    r"<macOS 14 / Windows 11",
    r"^_Answer here\._?\s*$",
    # Any `_<...>_` slot, plus the bare `<số ...>` / `<X.Y>` ones inside §5's code
    # block. Scanned only over the REQUIRED sections (see REQUIRED_END) so that
    # leaving the optional bonus section untouched stays legal.
    r"_<[^>\n]{1,60}>_",
    r"<số[^>\n]*>",
    r"<X\.[XY]>",
]
# Sections 1-5 are graded; section 6 onward is optional and may keep its template text.
# Matched loosely so renaming/translating the heading cannot turn the optional section
# into blocking false positives.
REQUIRED_END = re.compile(r"^##\s*6(?:[.)]|\s)", re.MULTILINE)
# Every generated report ends with a section the student must replace.
UNANSWERED = re.compile(r"required -- replace this line", re.IGNORECASE)

OK, WARN, BAD = "  ✓", "  •", "  ✗"


def tracked_files() -> set[str] | None:
    """Paths git is tracking, or None if this is not a usable git checkout.

    The grader only ever sees committed files, so "exists on disk" is not the
    question -- "is it in the repo" is.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(labkit.repo_root()), "ls-files"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


TRACKED = None  # populated in main()


def is_committed(path: pathlib.Path) -> bool | None:
    """True/False if we know, None if git is unavailable."""
    if TRACKED is None:
        return None
    try:
        rel = path.resolve().relative_to(labkit.repo_root()).as_posix()
    except ValueError:
        return None
    return rel in TRACKED


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.notes: list[str] = []

    def fail(self, msg: str) -> None:
        self.problems.append(msg)
        print(f"{BAD} {msg}")

    def ok(self, msg: str) -> None:
        print(f"{OK} {msg}")

    def note(self, msg: str) -> None:
        self.notes.append(msg)
        print(f"{WARN} {msg}")


def need_file(r: Report, path: pathlib.Path, label: str, how: str) -> pathlib.Path | None:
    rel = path.relative_to(labkit.repo_root())
    if not path.exists():
        r.fail(f"{label}: {rel} is missing — run `{how}`")
        return None
    if path.stat().st_size == 0:
        r.fail(f"{label}: {rel} is empty — run `{how}`")
        return None
    if path.suffix == ".md" and UNANSWERED.search(path.read_text(encoding="utf-8", errors="replace")):
        r.fail(f"{label}: {rel} still has an unanswered 'replace this line' section")
        return None
    if is_committed(path) is False:
        r.fail(f"{label}: {rel} exists but is NOT committed — `git add` it or the grader cannot see it")
        return None
    r.ok(f"{label}: {rel}")
    return path


def any_file(r: Report, patterns: list[str], label: str, how: str) -> bool:
    root = labkit.repo_root()
    hits = [p for pat in patterns for p in sorted(root.glob(pat)) if p.stat().st_size > 0]
    if not hits:
        r.fail(f"{label}: none of {patterns} found — run `{how}`")
        return False
    stale = [p for p in hits if p.suffix == ".md" and UNANSWERED.search(p.read_text(encoding="utf-8", errors="replace"))]
    if stale and len(stale) == len([p for p in hits if p.suffix == ".md"]):
        r.fail(f"{label}: {stale[0].relative_to(root)} still has an unanswered section")
        return False
    uncommitted = [p for p in hits if is_committed(p) is False]
    if uncommitted and len(uncommitted) == len(hits):
        r.fail(f"{label}: {uncommitted[0].relative_to(root)} is not committed — `git add` it")
        return False
    r.ok(f"{label}: {', '.join(str(p.relative_to(root)) for p in hits[:3])}")
    return True


def blank_table_cells(md: str) -> list[str]:
    """Rows of a markdown table that still have an empty cell.

    The template ships its data tables empty (`| UD-Q4_K_XL | | | ... |`); a student
    who skips the measurements leaves them that way. Separator and header rows are
    ignored, as is anything inside a fenced code block.
    """
    bad, in_fence = [], False
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells):
            continue                      # separator row
        if any(c == "" for c in cells):
            bad.append(s[:60])
    return bad


def check_manifest(r: Report) -> None:
    path = labkit.active_json()
    if not path.exists():
        r.fail("Model manifest: models/active.json is missing — run `make setup`")
        return
    try:
        cfg = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except ValueError as exc:
        r.fail(f"Model manifest: models/active.json is not valid JSON — {exc}")
        return
    missing = [k for k in ("model", "repo_id", "primary_model", "compare_model") if not cfg.get(k)]
    if missing:
        r.fail(f"Model manifest: models/active.json lacks {missing} — re-run `make setup`")
        return
    if is_committed(path) is False:
        r.fail("Model manifest: models/active.json is not committed — `git add models/active.json`")
        return
    r.ok(f"Model manifest: {cfg['model']} ({cfg.get('primary_quant')} + {cfg.get('compare_quant')})")

    # Weights are gitignored, so their absence is not a submission problem.
    for key in ("primary_model", "compare_model"):
        p = labkit.repo_root() / cfg[key]
        if not p.exists():
            r.note(f"{cfg[key]} not on this machine (fine — weights are gitignored)")


def check_reflection(r: Report) -> None:
    path = labkit.repo_root() / "submission" / "REFLECTION.md"
    if not path.exists():
        r.fail("Reflection: submission/REFLECTION.md is missing")
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    end = REQUIRED_END.search(text)
    required = text[: end.start()] if end else text
    hits = [
        m.group().strip()
        for p in TEMPLATE_MARKERS
        for m in re.finditer(p, required, re.MULTILINE if p.startswith("^") else 0)
    ]
    if hits:
        shown = ", ".join(sorted(set(hits))[:3])
        r.fail(
            f"Reflection: submission/REFLECTION.md still has {len(hits)} template "
            f"placeholder(s) in sections 1-5 (e.g. {shown}) — fill in your own "
            f"numbers and answers"
        )
        return
    # A word count is a poor proxy (the blank template is already ~1050 words, and a
    # student who trims the boilerplate can be shorter yet complete). Check the thing
    # that actually matters instead: the required tables must have no empty cells.
    blank = blank_table_cells(required)
    if blank:
        r.fail(
            f"Reflection: {len(blank)} table row(s) with empty cells in sections 1-5 "
            f"(e.g. \"{blank[0]}\") — paste your measured numbers in"
        )
        return
    r.ok(f"Reflection: submission/REFLECTION.md filled in ({len(text.split())} words)")


def check_screenshots(r: Report) -> None:
    folder = labkit.repo_root() / "submission" / "screenshots"
    if not folder.exists():
        r.fail("Screenshots: submission/screenshots/ is missing")
        return
    imgs = [p for p in folder.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    if len(imgs) < MIN_SCREENSHOTS:
        r.fail(
            f"Screenshots: {len(imgs)} of {MIN_SCREENSHOTS} required — "
            f"see submission/screenshots/README.md"
        )
        return
    uncommitted = [p for p in imgs if is_committed(p) is False]
    if uncommitted:
        names = ", ".join(p.name for p in uncommitted[:3])
        r.fail(
            f"Screenshots: {len(uncommitted)} not committed ({names}) — `git add "
            f"submission/screenshots/` or the grader cannot see them"
        )
        return
    r.ok(f"Screenshots: {len(imgs)} image(s)")


def check_runtime(r: Report) -> None:
    """Informational: the grader will not have these, and does not need them."""
    server = labkit.runtime_bin("llama-server", required=False)
    if server:
        r.ok(f"Runtime: llama-server present ({labkit.LLAMA_CPP_BUILD})")
    else:
        r.note("llama-server not on this machine (fine — runtime/ is gitignored)")


def main() -> int:
    global TRACKED
    r = Report()
    root = labkit.repo_root()
    TRACKED = tracked_files()
    print(f"==> Verifying submission readiness in {root}\n")
    if TRACKED is None:
        print("  (git not available — checking files on disk only; make sure you commit them)\n")

    print("Setup (00)")
    need_file(r, root / "hardware.json", "Hardware probe", "make probe")
    check_manifest(r)
    check_runtime(r)

    print("\nMeasure (01)")
    need_file(r, root / "benchmarks" / "01-quickstart-results.md",
              "Latency baseline", "make bench")
    any_file(r, ["benchmarks/01-tuning-*.md"], "Tuning sweep", "make tune")

    print("\nServe (02)")
    for users in (10, 50):
        need_file(r, root / "benchmarks" / f"locust-{users}_stats.csv",
                  f"Load run at {users} users", f"make load-{users}")
    need_file(r, root / "benchmarks" / "02-server-results.md",
              "Saturation reading", "make load-report")
    any_file(r, ["benchmarks/02-server-batching*.md", "benchmarks/02-server-metrics*.csv"],
             "Continuous-batching evidence", "make metrics (while make load-50 runs)")

    print("\nIntegrate (03)")
    need_file(r, root / "benchmarks" / "03-integration-results.md",
              "RAG pipeline run", "make pipeline")

    print("\nSubmission")
    check_reflection(r)
    check_screenshots(r)

    print()
    if r.problems:
        print(f"✗ Not ready — {len(r.problems)} item(s) to fix:\n")
        for p in r.problems:
            print(f"  - {p}")
        print("\nSee rubric.md for what each item is worth. Re-run `make verify` when fixed.")
        return 1

    print("✓ All checks passed.")
    if r.notes:
        print(f"  ({len(r.notes)} informational note(s) above — none block submission.)")
    print()
    print("  Note: this checks that the files exist. It cannot check that your numbers agree")
    print("  with each other -- re-read benchmarks/*.md against REFLECTION.md before pushing.")
    print()
    print("  Next: commit, push to a PUBLIC GitHub repo, paste the URL into the LMS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
