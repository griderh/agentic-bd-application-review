# Governed Excel fact sheet: draft format and stewardship

> **Superseded as the target workflow (October 21, 2026).** The user chose evidence-backed extraction from supporting documents, conversational corrections, and optional Excel inspection/export instead of a human-maintained workbook. See the [current direction and implemented archive boundaries](evidence-review-workflow.md). This document describes the still-runnable earlier prototype, not a business requirement to maintain Excel. Automatic extraction and revisions are not implemented yet; existing inputs are preserved.

## What is implemented

This first increment validates **drafts** of recurring firm identity facts and named signer-role assignments. It does not publish an approved fact sheet, authenticate reviewers, resolve signers for a packet, or make answers fillable. Neither a clean validation report nor a person's name in JSON is evidence of authorization.

**The deliverable for business users is an editable Excel workbook (`fact-sheet.xlsx`).** JSON is an internal application format only. Maintaining facts must not require business users to edit it.

Period-specific financial values, disclosures, personal acts, notification addresses, signatures, and signature dates are outside this first draft schema. Financial reports and issuer-required attachments remain primary evidence. Do not turn absent evidence into a negative disclosure or guessed signer.

The business must name the responsible owner and control who may edit the maintained workbook. No separate auditor or second-person fact-sheet approval is required. The owner may maintain and check their own entries; `Reviewed by` can be the same person as `Owner`. This does not remove the signatories' existing review of the generated packet.

The business owner is responsible for source-data accuracy. A plausible typo may pass mechanical checks and lead to an incorrect application answer. The answering workflow must identify the exact fact-sheet version, record, and value used so a reviewer can distinguish a fact-sheet error from an extraction or generation error. That answer-generation linkage is not implemented yet; today's validation report records the input hash and fact records but generates no answers. Conflicting supporting evidence must still be flagged rather than silently overridden.

## Normal local PoC: one maintained workbook

The designated workbook is **`outputs/maintained/fact-sheet.xlsx`**, relative to the explicit data root. The business owner edits/checks/saves this file, not demo-generated copies. No separate auditor, code execution, or technical hash editing is required of the business maintainer.

The technical operator runs `bd-packet poc-init --root .` once to create the blank workbook. Setup refuses to overwrite an existing file and inserts no synthetic firm facts. Complete the steward field and at least one fact row before running intake.

The local operator then starts the PoC with `bd-packet poc --root .`. Each run automatically validates the same designated workbook using today's local date (or explicit `--as-of YYYY-MM-DD`), with no `--source` selection or separate validation command. Missing/invalid input is reported explicitly; no demo generation or automatic replacement occurs.

The maintained workbook is never rewritten. Each successful intake publishes a separate `validation.html` report, internal JSON, and an exact `input.snapshot.xlsx` under a unique `outputs/fact-sheet-check-<run-id>/` directory. The archived input is a run record, not another workbook to maintain. Do not use the maintained workbook's old Checks sheet as current results; open the HTML report printed by the application.

Intake success means those results were saved, even when they contain review exceptions. It is not approval, proof of factual accuracy, or completion of a packet. Packet generation and answer-level provenance remain unimplemented. A graphical launch/upload interface and production access controls are also outstanding.

## Developer-only self-contained synthetic example

**Developer/operator only:** with the development venv activated, from the repository root. Business maintainers do not run these commands:

```bash
python examples/fact_sheet_demo.py
```

This is a ready-to-run example, not a template needing files you must prepare first. It creates:

1. A synthetic PDF containing a fake legal name, leading-zero CRD, and named CCO.
2. A draft Excel workbook with actual source hashes and exact native-text evidence.
3. A new Excel workbook with three facts and one deliberately overdue review in its Checks sheet; JSON diagnostics are saved alongside it for the application.

All files are isolated beneath a unique Git-ignored `outputs/fact-sheet-demo-<run-id>/synthetic-root/` directory. The script prints the Excel location. It never reads repository business documents. The fixed evaluation date is October 21, 2026, so the overdue example remains reproducible when run later.

The demo requires development dependencies because ReportLab generates the synthetic PDF; the validation command itself uses existing runtime dependencies only.

## Draft contents

### Business-user workbook

| Worksheet | Purpose |
| --- | --- |
| Instructions | Field guidance, maintenance steps, and draft/not-approved warnings |
| Details | Version label, steward, format version, optional predecessor hash |
| Facts | One row per fact version, with value, category, owner, reviewer, and dates |
| Evidence | One row per supporting reference: fact Record ID, root-relative supporting document path, page, and exact quotation |
| Checks | Last validation's mechanical exceptions and evaluation date; **not approval** |

Edit the white data cells in Facts/Details/Evidence; keep the original column headings and worksheet names. Use `firm_identity` or `signer_role` categories and `text` or `identifier` value types from the dropdowns. Values and identifiers must remain text, including CRDs such as `001234`. Dates may be ISO `YYYY-MM-DD` text or Excel date cells without times. Do not enter formulas. Excel dropdowns and formatting are usability aids, not security or validation boundaries.

For evidence, use a path under `bd_agreements/supporting_data/`, the PDF page number, and an exact native-text quotation. Do not use completed packets or arbitrary external paths. The application resolves the source identity and quote offsets itself; a quote appearing more than once on the selected page is ambiguous and requires a more specific quotation. OCR/image-only pages are not supported as native quotes.

The hidden **Source SHA256** column is application-generated provenance, not a business editing field. A blank hash on new evidence is resolved to the current source version at validation, without approving that source. Keep generated hashes on unchanged evidence. A mismatch is a review exception, never silently updated; after deliberately reviewing replacement evidence, clear that row's hash to resolve it to the new version. This is a snapshot reference, not an authenticated approval or source archive.

Facts without evidence remain visible with exceptions. Unknown source paths, altered sources, missing/ambiguous quotes, and invalid pages do not discard otherwise supported facts. Malformed workbook structure, formulas in imported fields, numeric identifiers, orphan Evidence record IDs, or invalid mandatory metadata prevent publication with a safe error. Some schema errors identify the worksheet rather than an exact cell.

The Checks worksheet is a point-in-time report. **Every edit makes the previous results stale.** The business maintainer checks their edits and saves the maintained workbook; no code, terminal, JSON, or technical hash editing is required. Normal `poc` intake now validates automatically and writes a separate HTML report, not a new maintained workbook. Only the developer-only `fact-sheet-check` round-trip tool produces a workbook with refreshed Checks. Technical operators handle evidence-version changes; Excel filenames alone do not establish authorized history.

### Internal application schema

`FactSheet` and `Fact` in [fact_sheet.py](../src/bd_packet_builder/fact_sheet.py) define strict, versioned Pydantic schemas. Generate JSON Schema directly with `FactSheet.model_json_schema()`; no hand-maintained duplicate schema is needed.

| Sheet field | Meaning |
| --- | --- |
| `schema_version` | Format version, currently integer `1` |
| `version_id` | Steward-supplied draft label, not a verified release identity |
| `supersedes_sha256` | Optional claimed previous draft hash; not verified release history |
| `steward` | Named coordinator; this field does not authenticate a person |
| `facts` | One to 500 fact records |

| Fact field | Meaning |
| --- | --- |
| `fact_id` | Unique record ID, including among historical versions |
| `key` | Canonical lowercase lookup key such as `firm.legal_name`, `firm.crd`, or `signer_roles.cco` |
| `category` | `firm_identity` or `signer_role` |
| `value` | Typed text or string identifier; leading zeros are preserved |
| `role` | Required human-readable role for signer assignments; omitted for firm identity |
| `owner` | Person/team responsible for maintaining this fact |
| `reviewed_by`, `reviewed_on` | Claimed reviewer and date the fact was checked |
| `review_due` | Next review date; not an automatic renewal |
| `effective_from`, `effective_to` | Inclusive applicability dates; end may be null |
| `citations` | Up to 20 source/page/exact-quote citations from the supporting inventory |

An empty citation list is allowed in an unfinished draft but produces `missing_evidence`; it never means the fact has supporting evidence. A signer value must be text identifying a person, not just a numeric identifier. Whether the evidence establishes that person's role remains a human review responsibility.

Keys and role names must be standardized by the steward. The validator detects overlapping versions **under the same key**; it cannot discover that differently named keys/roles are aliases or that a factual claim was misleadingly categorized.

Extra fields, including self-declared `approved`, `approver`, or `released_at`, are rejected. Identifiers are not coerced from numbers, and only ISO dates are accepted at the JSON boundary. Reviewer and due dates are mandatory; incomplete review metadata must be supplied before schema validation succeeds. Dates do not prove a review took place.

## Validate a manually prepared local draft

**Technical operator usage template, not business-maintainer instructions:** first save an edited workbook following the template, under the explicit root's `outputs/` directory. This command does not generate or approve real firm facts:

```bash
bd-packet fact-sheet-check --root . \
  --source "outputs/fact-sheets/draft.xlsx" \
  --as-of 2026-10-21
```

The required `--as-of` date makes the evaluation date explicit; it is not the reporting period of a financial document. Paths are root-relative. Traversal, absolute input paths, and source/output symlinks are rejected. Draft input is bounded to 2 MiB. Supporting evidence is read only from the existing supporting-data inventory, never completed applications.

For the self-contained demo, use its generated `synthetic-root` as `--root`; a workbook beneath it is supplied relative to that root (for example `outputs/fact-sheets/synthetic-draft.xlsx`). Do not treat the demo's synthetic evidence as real firm evidence.

Excel ZIP contents are limited to 20 MiB expanded and 100 entries, 500 fact rows, and 10,000 evidence rows (at most 20 references per fact). Macro/external-link workbooks are rejected; formulas are not evaluated. XML parsing uses defusedxml. The legacy internal `.json` input remains supported for existing programmatic callers, but also produces an Excel deliverable. Users do not need to maintain it.

Every fact is checked; there is no implicit "latest wins" rule:

- Exact native-text quotations must resolve to a known, unchanged source version and valid page.
- Missing/unknown evidence, altered quotes, future reviews, not-yet-effective/ended facts, and overdue reviews appear as per-fact exceptions.
- `review_due` and `effective_to` include their stated day; they are not overdue/ended until the following day.
- The scope requires review on change and at least annually. A scheduled review beyond the next calendar-year anniversary is flagged. A February 29 review has a February 28 anniversary in a non-leap year. Earlier due dates remain meaningful.
- Overlapping effective intervals for the same key produce duplicate/conflict exceptions on **both** records, even if the values match. Adjacent intervals sharing an endpoint overlap. Nonoverlapping history stays visible and is flagged if no longer effective on the evaluation date.

Exact quote resolution does not show that a value occurs in the quote, that the quote supports the fact, or that the source/reviewer is authorized. Those remain explicitly unverified. Unknown or unconfigured required keys cannot be inferred: report coverage is only the supplied fact records, not proof that a complete fact sheet exists.

Output is a unique `outputs/fact-sheet-check-<run-id>/` containing **`fact-sheet.xlsx`** for business use and **`fact-sheet-check.json`** for internal diagnostics. The JSON records the input workbook hash, version claims, evaluation date, values/evidence, and every record's check result. The console prints counts and output locations, not fact contents. Both files are published together after source/input rechecks; a workbook write failure must not leave a successful JSON-only run. A zero exit status means files were written, **not** that the draft is approved or free of exceptions. Each internal fact check has `usable_for_filling: false`.

Schema, access, source mutation, write, and detected draft-change failures do not publish successful reports. Draft and supporting hashes are rechecked around atomic publication; normal failures clean staging. This is not an immutable archive, filesystem sandbox, or complete concurrency guarantee.

## Business process before any approved release

### Production handoff: one maintained workbook

The unique demo directories are development snapshots, not the intended business-maintenance layout. Before production handover:

- Establish **one clearly designated maintained Excel workbook** at a configured, access-controlled location; tell the business owner exactly which file to edit.
- Keep historical snapshots and validation outputs in a separate archive. They must not appear as competing current workbooks.
- Configure application intake to read that designated workbook and validate automatically. Do not select a current workbook by modification time or folder order.
- Record the exact input hash/version and fact records used for each run. Business users do not run code, and no separate auditor is required.
- Exclude synthetic demo workbooks and synthetic supporting evidence from production intake. Review obsolete demo artifacts for deliberate cleanup/retention; do not automatically delete business records.

The local PoC now implements the fixed maintained path, automatic intake validation, and separate input snapshots/results. Production location selection, permissions, retention and handover remain acceptance requirements tracked in [M5 of the development plan](development-plan.md#m5---deferred-production-integrations-and-operational-hardening).

1. **Business owner maintains and checks:** update the Excel values, evidence references, and review dates. The same person may own and check an entry. Check for typos before saving; no separate auditor or fact-sheet approver is required.
2. **Business owner saves:** preserve the previous version and provide the updated workbook to the local technical operator. Do not run code or maintain JSON or hidden hashes.
3. **Technical operator starts the PoC:** `bd-packet poc --root .` validates the designated workbook automatically and produces a separate HTML results report. This is technical processing, not an independent audit or business approval. The owner resolves factual issues in the same workbook. Confidential files stay in access-restricted storage, not Git or ordinary test fixtures.
4. **Application intake:** the local PoC reads the designated workbook and checks structure/evidence/dates/conflicts, recording its exact bytes/hash and supplied records in internal run results. Production access controls for that location still need implementation, not a second-person audit or editable approval flag.
5. **Future builder consumes:** use supported facts with traceable version/record/value references; continue supported work with explicit exceptions for unsupported or conflicting facts. Do not claim that successful validation guarantees factual accuracy.
6. **Business owner keeps current:** review on change and at least annually. Correct source-data errors in the workbook; retain prior versions. Packet signatories still review completed applications before signing.

Step 4's local intake is implemented; production authorization and step 5's answer-generation linkage are not. The validator still makes no facts fillable and does not authenticate workbook ownership. Local files and hashes alone do not enforce authorization or tamper-resistant history. This technical gap is not a requirement for a separate human approver.

The AI may eventually propose updates, but may never self-approve them or change recipients/permissions through document text.
