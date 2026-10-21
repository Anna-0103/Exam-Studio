# Exam Studio

A Streamlit practice website for Data Analytics in Accounting. Solve course-based tasks in Excel or SQLite, check outputs, and return to saved attempts with answers and feedback intact.

## Run locally

Use Python 3.12.

```sh
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy from GitHub to Streamlit Community Cloud

1. Create a GitHub repository named `exam-studio`.
2. Upload or push this project's tracked files, including `data/` and `assets/`. Exclude `.venv/`, `research-sources/`, `qa/` and backups.
3. In [Streamlit Community Cloud](https://share.streamlit.io/), choose **Create app** and select the repository.
4. Set the branch to `main`, the entrypoint to `app.py`, and Python to **3.12** in advanced settings.
5. Add `GEMINI_API_KEY` in **App settings → Secrets** to enable AI help (see below), then deploy. All other features work without a key or database service.

Keep the repository private if the supplied teaching materials are not licensed for public redistribution. The course datasets remain third-party content; this project does not relicense them.

Official deployment guide: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

## Features

- 103 sourced questions: 43 Excel, 40 SQL and 20 regression interpretation.
- 66 practice exams: 52 manipulation and 14 interpretation, including clearly labelled scenario variants.
- Fixed exam timers: 8 minutes for manipulation and 5 minutes for interpretation.
- Clickable question navigation with active-question, answered and checked-result states.
- Individual-question practice; subject, skill and text filtering with Back/Next pagination and visible item counts.
- Immediate feedback for all new practice attempts; older saved Exam-mode attempts retain their review rules.
- Numeric and table result comparison, including ordering, duplicates, nulls and tolerances.
- Authored hints, worked approaches and self-review checklists for explanations.
- Question-scoped Gemini help, saved conversation history, preserved drafts and readable failure messages.
- Browser-local saved attempts with answer revisions, feedback, notes, question snapshots and elapsed time.
- JSON backup export/import for another device; imports create a separate copy.
- Individual dataset downloads and one ZIP containing an exam's files.
- Browser-tab conflict detection and visible persistence failures.

This is independent practice, not a replica of the instructor's 400-question bank or an official exam blueprint. A matching output is not proof of a correct method. Many exams reuse questions in different combinations; regression variants practise different inputs with the same course-supported models.

## Enable Gemini help

In Streamlit Community Cloud, open the app's **Settings → Secrets** and add:

```toml
GEMINI_API_KEY = "your-key-from-Google-AI-Studio"
GEMINI_MODEL = "gemini-3.5-flash-lite"
```

For local use, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and replace the placeholder. Never commit the actual secrets file or paste a key into the student interface. Environment variables of the same names are supported; Streamlit Secrets take precedence.

The tutor uses Google's `generateContent` REST API with exactly `gemini-3.5-flash-lite` by default. There is no silent model fallback. The key is sent in the server-side `x-goog-api-key` header, never in the URL or saved attempt. No additional SDK is needed.

“Get help from AI” offers the student's working, optional output and a follow-up question. It sends only the current question, compact dataset structures, reference approach and up to 12 recent conversation messages to Google. It does not upload the dataset files. Instructions favour hints rather than complete answers; this is a model instruction, not a guarantee. Each question's conversation is isolated, saved with the attempt, and included in backups. Starting a fresh conversation resets the next request's context while retaining previous guidance.

AI help is disabled during an unfinished Exam-mode attempt and available in Practice mode or post-exam review. Missing credentials, denied model access, rate limits, timeouts, empty and truncated responses produce explicit messages while retaining the student's draft. Requests have a 55-second timeout and a short per-session cooldown; there is no automatic billable retry. Set appropriate project quotas in Google AI Studio for a public deployment; the cooldown is not a global spending limit.

Official references: [model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), [generateContent API](https://ai.google.dev/api/generate-content).

## Saving: actual persistence contract

The custom Streamlit v2 component stores attempts in `localStorage` on the app's origin. Streamlit Session State alone is **not** used as durable storage. Each attempt is stored separately; a successful browser write is acknowledged before “Saved in this browser” appears.

Text edits reach Python on blur, then trigger browser saving. Wait for the saved status before closing. “Save & leave” pauses the timer. Exports/restored attempts are paused; an abrupt close may lose timer seconds since the last saved interaction. The timer is for practice, not tamper-resistant assessment. Feedback history retains up to 300 checks per question.

Clearing site data, changing browser/device, private browsing or storage quotas can affect persistence. Export a backup for important work. This is not account-based or cross-device sync. Backups do not contain students' external Excel workbooks or SQL-editor files.

Saved answers are transmitted to the running Streamlit server to render/check them; the application does not write submissions to a shared server database or application logs. Users sharing a browser profile can see its saved attempts.

Question snapshots preserve the original reference answers when content changes. Imported files are untrusted data and are validated; they are never executed. Imported “grades” are not certified. Student SQL and formulas are never evaluated by the server.

## Content and provenance

`data/catalog.json` records every question's exact source, worked approach, reference output, skill and dataset. Dataset records include SHA-256 checksums and source paths in the supplied archive.

`scripts/build_content.py` reproducibly builds the bank from the supplied `materials.zip`, unpacked to `research-sources/materials/`. It is a maintainer tool, not required on the deployed server. It does not retrieve data from the internet.

Content decisions:

- Preserve original source files, except for an explicitly labelled OSU 2014 P-card subset with all source columns. Answers apply to this subset.
- The large movies database is gzip-compressed in Git and decompressed for download.
- Restaurant models are fitted by ordinary least squares to actual daily aggregates from the supplied workbook. Coefficients displayed in questions are rounded to six decimals; answer calculations use those displayed coefficients. Prediction scenarios are explicitly hypothetical. Missing game records are treated as non-game days; rows missing model/weather data are removed.
- Regression explanations do not claim statistical significance from coefficients alone. No unsupported quadratic-regression task is introduced.
- Payroll change is explicitly 2016 minus 2015, resolving inconsistent source wording.
- Optional Fiftyville and optional P-card tasks are excluded. Coverage is curated, not exhaustive.

## Verify

```sh
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover output checking, malformed imports, backup round trips including AI conversations, timer arithmetic, catalog consistency, navigation, Gemini request/response contracts and Streamlit flows. Mocked API tests do not establish live model availability for a particular API key. Browser storage and refresh must additionally be checked in a real browser.

## Repository structure

- `app.py`: Streamlit screens and user flows.
- `exam_core.py`: pure answer comparison, snapshots and backup validation.
- `ai_tutor.py`: Gemini request construction, question context and error handling.
- `assets/`: browser storage, timer and visual styling.
- `data/`: reproducible catalog and downloadable course datasets.
- `scripts/build_content.py`: content-generation tool.
- `tests/`: domain and Streamlit tests.
- `ASSIGNMENT_DELIVERABLES.md`: improvement rationale and evaluation plan.
