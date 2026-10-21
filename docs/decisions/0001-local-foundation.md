# 0001 - Local Python and native-PDF foundation

Date: October 20, 2026.

Status: accepted for the first deterministic feasibility increment; not a complete M0 or production architecture decision.

## Context

The [development plan](../development-plan.md) calls for a local PoC using repository documents, followed by Foundry model interpretation. We first need reproducible tooling and direct evidence that native PDF form values are visible after writing.

Local inspection found:

- NMSTO: three pages, 45 native fields, including 43 text fields.
- Princeton: seven pages, 75 native fields.
- Both Broward PDFs: no native fields; later layout/overlay work is necessary.
- Carrollton blank inputs are legacy Word files; conversion or approved PDF originals remain an open scope/input decision.

Only blank form structure was inspected. No completed answers were used to derive facts or populate the demonstration.

## Decisions

- Use Python 3.12, validated with the locally available 3.12.13. The selected PDF packages support this minor version; current `azure-ai-projects` package metadata also permits it. Final SDK/framework and hosting compatibility remain to be verified when those components are selected.
- Use standard venv/pip and fully pinned runtime/development requirements. Keep tool/package configuration in `pyproject.toml`.
- Use pypdf for native field inspection and writing (BSD-3-Clause), pypdfium2/PDFium for local rendering (BSD/Apache and bundled dependency notices), and Pillow for image handling (MIT-CMU). Use ReportLab (BSD) only to create synthetic test fixtures, not as a runtime dependency.
- Keep bundled PDFium/dependency license notices intact; review redistribution requirements if packaging a deployable application. No remote PDF/OCR service or AGPL PDF library is introduced.
- Restrict the experiment to fixed synthetic text in recognized firm-name fields, never arbitrary assignments or signature/date entry.
- Use immutable selection results and deterministic monthly filename parsing for the first source-selection rule, with explicit unresolved/mismatch flags. Storage inventory and irregular historical naming are not silently inferred.
- Do not install/select a model SDK, framework, OCR system, or hosting stack yet. No model calls, Azure provisioning, or network-drive integration are required for this increment.

## Verification and consequences

TDD began with failing imports for the not-yet-implemented modules. Integration testing then caught a substantive rendering failure: the field value was saved but the before/after images were identical. Initializing PDFium's form environment before rendering fixed the failure; the regression asserts a visible change confined to the synthetic form's target rectangle.

Synthetic tests cover source periods, ambiguity and missing sources, signature/date preservation, output isolation, path traversal/symlink rejection, prefilled/encrypted input rejection, render-failure cleanup, and CLI failure status. A separate explicit local NMSTO experiment demonstrated a visible synthetic answer in the firm-name field without changing the original.

Strict mypy checks application code. PDFium lacks packaged typing, so a targeted missing-import override is limited to that dependency, whose use is isolated in the renderer. This is not blanket type-check suppression.

This proves a narrow native-field path, not general document completion or zero hallucinations. Flattened overlays, OCR, page-coordinate validation across issuers, evidence interpretation, full packet assembly, retry/resume, and the final held-out evaluation remain outstanding.

## Follow-on: first local evidence-inventory slice

The inventory uses the existing PDFium dependency to inspect in-memory PDF bytes without extracting text. Encrypted or unparseable PDFs remain visible but unusable for page evidence. The native PDFium security-handler check also rejects encryption with an empty password. No new dependency, service, model adapter, or framework was needed.

Internal immutable dataclasses represent metadata and references; strict reference checks reject malformed identities, coerced page values, unknown sources, stale bytes, and out-of-range pages. These are not external/model payload schemas or proof of semantic support. Source identities combine relative path and content hash so identical files at different paths retain distinct references.

Only the designated supporting-data tree is scanned. Known document extensions are inventoried; excluded formats and symlinks produce visible issues. Access failures, detected source mutation, oversized sources, and publication failures are technical errors, not successful partial snapshots. Per-source reads are bounded to 64 MiB. Output is staged in a unique local run and atomically renamed; input hashes are rechecked before publication. Concurrent file changes can invalidate the metadata snapshot, so references must be revalidated before later use; this does not provide an immutable archive or an operating-system isolation boundary.

Historical month/year spellings and explicit annual cadence extend the original pure selector. Only FOCUS and audited financials are configured as homogeneous version families. Biographies, mixed Bloomberg products, and ambiguous legacy dates are not guessed into one latest-document series. No modified timestamps determine selection.

TDD observed missing-module and historical-period failures before implementation. Synthetic regressions cover version selection, duplicates, missing/mismatched periods, corruption/encryption, invalid references, symlinks, source mutation, output-write cleanup, size limits, and safe CLI errors. An explicit local run inventoried 27 business-support files with one duplicate-content pair; all source hashes matched afterward. Content dates remain unverified, and extraction, staleness policy, governed facts, and semantic evaluation remain future work.

## Follow-on: native text and literal reporting dates

Use the existing PDFium dependency for native page-area text, with strict Unicode decoding and explicit resource cleanup. Its bounded-text API supports full Unicode; its range-text API is UCS-2-limited and its internal character indices can differ from returned string indices. Citations therefore use offsets into extracted text with CRLF normalized to LF, not internal PDFium offsets or PDF coordinates.

Reuse inventory source-version reads and a shared staged JSON publisher. Both metadata and text publication now recheck source hashes after output writing and immediately before atomic rename; a regression first demonstrated that mutation during writing previously escaped the pre-write check. This improves detected-mutation handling but does not replace immutable source archiving or operating-system permissions.

Only explicit, narrowly labeled reporting dates are compared to filename periods. This is literal corroboration, not a claim of fiscal-year correctness, report/entity identity, or factual support. Multiple distinct dates, unfamiliar date forms, incomplete native-text coverage, and filename mismatches remain review exceptions. Do not silently select an older source or overwrite the inventory's unverified status.

Native text may be incomplete, out of reading order, or inconsistent with visible content. OCR and rendered validation remain necessary. The local run found usable text on 124 of 195 pages; all six financial-document date checks stayed unverified. No dependency, service, model integration, real-document fixture, or remote upload was added.

TDD started with missing-module failures and includes page/quote provenance, reporting-date matches/conflicts/mismatches, no-text pages, extraction failures, strict limits, source mutation, and staged-write cleanup. Model-quality metrics are not applicable: this increment makes no model calls.

## Follow-on: optional local Tesseract feasibility

Date: October 21, 2026.

The user approved local Tesseract after considering local OCR, Azure Document Intelligence, and Foundry vision. Start with a bounded single-page experiment, not automatic conversion of all textless pages. The native evidence command and reporting-date rules remain unchanged. No remote service or Python OCR package is added.

Use Tesseract 5.x with English data, 300-DPI PDFium rendering, and page-segmentation mode 6. Record the actual engine version and rendered-image hash. Local installation is Tesseract 5.5.3 through Homebrew; system packages and English trained data are not pinned by pip. Treat distro/version variation as an evaluation concern, not proven equivalence. Respect Apache-2.0 and bundled dependency/data licenses when redistributing.

The subprocess receives fixed arguments and a generated temporary image path, never document-supplied commands. Suppress raw engine diagnostics, enforce process timeouts, check raster size before rendering, and spool output before bounded parsing. TSV word data is validated for hierarchy, finite confidence, and in-image geometry. Record the original source/page/hash and top-left pixel coordinates; do not imply PDF-point geometry, table cells, or trustworthy financial facts.

The image and raw TSV are temporary; only unverified local JSON is published using the shared source-rechecking, atomic-output boundary. Failures clean working files on normal exception paths. This does not provide a disk quota, native-rendering sandbox, immutable source archive, or protection from every concurrent filesystem race.

TDD observed the missing module before implementation. Contracts cover source/page limits, symlinks, unavailable/unsupported engines, timeout/failure cleanup, malformed TSV, invalid word geometry/confidence, source changes, empty recognition, and safe CLI output. Real OCR tests are explicitly opted in and use generated image-only PDFs. One clean synthetic page recovered 6/6 exact target strings; this does not establish general OCR, table, or model quality.

A local FOCUS page produced 551 words, 128 below engine confidence 80; no independent transcript exists to turn those scores into accuracy. The source hash remained unchanged. Default tests do not require Tesseract; an added Linux CI step installs it and executes the real synthetic recognition test. Remote CI verification remains pending the next push.

PDFium's runtime documentation accepts float render scale, but its untyped `scale=1` default causes Pylance to infer integer-only input. A narrowly scoped `reportArgumentType` suppression is limited to the float-scale call; actual 300-DPI rendering is covered by integration tests. No blanket type suppression or cast is introduced.

## Follow-on: application-driven contracts

Use the already planned Pydantic boundary for untrusted application interpretation and answer proposals. Pydantic 2.14.1 supports Python >=3.10; its required core is pinned to 2.50.1, with annotated-types 0.8.0, typing-inspection 0.4.4, and typing_extensions 4.16.0 pinned in runtime requirements. Fresh Python 3.12 installation and focused contracts tests were verified. No additional framework or model SDK is introduced.

Keep application requirements separate from answer proposals so a proposed value cannot override the issuer's expected type, financial unit, or requested period. Preserve the actual instruction, application hash/page, and signer role. Require typed values and resolvable native quotations rather than accepting a citation string or confidence score as proof. Unknown extra fields and unintended scalar coercion fail schema validation. A regression caught Pydantic's literal-version comparison accepting `true` and `1.0` as version 1 even under strict configuration; an explicit integer-type check now rejects them.

Money crosses JSON as a bounded plain decimal string with explicit units and converts to `Decimal`, never binary float. String identifiers preserve leading zeros. False and zero are valid sourced proposals, not substitutes for missing evidence. Proposed attachments identify sources, not arbitrary paths or delivery actions.

Schema validity and literal quote resolution never approve a value. All check results leave `fill_value` unset, with explicit source approval, semantic support, and application interpretation still unverified. Reporting-period claims are proposals only; no filename or model claim bypasses the observed filing/reporting-month ambiguity. Signature fields and signature dates defer to human signing. A technical source-change/I/O error propagates rather than being disguised as missing evidence.

No new command, application parser, PDF field writer, fact sheet, OCR integration, or external payload logging is added. JSON Schemas are generated directly from the models rather than duplicated as hand-maintained files. Contract tests are synthetic/offline and demonstrate malformed payload rejection and non-approval, not model grounding quality. A real but unrelated quote is explicitly tested to remain unfillable.
