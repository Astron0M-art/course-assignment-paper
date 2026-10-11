# Requirements matrix and audit spec

Before drafting, create a table with these columns: **requirement**, **exact value**, **mandatory / suggested / scored / not specified**, **source + page or LMS date**, **verified?**, **where the answer will appear**. Keep a separate unresolved list. An absent requirement is recorded as `not specified`, not supplied from a previous paper.

## Fields to capture

| Area | Questions to answer from this assignment |
| --- | --- |
| Identity | Exact course title and code, student-name spelling, degree/cohort if required; which current source confirms each? |
| Task shape | Essay or separate answers? How many questions, concepts, cases, risks, and required deliverables? |
| Rubric | Weight/points per criterion, required depth, suggested frameworks versus compulsory outputs? |
| Evidence | Course slides or readings, user-provided real-world case facts, external sources, quantitative assumptions, citation style and minimum count if stated? |
| Integrity | AI-assistance limits or disclosure, originality/collaboration rules, and permission to use/anonymize internal material? |
| Length | Language; total word range; per-question targets; whether abstract, cover, tables, footnotes, references and appendices count? |
| Layout | PDF/Word format, headings, cover, font, spacing, page range, abstract and bibliography requirements, if stated? |
| Delivery | Official filename pattern if any; otherwise a clearly labeled working filename; course code source, due date/time zone, upload destination, editable source and PDF requested by user? |

If the assignment PDF is silent on naming but a **current** LMS message supplies it, record both; the LMS is not a substitute for the PDF's substantive task. A current LMS example that expressly says to replace only the student's name is a naming rule. If no official filename rule exists, choose a descriptive name and label it a working convention, never an official requirement. If official materials conflict, stop treating the affected field as settled and verify it before final submission. A past draft or an example detached from the current course is not proof of its code.

## `course_audit.py verify` spec

Create a per-assignment JSON file outside the skill package. Only include requirements verified for **this** course. Example structure, with values to replace from current sources:

```json
{
  "course_title": "Example Course Title",
  "course_code": "COURSE_CODE_FROM_CURRENT_LMS",
  "student_name": "STUDENT_NAME_AS_REQUIRED",
  "expected_filename": "EXACT_CURRENT_LMS_FILENAME.pdf",
  "filename_basis": "official",
  "filename_source": "Current LMS notice date and location",
  "required_first_page": ["course_title", "course_code", "student_name"],
  "forbidden_identity_tokens": ["STALE_CODE_IF_KNOWN"],
  "word_count": {
    "min": 0,
    "max": 0,
    "start_marker": "FIRST_BODY_HEADING",
    "end_marker": "REFERENCES_HEADING",
    "policy": "both"
  },
  "sections": [
    {
      "label": "Optional question or section",
      "start_marker": "SECTION_START",
      "end_marker": "NEXT_SECTION_START",
      "min": 0,
      "max": 0,
      "level": "suggested"
    }
  ]
}
```

Use `filename_basis: "official"` only with a current rule and give `filename_source`; otherwise use `"working_convention"` and explain that choice in `filename_source`. `expected_filename` is required in both cases so the artifact can be checked. `word_count` must be an object when the brief sets a limit, or explicitly `null` when it does not. Use `policy: "body"` only when the official rule excludes cover/abstract; use `"pre_references"` only when it includes them; use `"both"` when the scope is unclear. Set either total-word marker to `null` when that boundary is the start/end of the PDF; for the final question, `sections[].end_marker: null` means PDF end. Use an actual heading when references or other excluded material follows. If a contents page repeats a heading, the script returns `REVIEW`; inspect the PDF and set one-based `start_occurrence` and/or `end_occurrence` for that word-count section. Omit optional identity fields if the assignment genuinely lacks them. Put a field in `required_first_page` only if the current brief or LMS requires that field there; otherwise absence produces a review flag while an unexpected code in headers/footers still prompts review. Section `level` can be `mandatory` or `suggested`: a suggested range produces a review flag instead of an automatic failure. Reconcile total and per-question limits before drafting; their overlapping feasible range may be narrower than either alone. The script reports both whitespace and English-token estimates and flags possible repeated-header contamination near a limit; resolve any disagreement against the official rule or the editor's word count. Do not put invented zeros or placeholder strings into a real spec.
