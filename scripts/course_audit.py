#!/usr/bin/env python3
"""Extract an assignment PDF and check mechanical properties of a final PDF.

This tool cannot judge whether an argument meets a rubric or a citation supports
a claim. Those decisions require a human reading the official brief and paper.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError as exc:
    raise SystemExit(
        "PyMuPDF is required. Install this skill's scripts/requirements.txt first."
    ) from exc


WORD_RE = re.compile(r"\b[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*\b")
CODE_CANDIDATE_RE = re.compile(r"\b(?:C\d+|[A-Z]{2,8}[-_]?[0-9]{1,5}[A-Z]?)\b")


class Report:
    def __init__(self) -> None:
        self.fails = 0
        self.reviews = 0

    def add(self, status: str, message: str) -> None:
        print(f"[{status}] {message}")
        if status == "FAIL":
            self.fails += 1
        elif status == "REVIEW":
            self.reviews += 1

    def exit_code(self) -> int:
        print(f"Summary: {self.fails} FAIL, {self.reviews} REVIEW")
        return 2 if self.fails else 1 if self.reviews else 0


def load_pdf(path: Path) -> tuple[fitz.Document, list[str]]:
    if not path.is_file():
        raise ValueError(f"PDF does not exist: {path}")
    try:
        document = fitz.open(path)
        if document.is_encrypted:
            raise ValueError("PDF is encrypted; provide a readable export")
        return document, [page.get_text("text") for page in document]
    except (fitz.FileDataError, RuntimeError) as exc:
        raise ValueError(f"Cannot open PDF: {path}: {exc}") from exc


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def has_token(text: str, token: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(token)}(?!\w)", text, re.IGNORECASE) is not None


def code_candidates(text: str, expected: str) -> set[str]:
    candidates = {value.upper() for value in CODE_CANDIDATE_RE.findall(text)}
    if re.fullmatch(r"[A-Za-z][0-9]+", expected):
        candidates.update(value.upper() for value in re.findall(r"\b[A-Z][0-9]+\b", text))
    return candidates


def marker_matches(text: str, marker: str, start: int = 0) -> list[tuple[int, int]]:
    """Prefer heading lines; fall back to literal phrases for unusual PDFs."""
    words = marker.strip().split()
    if not words:
        raise ValueError("An empty word-count marker is invalid")
    phrase = r"\s+".join(re.escape(word) for word in words)
    heading = re.compile(rf"(?im)^[ \t]*(?:\d+[.)]?[ \t]*)?(?:#+[ \t]*)?{phrase}[ \t]*$")
    matches = list(heading.finditer(text, start))
    if not matches:
        matches = list(re.compile(phrase, re.IGNORECASE).finditer(text, start))
    return [(match.start(), match.end()) for match in matches]


def choose_marker(report: Report, text: str, marker: str, label: str,
                  occurrence: int | None = None, start: int = 0) -> tuple[int, int] | None:
    matches = marker_matches(text, marker, start)
    if occurrence is not None:
        if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 1:
            raise ValueError(f"{label}_occurrence must be a positive integer")
        if occurrence > len(matches):
            report.add("FAIL", f"{label} marker {marker!r}: occurrence {occurrence} not found")
            return None
        return matches[occurrence - 1]
    if not matches:
        report.add("FAIL", f"{label} marker {marker!r} not found")
        return None
    if len(matches) > 1:
        report.add("REVIEW", f"{label} marker {marker!r} occurs {len(matches)} times; set {label}_occurrence")
        return None
    return matches[0]


def words(text: str) -> tuple[int, int]:
    return len(text.split()), len(WORD_RE.findall(text))


def edge_repeat_uncertainty(document: fitz.Document) -> int:
    """Upper bound for words from repeated page-edge blocks in raw PDF text."""
    blocks: list[tuple[str, int]] = []
    for page in document:
        height = page.rect.height
        for block in page.get_text("blocks"):
            if block[1] >= height * 0.12 and block[3] <= height * 0.88:
                continue
            value = str(block[4]).strip()
            if not value or len(value) > 160:
                continue
            template = re.sub(r"\d+", "#", normalized(value))
            blocks.append((template, max(words(value))))
    repeated = {template for template, count in Counter(key for key, _ in blocks).items() if count >= 2}
    return sum(count for template, count in blocks if template in repeated)


def range_status(counts: tuple[int, ...], minimum: int, maximum: int, uncertainty: int) -> str:
    if all(minimum <= count <= maximum and count - uncertainty >= minimum for count in counts):
        return "PASS"
    if any(count >= minimum and count - uncertainty <= maximum for count in counts):
        return "REVIEW"
    return "FAIL"


def check_range(report: Report, label: str, text: str, minimum: int, maximum: int,
                level: str = "mandatory", uncertainty: int = 0) -> None:
    whitespace, tokens = words(text)
    shown = (f"{label}: whitespace={whitespace}, English tokens={tokens}; "
             f"required {minimum}–{maximum}; repeated edge words up to {uncertainty}")
    status = range_status((whitespace, tokens), minimum, maximum, uncertainty)
    if level == "informational":
        report.add("INFO", shown + "; alternative count, not the official scope")
    elif status == "PASS":
        report.add("PASS", shown)
    elif status == "REVIEW":
        report.add("REVIEW", shown + "; counting scope or page edges need checking")
    else:
        report.add("REVIEW" if level == "suggested" else "FAIL",
                   shown + ("; suggested range" if level == "suggested" else "; outside range"))


def positive_range(data: dict, label: str) -> tuple[int, int]:
    minimum, maximum = data.get("min"), data.get("max")
    if (not isinstance(minimum, int) or isinstance(minimum, bool)
            or not isinstance(maximum, int) or isinstance(maximum, bool)
            or minimum <= 0 or maximum < minimum):
        raise ValueError(f"{label} needs positive integer min/max with max >= min")
    return minimum, maximum


def extract(args: argparse.Namespace) -> int:
    if args.pdf.resolve() == args.out.resolve():
        raise ValueError("Output path must differ from the input PDF")
    if args.out.exists():
        raise ValueError(f"Output already exists; choose a new path: {args.out}")
    document, pages = load_pdf(args.pdf)
    output = []
    thin_pages = []
    for number, page_text in enumerate(pages, 1):
        output.append(f"\n# Page {number}\n\n{page_text.strip()}\n")
        if len(page_text.strip()) < 80:
            thin_pages.append(number)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=args.out.parent,
            prefix=".course-audit-", suffix=".tmp", delete=False
        ) as temporary:
            temp_path = Path(temporary.name)
            temporary.write("\n".join(output))
        os.link(temp_path, args.out)  # exclusive, atomic creation; never replace a PDF or earlier extraction
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    print(f"Extracted {len(document)} page(s) to {args.out}")
    if thin_pages:
        print(f"REVIEW: little extractable text on pages {thin_pages}; inspect visually and OCR scans")
        return 1
    print("Inspect the original PDF pages and rubric before treating this text as complete.")
    return 0


def verify(args: argparse.Namespace) -> int:
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("Spec must be a JSON object")
    required_front = spec.get("required_first_page", [])
    if not isinstance(required_front, list) or any(
        field not in ("course_title", "course_code", "student_name")
        for field in required_front
    ):
        raise ValueError("required_first_page must list known identity fields")
    forbidden = spec.get("forbidden_identity_tokens", [])
    if not isinstance(forbidden, list):
        raise ValueError("forbidden_identity_tokens must be a list")
    sections = spec.get("sections", [])
    if not isinstance(sections, list):
        raise ValueError("sections must be a list")
    expected_name = spec.get("expected_filename")
    if not isinstance(expected_name, str) or not expected_name.lower().endswith(".pdf"):
        raise ValueError("Spec needs an exact expected_filename ending in .pdf")
    basis = spec.get("filename_basis")
    source = spec.get("filename_source")
    if basis not in ("official", "working_convention") or not isinstance(source, str) or not source.strip():
        raise ValueError("Spec needs filename_basis (official/working_convention) and filename_source")
    if "word_count" not in spec:
        raise ValueError("Spec needs word_count as a verified range object, or null when no limit exists")
    if "FROM_CURRENT" in json.dumps(spec).upper() or "STALE_CODE_IF_KNOWN" in json.dumps(spec):
        raise ValueError("Replace example placeholder values with verified course requirements")
    report = Report()
    document, pages = load_pdf(args.pdf)
    full_text = "\n".join(pages)
    first = pages[0] if pages else ""
    edge_uncertainty = edge_repeat_uncertainty(document)
    report.add("PASS" if args.pdf.name == expected_name else "FAIL",
               f"Filename ({basis}; {source}): actual={args.pdf.name!r}; expected={expected_name!r}")
    report.add("PASS", f"PDF opens with {len(document)} page(s)")
    if not normalized(full_text):
        report.add("FAIL", "No extractable PDF text; inspect and OCR/export again")
    for number, page_text in enumerate(pages, 1):
        if len(page_text.strip()) < 80:
            report.add("REVIEW", f"Page {number} has little extractable text; inspect visually")

    for key, display in (("course_title", "Course title"),
                         ("course_code", "Course code"),
                         ("student_name", "Student name")):
        value = spec.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a nonempty string when supplied")
        present = normalized(value) in normalized(first) if key == "course_title" else has_token(first, value)
        required = key in required_front
        status = "PASS" if present else "FAIL" if required else "REVIEW"
        report.add(status, f"{display} on PDF first page: {value!r}")

    for stale in forbidden:
        if not isinstance(stale, str) or not stale:
            raise ValueError("forbidden_identity_tokens must be nonempty strings")
        found = has_token(full_text, stale) or has_token(str(document.metadata), stale)
        report.add("FAIL" if found else "PASS", f"Stale identity token {stale!r} absent from PDF text/metadata")

    expected_code = spec.get("course_code") or ""
    if expected_code:
        other_front = sorted(code_candidates(first, expected_code) - {expected_code.upper()})
        if other_front:
            status = "FAIL" if not has_token(first, expected_code) else "REVIEW"
            report.add(status, f"PDF first page contains other code-like token(s): {other_front}")
        for page_number, page in enumerate(document, 1):
            height = page.rect.height
            edge_text = "\n".join(
                str(block[4]) for block in page.get_text("blocks")
                if block[1] < height * 0.12 or block[3] > height * 0.88
            )
            others = sorted(code_candidates(edge_text, expected_code) - {expected_code.upper()})
            if others:
                report.add("REVIEW", f"Page {page_number} header/footer has other code-like token(s): {others}")

    if args.source:
        source = args.source.read_text(encoding="utf-8")
        source_front = source[:2500]
        if expected_code:
            other_source = sorted(code_candidates(source_front, expected_code) - {expected_code.upper()})
            if other_source:
                report.add("REVIEW", f"Source front matter contains other code-like token(s): {other_source}")
        for key in ("course_title", "course_code", "student_name"):
            value = spec.get(key)
            if value:
                present = normalized(value) in normalized(source_front) if key == "course_title" else has_token(source_front, value)
                report.add("PASS" if present else "REVIEW", f"{key} in source front matter: {value!r}")
        for stale in forbidden:
            report.add("FAIL" if has_token(source_front, stale) else "PASS",
                       f"Stale identity token {stale!r} absent from source front matter")

    word_spec = spec.get("word_count")
    if word_spec is not None:
        if not isinstance(word_spec, dict):
            raise ValueError("word_count must be an object")
        minimum, maximum = positive_range(word_spec, "word_count")
        start_marker = word_spec.get("start_marker")
        end_marker = word_spec.get("end_marker")
        if start_marker is not None and not isinstance(start_marker, str):
            raise ValueError("word_count start_marker must be a string or null")
        if end_marker is not None and not isinstance(end_marker, str):
            raise ValueError("word_count end_marker must be a string or null")
        start = (choose_marker(report, full_text, start_marker, "start", word_spec.get("start_occurrence"))
                 if start_marker else (0, 0))
        end = (choose_marker(report, full_text, end_marker, "end", word_spec.get("end_occurrence"),
                             start[1] if start else 0)
               if end_marker and start else (len(full_text), len(full_text)) if start else None)
        if start and end and start[0] >= end[0]:
            report.add("FAIL", "Word-count markers are out of order")
        elif not start or not end:
            report.add("REVIEW", "Word count needs unambiguous PDF boundaries")
        else:
            body = full_text[start[0]:end[0]]
            before_refs = full_text[:end[0]]
            policy = word_spec.get("policy", "both")
            if policy not in ("body", "pre_references", "both"):
                raise ValueError("word_count policy must be body, pre_references, or both")
            report.add("PASS", f"Word-count boundaries: {start_marker or 'PDF start'} → {end_marker or 'PDF end'}")
            if policy == "both":
                check_range(report, "Body within selected boundaries", body, minimum, maximum,
                            "informational", edge_uncertainty)
                check_range(report, "All text before selected end", before_refs, minimum, maximum,
                            "informational", edge_uncertainty)
                counts = (*words(body), *words(before_refs))
                status = range_status(counts, minimum, maximum, edge_uncertainty)
                report.add(status, "Word-count scope is not established; both estimates shown for review")
            else:
                check_range(report, "Body within selected boundaries", body, minimum, maximum,
                            "mandatory" if policy == "body" else "informational", edge_uncertainty)
                check_range(report, "All text before selected end", before_refs, minimum, maximum,
                            "mandatory" if policy == "pre_references" else "informational", edge_uncertainty)

    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("Each section must be an object")
        label = str(section.get("label", "Section"))
        minimum, maximum = positive_range(section, label)
        start_marker, end_marker = section.get("start_marker"), section.get("end_marker")
        if not isinstance(start_marker, str) or (end_marker is not None and not isinstance(end_marker, str)):
            raise ValueError(f"{label} needs a start_marker and a string or null end_marker")
        start = choose_marker(report, full_text, start_marker, "start", section.get("start_occurrence"))
        end = ((choose_marker(report, full_text, end_marker, "end", section.get("end_occurrence"), start[1])
                if end_marker else (len(full_text), len(full_text))) if start else None)
        if start and end and start[0] >= end[0]:
            report.add("FAIL", f"{label}: section markers out of order")
            continue
        if not start or not end:
            report.add("REVIEW", f"{label}: section count needs unambiguous PDF boundaries")
            continue
        level = section.get("level", "mandatory")
        if level not in ("mandatory", "suggested"):
            raise ValueError(f"{label} level must be mandatory or suggested")
        check_range(report, label, full_text[start[0]:end[0]], minimum, maximum, level, edge_uncertainty)

    return report.exit_code()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract_parser = commands.add_parser("extract", help="Export page-numbered text from a brief PDF")
    extract_parser.add_argument("--pdf", type=Path, required=True)
    extract_parser.add_argument("--out", type=Path, required=True)
    verify_parser = commands.add_parser("verify", help="Check final PDF identity, readability and word ranges")
    verify_parser.add_argument("--pdf", type=Path, required=True)
    verify_parser.add_argument("--spec", type=Path, required=True)
    verify_parser.add_argument("--source", type=Path, help="Optional editable source for front-matter checks")
    args = parser.parse_args()
    try:
        return extract(args) if args.command == "extract" else verify(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
