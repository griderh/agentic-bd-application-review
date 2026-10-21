# agentic-bd-application-review
This agentic AI application reviews broker-dealer application requirements and constructs the application using supporting documentation such that it can be reviewed and submitted by signatories

## Project documentation

- [Phase 1 scoping document](Broker-Dealer%20Packet%20Automation%20Phase%201%20Scoping%20Document.md): business requirements, boundaries, and evaluation criteria.
- [Development plan](docs/development-plan.md): milestones, dependencies, acceptance criteria, and open implementation decisions.
- [Copilot coding instructions](.github/copilot-instructions.md): repository-wide Python, test-driven development (TDD), grounding, and data-handling standards.

## Development status

The foundation, local evidence inventory, native-PDF text, and opt-in local OCR experiment are implemented: a Python package, offline synthetic tests, lint/type checks, deterministic monthly/annual filename selection, read-only source metadata, page-level native text and literal date checks, single-page OCR, and a narrow native-field PDF feasibility demo. This is not yet an automated application-completion workflow. Foundry integration, governed fact extraction, integrated OCR validation, flattened overlays, reviewer summaries, and packet assembly remain future increments.

The initial deliverable is a locally executed Python PoC using [blank forms](bd_agreements/Blank/) and [supporting documents](bd_agreements/supporting_data/) already in this repository. It calls a remote model through an approved Foundry endpoint, validates the results, and generates outputs locally; the model does not directly access the local folders. [Completed packets](bd_agreements/Completed/) support validated evaluation and wording precedent, not current factual authority. Network-drive mapping, cloud application hosting, Azure Blob document storage, and production integrations are deferred until the working PoC has been reviewed.

Treat business samples and generated outputs as potentially confidential. Do not publish them, copy them into ordinary test fixtures, or upload them to model/OCR services without approved access. Use synthetic or sanitized fixtures for offline development and CI.

## Local setup

Use Python 3.12 (validated locally with 3.12.13). From the repository root on macOS or Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-build-isolation --no-deps -e .
python -m pip check
```

On Windows, create the environment with `py -3.12 -m venv .venv` and activate it with `.venv\Scripts\Activate.ps1`, then use the same `python -m pip` commands. Windows execution has not yet been validated.

Dependencies, including transitive packages, are pinned in [runtime requirements](requirements.txt) and [development requirements](requirements-dev.txt). Package metadata and tool settings live in [pyproject.toml](pyproject.toml). No uv, Azure credentials, or model access is needed for this increment.

## Quality checks

With the venv activated:

```bash
python -m pytest --cov --cov-report=term-missing
python -m ruff check .
python -m ruff format --check .
python -m mypy
```

Tests generate synthetic PDFs in pytest temporary directories; they do not read business samples, use network drives, or call models. The [CI workflow](.github/workflows/ci.yml) runs the same checks on Linux and macOS without uploading document artifacts. Local checks are verified separately from GitHub-hosted CI, which runs after changes are pushed.

## PDF feasibility demo

Inspect structure without printing extracted document text or field values:

```bash
bd-packet inspect "bd_agreements/Blank/New_Mexico_State/NMSTO - FY26-27-B_D-Application.pdf"
```

Explicitly run the demo against the local NMSTO blank form:

```bash
bd-packet demo --root . \
  --source "bd_agreements/Blank/New_Mexico_State/NMSTO - FY26-27-B_D-Application.pdf"
```

The demo writes only the fixed value `SYNTHETIC POC - NOT FOR SUBMISSION` into a recognized native firm-name field. It cannot accept arbitrary field/value assignments. All other fields, including signatures and signature dates, remain unchanged and blank. It rejects prefilled, encrypted, unsupported, and digitally signable forms rather than pretending to complete them. It does not read completed applications or support documents and makes no network calls.

Each run creates a unique directory under the explicit root's Git-ignored `outputs/` folder:

- `demo.pdf`: synthetic demonstration only, not a completed or submission-ready application.
- `before.png` and `after.png`: first-page renders for local placement inspection.
- `manifest.json`: source/output hashes, page count, synthetic value, and demo status.

Paths for `--source` are relative to `--root`, not the current directory. Sources must remain within `bd_agreements/Blank/`; source and output symlink escapes are rejected. Results are published only after writing/rendering succeeds and the source hash is rechecked. Originals are never overwritten. Do not submit or sign demo outputs.

The current demo requires exactly one recognized native firm-name text field (`Name of Firm` or `Firm_name`) on page one. Flattened forms such as Broward require a later overlay/layout implementation; legacy Word conversion is also not implemented.

## Local supporting-document inventory

With the venv activated, explicitly inventory the local supporting documents:

```bash
bd-packet inventory --root .
```

Only `bd_agreements/supporting_data/` under the explicit root is scanned; blank and completed packets are excluded. A unique, atomically published `outputs/inventory-<run-id>/inventory.json` contains:

- Root-relative source paths, stable path-and-content identities, SHA-256 versions, byte counts, formats, and PDF page counts.
- Filename-derived periods with explicit precision and `filename_only` provenance.
- Duplicate-content flags retaining every source path, plus unreadable/encrypted PDF and unavailable-page flags.
- Visible excluded-input issues and filename-based selections for monthly `Focus_Reports` and annual `Audited_Financials`.

The console prints counts and the output location, not filenames or document text. All sources carry `content_date_unverified`; a flagged-source count does not mean every file is broken. Treat the local manifest as potentially confidential metadata, not a submission document.

Sources remain read-only. Source/output symlinks are rejected, unsupported inputs are recorded, and access errors or detected changes abort publication rather than silently skipping evidence. Each source is limited to 64 MiB. Hashes are rechecked before publication. The manifest records versions but does **not** copy or archive immutable source files; additions/removals after the scan require a new inventory. The internal page-reference resolver checks known source identity, unchanged bytes, and a valid one-based PDF page, not whether that page supports an answer. No external/model manifest loader is implemented.

The local validation run found 27 sources (25 PDFs, one PNG, one DOCX), one identical-content duplicate pair, and 195 PDF pages. No sources were modified and no document content was uploaded. PDF page-count inspection is not a rendering, OCR, or semantic-readability check.

### Source-selection rules and remaining limits

[select_document](src/bd_packet_builder/sources.py) is a pure function over paths from **one homogeneous document family**. It chooses the requested period when present, otherwise the latest available period, and returns explicit missing/ambiguous/unparseable/mismatch flags. A missing requested period may return available evidence with a mismatch; that does not mean it satisfies the issuer's request.

Monthly parsing recognizes one `YYYY-MM`, `YYYY_MM`, or English month/year such as `Aug2026`, `Feb2023`, or `Sept 2021`. Annual parsing requires explicit annual cadence and a single year. Ambiguous compact dates, competing years, and unsupported date patterns remain unresolved. File modified time and folder order never determine the selected period.

The inventory enables version selection only for FOCUS reports and audited financials. Other folders, including biographies and mixed Bloomberg products, are inventoried without assuming their files form one version series. An unreadable selected PDF does not silently fall back to an older report; it leaves selection unusable with a flag. Duplicate latest periods remain ambiguous even when bytes match. Excluded inputs within a versioned family prevent a potentially misleading selection.

Broad content-period verification, approved staleness policy, governed fact sheets, fact extraction, exact-value/cross-field checks, and semantic grounding remain M1/later work. The native-text increment below provides only narrow literal reporting-date corroboration. There are no model-evaluation results because no model was called.

## Native PDF text and reporting-date evidence

Explicitly extract potentially confidential native text to a local, Git-ignored output:

```bash
bd-packet evidence --root .
```

This rebuilds the supporting-document inventory and writes a unique `outputs/evidence-<run-id>/evidence.json`. **Unlike the metadata inventory, this file contains document text.** Keep it local and restricted; do not commit it, upload it as a CI artifact, or include it in a submission packet. Console output contains only counts and the output location. No external service, model, or OCR call occurs.

The bundle records source paths/hashes, one-based PDF page numbers, native page-area text, extraction flags, and versioned deterministic reporting-date checks. Page order is preserved, including empty pages. Text offsets are Python string indices after CRLF-to-LF normalization, not PDF coordinates. The internal quote resolver re-extracts the current referenced page and checks the exact substring; a valid quote still does not prove that it supports an answer.

The initial reporting-date rules recognize:

- Monthly FOCUS: line-leading `As of`, `Reporting period ended`/`Period ended`, or `For the period beginning ... and ending`, followed by a full English month/day/year or ISO date.
- Audited financials: a `Statement of Financial Condition` heading immediately followed by a full date, optionally prefixed by `As of`.

Other dates, ambiguous numeric dates, partial dates, and unfamiliar wording are not guessed. Distinct labeled dates produce a conflict; mismatches remain explicit. A recognized date corroborates only the filename's month/year or year, not source approval, entity identity, fiscal-year-end policy, freshness, or semantic adequacy. Any page lacking usable native text, or an unrecognized labeled date, prevents a complete-document corroboration. The original metadata inventory's `content_date_unverified` flags are deliberately retained.

Supported pages continue when another page has no text or a native extraction error. PNG/DOCX and unreadable/encrypted PDFs remain visible but have no native-page evidence. No-text pages may be scans, blank pages, or other content; this command cannot distinguish them or establish visual readability. Native text order and fidelity are not assumed to match rendered layout.

Limits are visible in the bundle and configurable:

```bash
bd-packet evidence --root . \
  --max-pages-per-document 500 \
  --max-chars-per-page 100000 \
  --max-chars-per-run 5000000
```

These are the defaults; source reads retain the inventory's 64 MiB limit. Limits must be positive integers. A limit violation aborts rather than publishing truncated evidence. Sources are rechecked after extraction and before/after output writing; detected mutation or I/O failure prevents publication and cleans staging. This is not an immutable archive, concurrent-filesystem isolation, or a hard wall-clock/memory sandbox for native PDF parsing.

The explicit local run retained 195 PDF pages from 27 supporting files: 124 pages had usable native text and 71 did not. All six configured financial-document period checks stayed unverified; the three audited statements yielded labeled date observations but lacked complete native-text coverage. All 27 source hashes remained unchanged. OCR feasibility is needed before claiming complete coverage of these inputs.

## Opt-in local OCR feasibility

Tesseract is an optional **system dependency**, separate from the Python venv. No Python OCR wrapper, model SDK, or remote OCR service is needed. The experiment requires Tesseract 5.x and English trained data. Local validation used Tesseract 5.5.3; distribution-provided versions and trained data are not locked by the Python requirements files.

On macOS:

```bash
brew install tesseract
tesseract --version
tesseract --list-langs
```

On Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-eng
```

Check that `eng` is listed and the `tesseract` executable is on `PATH`. Windows OCR setup has not been validated. Tesseract uses the Apache-2.0 license; retain applicable engine, trained-data, and dependency notices if redistributing.

With the Python venv activated, explicitly choose **one** supporting PDF and one-based page:

```bash
bd-packet ocr --root . \
  --source "bd_agreements/supporting_data/Focus_Reports/InspereXLLC_Aug2026_FocusReport-Public.pdf" \
  --page 1
```

The command renders that page locally at 300 DPI, runs English Tesseract with page-segmentation mode 6 (single text block), and writes a unique `outputs/ocr-<run-id>/ocr.json`. The source must be in the read-only supporting-document inventory; blank/completed packets, non-PDFs, unreadable/encrypted sources, symlinks, and invalid pages are rejected. Source hashes are rechecked before and after output writing. The command does not modify the PDF or add a text layer.

The result includes the source identity/hash, selected page, engine version, rendering hash/dimensions, text, and per-word bounding boxes and engine-confidence scores. Boxes use **rendered pixels from the top-left**, not PDF points; line grouping follows Tesseract's block/paragraph/line hierarchy, not reconstructed table cells. The temporary page image is removed after processing. The JSON contains potentially confidential text and remains local and Git-ignored. The console does not print page text or raw engine diagnostics.

**OCR is unverified.** The output always carries `ocr_unverified` and `not_semantic_grounding`, and an empty recognition result adds `no_ocr_text`. It is separate from the native evidence bundle: no automatic OCR fallback, native-text replacement, quote-resolution integration, reporting-date promotion, or financial-value approval is implemented. A confidence score is not an accuracy percentage or approval threshold. Scans, table relationships, financial punctuation, handwriting, rotations, and layout require further evaluation.

Optional positive-integer limits:

```bash
bd-packet ocr --root . \
  --source "bd_agreements/supporting_data/Focus_Reports/InspereXLLC_Aug2026_FocusReport-Public.pdf" \
  --page 1 --timeout-seconds 30 --max-pixels 20000000 --max-output-bytes 4000000
```

These are the defaults. The timeout applies to each Tesseract process; the pixel limit is checked before rendering, and engine output size is checked before parsing. Output is spooled to a temporary file rather than accumulated in memory during the process. This is not a hard temporary-disk quota or a timeout/memory sandbox around PDFium rendering. Limits, malformed output, engine errors, and timeouts fail explicitly without publishing a successful run; working files are cleaned up on normal exceptions. Missing Tesseract does not affect native extraction or default tests.

### OCR verification and limits

Default tests mock the engine boundary for deterministic safety/error contracts. Explicitly run real recognition against a generated **image-only synthetic PDF**, without business documents:

```bash
BD_RUN_OCR=1 python -m pytest tests/integration/test_ocr.py -m ocr -v
```

The local fixture recovered 6/6 exact target strings on one clean synthetic page: a heading, date, decimal financial value, leading-zero identifier, and two simple labeled numeric rows including parentheses. This is a small feasibility case, **not** a corpus accuracy or table-reconstruction metric. The Linux CI job installs Tesseract and runs this opt-in test; macOS CI retains the default synthetic contract suite. The added CI step must be verified on GitHub after pushing.

An explicit local run on page 1 of the August 2026 FOCUS report produced 551 OCR words; 128 had engine confidence below 80. This is diagnostic output only, not a measured error count: that business page has no independently annotated accuracy result. Its source hash remained unchanged. No documents were uploaded or submitted to a model.

See the [foundation decision record](docs/decisions/0001-local-foundation.md) for library choices, verified behavior, and remaining work.
