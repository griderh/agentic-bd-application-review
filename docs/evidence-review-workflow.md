# Evidence-first generation, reviewer revisions, and historical reference checks

## Agreed direction

The [scope](../Broker-Dealer%20Packet%20Automation%20Phase%201%20Scoping%20Document.md) now calls for:

1. Interpret the current blank application's requirements.
2. Propose answers from approved independent supporting documents, preserving source/version/page and reporting context.
3. Validate current proposals before a bounded historical comparison. The archive cannot supply missing current facts.
4. Continue supported work and present exceptions; humans should intervene only where necessary, plus the required final packet review/signing.
5. Accept reviewer corrections conversationally against a specific packet version, verify the supporting evidence, regenerate/revalidate affected outputs, and return the new version and change summary.

No human-maintained fact sheet is required. An Excel inspection/export view is optional, not a second editing system to synchronize. Store facts, evidence, checks and correction history as internal JSON, separately from submission packets. Do not create a fresh Excel workbook each run.

For revisions, distinguish wording/format changes, document-supported factual changes, and reviewer-only assertions. A statement supplied only in chat is not document evidence; preserve its reviewer-provided origin and leave unsupported answers unresolved. Packet-specific corrections must not silently update future packets or source documents. No separate auditor is needed, and no signature/date/submission permission is introduced.

Foundry hosting and a possible Microsoft 365 Copilot conversation surface are deployment candidates, not prerequisites for offline contracts. Publishing a conversation surface does not itself supply document revision, authorization, storage or concurrency controls.

## What is implemented now

The [requirement-driven retrieval command](../README.md#requirement-driven-evidence-retrieval) now connects supplied typed requirements, a lightweight source-family catalog, validated model routing, conservative document/version selection, bounded native page reading and unapproved answer proposals. It does not extract a whole drive or require business-authored fact values. Attachment-only content is excluded from answer requests; every proposal is restricted to the pages inspected for that requirement. Supported needs continue while missing/ambiguous sources, unsuitable periods and search limits are reported. Catalog descriptors are not source approval.

The initial window is normally pages 1 and 2, with expansion through the first four pages if terms are absent, within eight pages total. This is a bounded local slice, not general document search. Local OCR can inspect selected sparse/image-dominant pages, including landscape/rotated scans, but remains unverified and cannot ground native answer proposals. An exact-context cache can reuse unapproved native proposals after current source/page/citation rechecks; it does not supply a trusted cross-form fact register. Discovery-to-approved-requirements handoff, semantic support approval, reviewer-facing packet summaries and final document release are still unfinished. See the README for commands and precise limits.

The [history module](../src/bd_packet_builder/history.py) supplies strict offline contracts and a manual-input checker. It does **not** search an archive, extract historical questions/answers automatically, generate current answers, judge narrative support, revise PDFs, or integrate a model/chat service.

A separate [opt-in Foundry smoke command](../README.md#opt-in-synthetic-foundry-connection-test) tests one direct model request using fixed synthetic evidence only, with strict output and explicit usage/behavior checks. It neither supplies historical packets nor connects the history/workbook commands to a model. Live verification passed 6/6 controlled assertions on October 23, 2026 using the resource-scoped Foundry User role, standard Azure OpenAI hostname and Cognitive Services token audience; no general grounding evaluation or document-answering workflow is claimed.

A subsequent [synthetic PDF-to-proposals experiment](../README.md#synthetic-pdf-to-proposals-experiment) now exercises native extraction, model-suggested typed answers and the existing citation/review contracts together. The app generates its fictional source documents; users supply none. The model sees extracted supporting evidence and predefined requirements, not held-out expectations or completed applications. One live synthetic case passed 9/9 requirement assertions; values remain unfillable pending the production approval/grounding gates. This is not automatic requirement discovery, archive integration, packet generation or a real-document answering workflow.

The [real blank-form discovery experiment](../README.md#real-blank-form-requirement-discovery-experiment) now generates unapproved requirement candidates from one explicitly authorized blank PDF without a predefined question list. It validates native quotation spans, separates repeated sections using returned context, withholds ambiguous findings, and optionally scores an independent local-only anchor checklist. The revised Broward run covered 82/82 checklist anchors with 71/72 findings literally anchored; an `Other` blank, narrative type classification and cross-page condition interpretation remain unresolved. Anchor coverage is not completeness/semantic approval. These results are not yet automatically handed to the answer workflow; no supporting documents, history or packet output are involved.

The subsequent [choice/narrative layout increment](../README.md#choice-groups-write-ins-and-narrative-layout) separates response structure from visual controls. Choices use explicit option IDs with their own instructions and conditional write-ins; narrative values remain evidence-backed proposals. A developer-only Broward subset mapping, annotated renders and fictional inline/overflow previews exercise the geometry locally without approving or filling applicant answers. Narrative overflow preserves the full response for a question-labeled supplement rather than confusing a supplemental answer with evidence. Packet references come from ordered submission-section pagination, never model-guessed page numbers; the reviewer summary is excluded. Actual supplement assembly and final packet reference/render checks are not yet implemented.

Existing `poc`, `poc-init`, `fact-sheet-check`, and synthetic Excel tools remain runnable for compatibility and testing. Their workbook-input workflow is an earlier prototype, **not the target evidence-first user experience**. We have not changed those commands to pretend model extraction exists. The maintained workbook and previous outputs have not been deleted or overwritten.

## Archive separation

A trusted technical/evaluation custodian explicitly prepares an `ArchiveManifest` JSON under the local root's Git-ignored `outputs/`. Each entry supplies:

| Field | Contract |
| --- | --- |
| `path` | Canonical root-relative PDF path under `bd_agreements/Completed/` |
| `sha256` | Exact content hash; filename or modification time is not a version |
| `partition` | `reference` or `evaluation` |
| `issuer` | Explicit issuer context |
| `completed_on` | Completion date, or null if unknown (unknown prevents comparison) |
| `reporting_period` | Optional start/end dates; unknown is not inferred from filename |

Unlisted files are inaccessible through the reference reader. Paths, symlinks, nonregular files, traversal and oversized files are rejected. Every listed PDF's bytes are hashed to check the manifest, including evaluation PDFs, but **evaluation PDF text is never extracted or returned by the reference reader**. Hashing is a trusted local verification operation, not exposing held-out answers to a model.

The manifest rejects identical content assigned to reference and evaluation partitions, even under different filenames. Actual bytes must match declared hashes. The historical-check command also rejects exact copies of any listed archived packet in the current supporting inventory. Current proposal citations still resolve only against the supporting-data inventory.

These controls enforce an explicit manifest, not the trustworthiness of whoever edits it. Editable partition labels do not authenticate dataset assignment. The custodian must control manifest/storage access and preserve evaluation splits by issuer/template family. Copies with altered bytes, derived text/annotations, manually supplied leaked answers, and semantic near-duplicates cannot be detected by exact PDF hashes. Keep held-out answers **and derivatives** out of requests, prompts, retrieval, examples and caches operationally; a future ingest/lineage system must enforce those routes. No automatic partitioning or evaluation scoring is implemented here.

Limits: 500 listed PDFs, 64 MiB per PDF, 2 MiB per JSON input, 100 comparison pairs, 500 current requirements/proposals, and 100,000 native characters per selected historical page. Source files remain read-only. This is not an OS sandbox or immutable archive.

## Discrepancy request and result

`HistoryRequest` contains the current issuer, existing strict `ApplicationRequirements` and `AnswerProposals` sets, and explicitly selected historical pairs. Each pair includes:

- Current requirement ID.
- Historical permitted PDF path and hash.
- Page and exact native quotation.
- Manually supplied historical question, typed value, and optional signer role.

The historical quote is checked against the selected PDF page. It does not establish that the question/value actually follows from that quotation. Report flags explicitly retain unverified historical answer support and question mapping. Current proposals are checked with the existing evidence checker; semantic support, source authorization, blank-PDF identity and actual requirement interpretation remain unverified.

Comparison is conservative:

- No proposed current answer, rejected citations, or signing fields: `not_comparable`, never filled from history.
- Unknown/excluded reference or version/quote problem: `not_comparable`; excluded reference payloads are not echoed into reports.
- Different issuer, question text, reporting period or signer role, unknown completion date, different value kind/unit: `not_comparable`, not a current-answer error.
- Money requires known matching reporting periods. Monetary equality uses `Decimal` with matching units, not float/string formatting.
- Attachments are not compared. No semantic question equivalence or automatic "nearest issuer" matching is attempted.
- Equal typed values: `same_value_unverified`, **not** an accuracy pass.
- Different typed values with matching supplied context: `value_difference_review`, **not** proof of an error.

Every result has `fill_value: null`; no proposal, fact sheet or PDF is altered. Legitimate changes in signatories, periods, metrics or wording do not authorize reusing old facts. Null period/role metadata is allowed for questions where these do not apply, but is not proof that a hidden context dependency was detected. This manual harness does not assess false-alarm rates or model quality.

## Runnable offline validation

**Ready-to-run synthetic tests**, from the repository root with development dependencies installed:

```bash
.venv/bin/python -m pytest tests/integration/test_history.py -q
```

Tests generate their own synthetic PDFs and request/manifest JSON in temporary roots. They do not read real completed packets or call a model. The tests demonstrate boundaries and result shapes, not an end-user workflow.

**Technical usage template only**—the following requires manually prepared files; it does not create them:

```bash
bd-packet history-check --root . \
  --manifest outputs/archive-partitions.json \
  --comparisons outputs/historical-comparisons.json
```

Use `ArchiveManifest.model_json_schema()` and `HistoryRequest.model_json_schema()` for exact schemas; the [integration fixtures](../tests/integration/test_history.py) demonstrate synthetic payloads. The business reviewer is not expected to maintain JSON.

The command publishes only `outputs/history-check-<run-id>/history-check.json`, with input hashes, per-pair outcomes, and explicit no-grounding/no-replacement flags. It emits no Excel files or packet. Output may contain confidential historical quotations and must stay internal, never merged into the submission packet or ordinary logs.

Inputs, reference/evaluation hashes and supporting versions are rechecked around atomic publication. Technical failures abort and clean staging instead of reporting a completed check. Successful publication can contain exceptions; success is not factual approval. The report covers supplied pairs only, not every archive packet or every current requirement.

## Remaining implementation and evaluation

- Approved model integration for application interpretation and evidence-backed extraction.
- Explicitly permissioned historical retrieval that only exposes reference entries after current proposals exist; derivative lineage and held-out partition checks at every input/cache boundary.
- Semantic question/context mapping and narrative support evaluation, independent of exact quote checks.
- Reviewer revision request contracts tied to packet/base version, permission checks, target clarification, optimistic concurrency, idempotent regeneration and visible diffs.
- Production identity/storage/retention, signing-service choice and eventual Copilot connection.

Measure historical-check usefulness separately: meaningful discrepancies caught, false alarms and incomparable cases with denominators. Add a curated reference subset before broad retrieval; freeze held-out evaluations and validate historical ground truth against independent period-appropriate evidence. No eligible evaluation cases means not applicable, not a pass.

## Automatic visual mapping boundary

The [visual mapping command](../README.md#automatic-visual-mapping-of-blank-pages) now proposes questions, controls, labels and linked write-in/narrative regions from selected blank-page images plus optional native text. It does not use supporting evidence or historical packets, and its local evaluation references never enter the model request. Maps remain separate from `ApplicationRequirements` and answer proposals: valid geometry is not authority to fill an answer.

Digital, image-only, landscape and rotated blank pages can be rendered for this bounded experiment. Coordinates describe the displayed image, not the older unrotated PDF writer. Native-region checks are narrower than visual coverage and are not implemented for rotated pages. Image-only interpretation is not integrated supporting-document OCR or verified factual evidence. Cross-page dependencies, semantic completeness, usable writing space and eventual rendered packet placement still require separate checks.

The evaluated real subset passed after a general boundary-prompt revision with unchanged references/tolerances. Initial failed results and the intervening schema rejection remain part of the observations; do not describe the limited subset or repeated synthetic representations as general accuracy or completion of the end-to-end workflow.
