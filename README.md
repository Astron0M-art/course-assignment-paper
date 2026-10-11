# Course Assignment Paper

Codex skill for writing and checking course assignments against the **current** assignment PDF, rubric, and LMS submission rules. It includes a PDF extraction and submission audit script. Assignment documents and personal drafts are not included.

## Install

Public repository; no GitHub login is required. Git must be installed.

**macOS (Terminal)**

```sh
mkdir -p "$HOME/.codex/skills" && git clone https://github.com/Astron0M-art/course-assignment-paper.git "$HOME/.codex/skills/course-assignment-paper"
```

**Windows (PowerShell)**

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex\skills" | Out-Null; git clone https://github.com/Astron0M-art/course-assignment-paper.git "$HOME\.codex\skills\course-assignment-paper"
```

Restart Codex after installation. Use `$course-assignment-paper` and provide the current course assignment PDF and grading requirements. For the PDF audit script, install Python 3.10+ and `pip install -r scripts/requirements.txt`.

To update an existing installation, run `git -C ~/.codex/skills/course-assignment-paper pull --ff-only` on macOS, or `git -C "$HOME\.codex\skills\course-assignment-paper" pull --ff-only` in PowerShell.
