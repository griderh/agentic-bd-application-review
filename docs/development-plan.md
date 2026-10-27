# Phase 1 development plan

Status: initial implementation roadmap, October 20, 2026.

## 1. Purpose and boundaries

Implement the [approved Phase 1 scope](../Broker-Dealer%20Packet%20Automation%20Phase%201%20Scoping%20Document.md) in independently testable increments. Follow the [repository coding instructions](../.github/copilot-instructions.md). This plan adds an implementation sequence; it does not approve new business capabilities or replace the scope's open decisions.

The immediate development deliverable is a working proof of concept (PoC) running locally against the documents already in this repository. Start with one end-to-end PDF packet, then broaden local coverage and evaluation. Milestones are acceptance-based, not tied to the illustrative POC dates.

### Local PoC data and scope

| Local folder | PoC use |
| --- | --- |
| [Blank issuer forms](../bd_agreements/Blank/) | Application inputs; choose a supported PDF form for the first end-to-end run |
| [Supporting documents](../bd_agreements/supporting_data/) | Read-only evidence and attachments, with explicit source provenance and period selection |
| [Completed packets](../bd_agreements/Completed/) | Explicit reference partition for wording/historical discrepancy checks, separate held-out evaluation partition; never current factual authority or held-out answer input |

Use configurable repository-relative paths, resolved from an explicit repository/data root rather than the caller's working directory. Preserve these inputs unchanged. Write generated packets, reviewer summaries, manifests, and evaluation results to a separate configured, Git-ignored local output location. Maintain dataset partitions so completed holdout packets cannot leak into the answering workflow.

**Not part of initial PoC development:** network-drive mapping, VPN/ExpressRoute, SharePoint/Blob synchronization, production private networking, cloud hosting, Teams/Copilot publishing, production notification delivery, and signing-service integration. Do not implement these or make their design/access decisions prerequisites for the local PoC. Keep a narrow local filesystem boundary so source locations can be changed or an adapter added later without rewriting business rules; do not build speculative network adapters now.

**Agreed PoC architecture:** The Python application runs on the developer's computer, reads documents from the local repository folders, and calls a remotely hosted model through an approved Foundry endpoint. The application sends only the relevant document text or page images needed for interpretation, validates the returned results, and generates the packet and reviewer summary locally. The model does not need direct filesystem access to the repository.

Live interpretation requires endpoint reachability, approved credentials, and appropriate handling of the document content sent to Foundry. This is model API access, not application hosting or network-drive integration. No local model, Foundry-hosted application, or Azure Blob document upload is required for the PoC. Unit and synthetic integration tests remain offline; cloud application hosting and document storage can be considered later.

**Sequencing:** M0-M3 establish the working local PoC; M4 broadens local coverage and evaluation. M5-M6 are a deferred production roadmap, not PoC completion criteria. Begin production/network integration planning and implementation only after the business sponsor has reviewed the working PoC and agreed to proceed.

Implementation has started with the [local foundation increment](decisions/0001-local-foundation.md): Python 3.12 tooling, offline synthetic tests, a deterministic monthly source-selection rule, and a narrow native-field PDF read/write/render demo. This does not complete M0 or the end-to-end PoC: general interpretation and OCR/overlay choices remain open. No Azure application deployment or signing integration has been implemented.

**Bounded sequencing adjustment:** while M2 deterministic packet assembly remains unfinished, the approved next experiment is a [synthetic-only Foundry connection test](../README.md#opt-in-synthetic-foundry-connection-test). The pinned OpenAI SDK and Azure Identity use explicit Azure CLI authentication, versioned repository instructions, strict structured output, one paid request with no retries, and fixed synthetic evidence/expectations. This checks connectivity and six narrow behaviors, not document extraction or packet filling. It sends no business or historical/evaluation documents. Live verification on October 23, 2026 passed 6/6 controlled assertions after assigning resource-scoped Foundry User and using the standard Azure OpenAI hostname with the Cognitive Services token audience (511 total tokens). The originally supplied hostname still rejected Responses access; the README records the tested configuration. This does not complete M1, M2 or M3, change their acceptance criteria, or establish general model-quality performance.

The next approved slice is now implemented as a [synthetic PDF-to-proposals experiment](../README.md#synthetic-pdf-to-proposals-experiment): generated fictional PDFs, native evidence extraction, nine predefined requirements, one bounded model request, strict application proposal validation, existing citation/review checks, and a separate known-answer evaluation. All fill values remain null; no source approval or general semantic-support gate is implied. The initial live case passed 9/9 requirement assertions (2 supported values, 5 exceptions, 2 signing deferrals; 3,956 total tokens). Offline mutation, schema, missing-answer, failure-publication and isolation regressions remain separate from that model result. This extends the same sequencing adjustment without completing packet assembly, automatic requirement discovery, real-document interpretation, archive retrieval or conversational revision.

The user next approved a [real blank-form discovery experiment](../README.md#real-blank-form-requirement-discovery-experiment) using the public Broward questionnaire. The bounded command now discovers native-text requirement candidates without predefined questions, verifies exact quotations/contexts, and publishes unapproved `ApplicationRequirements` plus flagged findings. Supporting/completed documents are never read or sent. Two five-page runs used an independent pre-request 82-anchor local checklist withheld from the model: initial coverage 81/82; revised coverage 82/82, with 71 of 72 findings literally anchored and one ambiguous `Other` blank withheld. The initial report remains unchanged. This is anchor coverage, not semantic/completeness accuracy: a narrative classification and cross-page conditional linking remain unresolved. Quoted relative periods, signer context and eligibility rules are not yet fully structured. Do not wire these candidates directly into answer generation as approved requirements. Deterministic packet assembly remains unfinished; this experiment does not complete M1/M2/M3.

The agreed next M2-facing slice adds explicit single-select/multi-select/narrative contracts, option-linked write-ins, and deterministic inline-versus-supplement planning at a fixed readable font. Visual controls and page regions are separate from answer kinds. A local hash-bound developer mapping covers Broward Q1 (three radios), Q2 (twelve checkboxes, two linked write-ins) and Q11 (narrative region); it checks native labels/bounds and produces annotated renders and fictional narrative previews. This is a limited feasibility mapping, not a new business-maintained template or automatic visual discovery. Native discovery v3 may propose choice metadata but withholds choice findings pending visual/semantic interpretation. Old discovery reports are not rewritten. A synthetic-only proposal run using the new schema passed 12/12 controlled requirement assertions (5,664 total tokens); no new real-document model upload occurred. General visual discovery, complete conditional dependency modeling, eligibility validation, supplement rendering/assembly and final rendered packet verification remain outstanding. The pagination helper resolves references only from an explicitly supplied ordered submission-section map; the example's map is hypothetical, not a completed packet.

The first M1 slice now adds a read-only supporting-document metadata inventory, source hashes/identities, PDF page counts, duplicate-content flags, monthly FOCUS and annual audited-financial filename selection, and version/page reference checks. The [README](../README.md#local-supporting-document-inventory) documents the runnable command and limits. This is a metadata snapshot, not an immutable source archive or approved fact sheet. Content-period verification, staleness policy, external/model contracts, fact extraction, consistency checks, and semantic evidence adequacy remain outstanding; M1 is not complete.

A second M1 slice adds bounded native-PDF page text, exact-substring quote resolution, and narrow labeled reporting-date comparison against filename periods. The [evidence command](../README.md#native-pdf-text-and-reporting-date-evidence) writes confidential text only to local Git-ignored outputs. It preserves textless/error pages and does not promote incomplete coverage to verified evidence. The local corpus yielded native text on 124 of 195 PDF pages; all six financial-document period checks remain unverified. This establishes an OCR feasibility dependency, not a reason to infer missing dates or claim M1 complete. Governed facts, general financial extraction, semantic support, and broad date/layout interpretation remain outstanding.

An approved [local Tesseract experiment](../README.md#opt-in-local-ocr-feasibility) now renders and recognizes one explicitly selected supporting PDF page. Tesseract is an optional system dependency; OCR output remains separate and unverified, with source/page provenance, rendered-pixel word boxes, engine confidence, and explicit limits/failures. One clean synthetic scanned page recovered 6/6 target strings; a local FOCUS page produced text but has no annotated accuracy result. Automatic fallback, OCR quote validation, financial/table accuracy, rotation/handwriting coverage, and integration into period/answer checks remain outstanding. This is a feasibility candidate, not the final production OCR decision or completion of M0/M1.

### Approved next increment: automatic visual mapping (October 26, 2026)

Build a bounded local multimodal blank-form mapping workflow, not another hand-coded issuer template. Render selected pages, supply their images and optional native text to the existing authorized model endpoint, and collect typed proposed questions, option groups, controls, linked write-ins and writable regions. Keep native-only discovery unchanged. All maps remain unapproved; no answer generation, source approval, signatures or packet assembly is enabled by a map.

Use displayed-page normalized coordinates (top-left origin, 0-1000), recording actual rendered dimensions, page dimensions and rotation. Convert to displayed PDF points explicitly for evaluation; do not hand rotated mappings to the existing unrotated writer. Native text is an optional verification signal, not a prerequisite for image-only pages. Missing anchors, unreadable pages and uncertain relationships must be visible review exceptions. Never treat a model's confidence or self-assessment as verification.

Before live calls, fix evaluation tolerances: maximum per-edge error 6 PDF points for control rectangles, 12 points for labels, and 8 points for writable regions. Match questions by independently supplied identifying text, assess kinds and option labels/relationships separately, count extra/missing items and controls, and require one-to-one matches. References stay local, version-bound and out of model inputs. Synthetic fixtures cover columns, distinct Other write-ins, digital/image-only PDFs, landscape and rotation. Evaluate authorized real blank pages against an independent subset reference and report subset denominators rather than claiming whole-form accuracy. Keep requests bounded (at most five selected pages, one request per page, no retries), preserve original inputs, and publish reports plus annotated images atomically in a unique ignored output directory. Failed evaluations remain failures; no loosening tolerances after seeing results.

**Implemented bounded slice:** `map-visual` now renders and submits selected blank pages to the existing model endpoint, uses a strict visual proposal schema, checks native anchors where available, and publishes versioned JSON plus original/annotated images atomically. No issuer coordinates/templates are imported by the application workflow; references are optional, local-only evaluation inputs. Native-only discovery remains unchanged. Image-only pages and displayed rotation are supported for proposals, not for approved PDF writing or supporting-document grounding. Missing/poor anchors, model uncertainty, unreadability and regions too short for a readable line are explicit flags.

**Evaluation observed October 26:** v1 passed the controlled four-variant synthetic case, but the two-page real blank subset failed: 15/15 controls, 14/15 label regions, 2/2 write-ins, 0/1 narrative region. General boundary instructions were clarified in v2; references and tolerances were not changed. One v2 invocation failed strict schema validation and published no map; it was deliberately rerun, not automatically retried. The published v2 real subset passed 3/3 question kinds, 15/15 controls and label regions, 2/2 write-ins and 1/1 narrative region (9,434 tokens). The v2 synthetic run passed 12/12 question kinds, 28/28 controls and label regions, 8/8 write-ins and 4/4 narrative regions across digital portrait, digital landscape, image-only portrait and image-only 90-degree rotation (13,427 tokens). Those 12 synthetic questions are three question designs repeated in four representations, not twelve independent semantic cases. The real subset is Q1/Q2/Q11 on pages 2/4; nine other proposed items and the other pages are not scored. Preserve failed and successful reports separately. These results do not complete automatic full-form verification, eligibility/semantic approval, supporting-document OCR integration, M2 packet assembly or M3 end-to-end completion.

### Approved next increment: requirement-driven evidence retrieval (October 26, 2026)

The agreed direction is to route the current application's needs to a small catalog of designated source families, not extract all files on a network drive. Catalog entries describe likely contents, configured folder, conservative version rule and initial page hints; they do not contain business facts or confer source approval. Automatic routing sees only catalog metadata and supplied requirements, then code validates every requirement/family identity before reading selected families. A document can be read, attached, or both. Missing sources, ambiguous current versions and unsuitable periods remain explicit exceptions.

Implement a local bounded slice first: at most four routed families, 30 inventoried sources, eight read pages, initial page hints and expansion to at most four pages per source/need when terms are not found. Reuse existing filename period selection and OCR boundaries. Native citations are rechecked; OCR remains separately labeled and cannot become native verified evidence. A prior internal report can cache unapproved native proposals only for unchanged requirements, catalog, plan, sources, extracted page text, schema, prompt and model configuration. Reuse is not business approval and does not eliminate source fingerprint/page rechecking. Real supporting documents must not be uploaded without explicit content authorization. Network-drive adapters, whole-drive indexing, universal scanned evidence approval, answer release and packet assembly remain outside this increment.

**Implemented bounded slice:** `retrieve` accepts typed requirements and optional catalog/manual plan, automatically routes by family when paid calls are explicitly enabled, selects versions in code and reads only bounded candidate pages. It separates attachment inspection from native answer context, validates requirement-specific inspected source/page citations, rejects multi-period collapse and requires observed financial ending dates when requested. Source/page/context-bound reuse is an **unapproved proposal cache**, not an approved cross-form fact sheet. Sparse/image-dominant pages can use opt-in local OCR; OCR output remains excluded from native answer proposals. Ambiguous versions, source/JSON/cache mutations and budget/period failures are explicit; no source documents are changed. Existing full-inventory and OCR commands retain their defaults.

**Verification observed October 26:** final synthetic routing/answer case passed 10/10 declared checks over six requirements, with exact source-family/quotation checks for supported values, missing-information abstention, unsuitable-period withholding, separate attachment candidate and signature exception. It read eight of 33 available fictional pages; the unrelated family was absent from retrieval results. Offline boundary tests additionally prohibit scanning the whole supporting root or unrelated family. The final two model requests used 3,576 input + 1,027 output = 4,603 tokens; unchanged-context native proposal reuse created no further model client. This is one controlled semantic case, not a general grounding rate. The deterministic suite passed 584 tests with local OCR enabled, including portrait, landscape and displayed 90-degree scan variants; aggregate coverage was 93%. Ruff lint/format, strict mypy (21 source files), dependency consistency, diff checks and changed production/example Pylance diagnostics passed. No real supporting documents were uploaded. See the [reproducible example and limitations](../README.md#requirement-driven-evidence-retrieval).

### Approved next increment: controlled draft completion (October 26, 2026)

Connect the existing typed requirements, evidence proposals and reviewed mappings to deterministic PDF writing for a representative subset of one public blank. Begin with fictional evidence, independently inspect actual renders, then require explicit supporting-content authorization and human evidence/placement review before a real-fact trial. Do not introduce unrestricted model writing, human-maintained fact sheets or a production approval claim.

**Implemented bounded slice:** `draft` validates a strict request and separate exact-request-hash review record. Writing requires explicit support/source/placement confirmations, valid current native quotations and attached evidence; omitted/withheld decisions leave answers blank. Signing requirements cannot be mapped or approved for writing. The writer supports text/identifiers, radio/checkbox groups and linked write-ins, readable inline narratives, complete multi-page supplemental answers, explicit attachment order and actual final evidence/supplement references. It publishes an incomplete draft, detailed JSON, separate internal text report and before/after form renders atomically after freshness/render checks. It never changes the original or marks the packet complete.

The general writer imports no issuer-specific templates. A separate reusable example uses the existing developer-mapped public-blank subset, adds scalar placements, generates fictional supporting PDFs and supplies a clearly fictional review fixture. This is a deterministic writing/assembly evaluation, not an automated discovery-to-business-approval workflow or model quality test. Render inspection exposed insufficient spacing after an `Other` label in the earlier example mapping; its write-in start was moved ten points right, and the writer now rejects text regions overlapping existing issuer text.

The existing ReportLab 5.0.1 pin moves from development-only to runtime because overlays/supplements are now application operations. Application schemas and function boundaries remain strictly typed; untyped third-party ReportLab imports use an explicit mypy override as PDFium already does. Fresh-environment installation and dependency consistency must be revalidated after the manifest change.

**Remaining boundaries:** local review JSON is trusted technical input, not authentication/production source authorization. No automatic semantic release, OCR-backed answer release, general scanned/rotated blank writing, money/date/table rendering, full-form completeness assurance, signer-specific copies, archive comparison, reviewer chat, notification, signing or submission is added. Existing model/retrieval proposals stay unfillable without this separate reviewed-draft handoff. This partially implements M2; it does not complete M2/M3 or change their acceptance criteria.

**Verification observed October 26:** 613 deterministic tests passed with opt-in local OCR, including 29 draft-specific cases; aggregate coverage was 93%. Ruff lint/format, strict mypy over 22 source files and changed production/example Pylance diagnostics passed. Pinned requirements and editable installation succeeded in a fresh venv; all 29 draft tests passed there and `pip check` found no conflicts. Actual public-blank fictional drafts wrote five answers across eight declared requirements; the missing DTC number, signature and signing date stayed blank, and undeclared form content remained unresolved. The inline packet has five form pages plus one evidence page (reference page 6). The overflow packet has five form pages, two full supplemental pages and two evidence pages (references pages 8/9). Both form-render checks reported zero changed pixels outside actual writable regions at the fixed tolerance; supplemental body text was checked and pages rendered for inspection. Reviewer reports were separate, and originals unchanged. No model calls or real supporting-document reads/uploads occurred in this demonstration; semantic/model accuracy is not applicable, not a pass.

## 2. Engineering decisions and remaining choices

### Latest direction: evidence-first extraction and conversational revisions

This decision supersedes the workbook-maintenance and separate fact-sheet approval proposals recorded below. The user wants minimal human involvement: extract application-needed facts from approved independent supporting documents, validate current proposals, and ask humans only about exceptions plus final packet review/signing. Do not require a human to populate identity or financial facts in a parallel workbook. An Excel view is optional inspection/export; machine-readable snapshots, evidence and correction history belong in a separate internal JSON archive, without generating new Excel files per run.

Add the scoped reviewer-revision capability (FR19): target a packet/base version and answer, clarify ambiguity, distinguish supported factual edits from wording changes and reviewer-only assertions, revalidate/regenerate affected outputs, preserve prior versions, and return a change summary. No separate auditor, automatic source mutation, global fact updates from packet-specific edits, signing or issuer delivery is introduced. Foundry/Microsoft 365 Copilot is an eventual conversation/deployment candidate, not an offline development prerequisite.

**Implemented in this increment:** strict `ArchiveManifest` / `HistoryRequest` contracts, an explicit Completed-PDF reference/evaluation allowlist, hash/version and native quote checks, conservative context/value comparisons, and a developer-only `history-check` JSON report. The reference reader never extracts evaluation text; identical PDF bytes cannot cross declared partitions or enter current supporting evidence during this check. Only supplied pairs are checked; differences flag review and never replace a current answer. The existing support inventory still supplies current evidence independently.

**Not implemented:** automated historical retrieval/question mapping, approved fact release, narrative support evaluation, chat correction/packet regeneration, derivative-lineage enforcement or production authorization. Targeted native-text proposals are implemented, but are not approved facts. Manual partition assignment must be trusted and access-controlled; exact hashes do not detect reformatted copies or answer-bearing derivatives. Existing workbook intake commands remain earlier prototypes, not target prerequisites. See the [current workflow and precise limits](evidence-review-workflow.md). M1 and the end-to-end PoC remain incomplete.

### Earlier implementation decisions (retained history)

The first [governed fact-sheet draft increment](fact-sheet-workflow.md) now defines strict identity/signer-role records, owner and review/effectiveness metadata, exact native evidence citations, and draft version labels/hashes. A local validator reports missing/invalid evidence, date exceptions, annual-review scheduling violations, and overlapping/conflicting records without selecting a winner or making facts fillable. A self-contained synthetic demo creates its own inputs. This is not authenticated approval, immutable release/version history, or a released-fact reader; those controls still require a named business steward/approver, permissions, and implementation. Financial facts/disclosures, automated updates, signer resolution and model integration remain outside this increment. M1 remains incomplete.

The agreed business-facing deliverable for this increment is now an **editable Excel workbook**, not a manually maintained JSON file. The demo creates Excel inputs and outputs; the validator imports human-entered values/evidence and publishes a workbook with dated checks, plus internal JSON diagnostics. Business users supply supporting paths/pages/quotes, not hashes or character offsets. Excel editing and successful validation do not grant approval. Controlled approval/release remains deferred.

**Subsequent ownership decision:** the business owner maintains and checks the fact sheet without a separate auditor or second-person fact-sheet approval. This supersedes the distinct steward/reviewer/approver workflow proposed above for fact-sheet maintenance. The owner may also be the recorded reviewer. Business maintainers only edit/check/save Excel; a technical operator runs the local validation commands until automatic application intake exists. Future intake must authorize the designated workbook through controlled access and record the exact version/record/value used in answers. Plausible source-data typos may pass validation and remain the owner's responsibility; conflicting evidence still produces exceptions. Packet signatory review is unchanged. Current drafts remain unfillable until the missing technical intake/grounding controls are implemented.

**Implemented local workflow correction:** `poc-init` creates one blank `outputs/maintained/fact-sheet.xlsx` without overwriting an existing workbook. `poc --root .` always reads that file and validates during intake; operators no longer choose a source or run a separate validator. The owner keeps editing the same file. Exact input snapshots, internal diagnostics and a readable HTML report are published separately per run; no competing maintained workbook is generated. Synthetic generation and the legacy workbook round-trip command are developer-only tools. This brings the single-workbook interaction forward from the production roadmap; production permissions/retention, GUI launch, packet generation and answer-level provenance remain outstanding.

The [local review harness](../README.md#local-requirementproposal-review) now exercises the contracts with a selected blank PDF and manually prepared requirements/proposals. It verifies application hash/page bounds, resolves native citations, reports every supplied requirement (including missing proposals), and publishes a separate internal diagnostic JSON with no fillable answers. Supplied-question coverage is not full-form detection, and this is not the scoped reviewer-summary PDF. Application interpretation and approved-answer generation remain future increments; there are no new model calls or OCR changes.

The offline [application-requirement and answer-proposal contracts](../README.md#application-requirements-and-answer-proposals) are now implemented using strict, versioned Pydantic schemas. They preserve issuer instructions/locations, requested periods, typed values/units, exact native-text citations, explicit unanswered outcomes, and signing prohibitions. A proposal checker resolves citations but always leaves values unfillable pending semantic support, source approval, and application validation; a model's reporting-period claim cannot verify a period. This does not implement application interpretation, governed facts, answer approval, or end-to-end filling. Foundry vision comparison remains deferred until the first approved endpoint integration; OCR remains separate and experimental.

There is no single universal agentic Python stack. The baseline is TDD, strong contracts, a deterministic core, constrained model interactions, and measured evaluations.

| Area | Baseline or decision |
| --- | --- |
| Language | Python 3.12, initially validated with 3.12.13 and the selected native-PDF tools. Recheck compatibility when the Foundry SDK/framework, OCR approach, and production runtime are selected |
| Dependency management | Standard-library `venv` plus pip. Commit version-pinned `requirements.txt` and `requirements-dev.txt`, including transitive dependencies; development requirements include runtime requirements. Use `pyproject.toml` for package metadata and tool configuration; no uv or separate lockfile tooling |
| Quality tooling | pytest; Ruff for lint, imports, and format; strict mypy for application code; branch coverage reporting for deterministic rules |
| Data contracts | Dataclasses for internal domain values; Pydantic for external inputs/configuration and model/tool responses; Protocol-based provider boundaries |
| Orchestration | Explicit bounded workflow, one packet per run, deterministic state transitions; no multi-agent architecture unless an evidenced requirement justifies it |
| Model integration | Foundry-backed adapter isolated from domain logic. Compare a thin supported SDK integration and Microsoft Agent Framework in M0; document compatibility, maintenance, preview risk, and the reason for the choice |
| Model deployment | Configuration, not a hardcoded model name. Benchmark candidates on the model-selection set; reserve the final holdout for evaluation |
| PDF/layout/OCR | Native-field feasibility uses pypdf and pypdfium2/PDFium, with Pillow for image handling; ReportLab creates synthetic test fixtures only. Opt-in local Tesseract 5.x supports single-page OCR feasibility; integrated accuracy/layout validation, flattened overlays, and production compatibility remain open |
| First entry point | Local command using the repository's blank forms and supporting documents through configurable input/source/output paths; no network drive or chat interface required |
| Production (deferred) | Foundry plus deterministic compute tools as scoped; compute host, network-drive/source-access pattern, private networking, and Teams/Copilot integration are later decisions after the working PoC is reviewed |
| Electronic signing | Human electronic signing after review. DocuSign availability, issuer acceptance, and an approved alternative remain open; no automated signing integration assumed |

Do not install frameworks or provision services just to write this plan. At implementation time, record material decisions in short architecture decision records under `docs/decisions/`, with context, alternatives, consequences, and verified compatibility.

### Input-format discovery

The repository currently contains blank PDF forms and legacy `.doc` issuer forms, plus supporting PDFs, images, and a `.docx` letterhead. Inventory formats before selecting the first issuer. Do not silently add Word-form automation to Phase 1: obtain approved PDF originals or agree a controlled conversion approach with the business owner, preserving issuer layout and validating the converted output.

Existing business documents may be confidential. Do not use them as ordinary CI fixtures or transmit them to external services without approved access. File availability is not evidence that an issuer family is suitable for a final holdout.

## 3. Proposed implementation boundaries

Create modules as functionality requires them, not empty scaffolding for its own sake:

| Boundary | Responsibility |
| --- | --- |
| Domain | Packet/page/field models, evidence references, document requirements, exceptions, signer requirements, explicit run status |
| Source services | Approved source inventory, immutable per-run references, fact-sheet validation, requested-period/latest-applicable selection |
| Interpretation adapter | Page/field/checklist interpretation and evidence-backed answer proposals through validated model/tool contracts |
| Validation | Exact-value checks, evidence resolution, consistency rules, unmet requirements, unsupported-answer rejection |
| PDF services | Native fields and flattened overlays, signer-specific copies, rendering checks, attachments, bookmarks, and page index |
| Workflow | Bounded stages, state persistence, retry policy, run isolation, cancellation, and explicit partial/failure states |
| Output services | Packet, internal reviewer summary, manifest/archive, and safe publication |
| Integration adapters | Local files first; approved storage, model, and internal notification providers later |

Proposed layout: `src/bd_packet_builder/`, `tests/unit/`, `tests/integration/`, `tests/fixtures/` for synthetic/sanitized fixtures only, and `evals/` for evaluation definitions and synthetic examples. Real-document PoC runs use the existing repository data folders above, without copying them into ordinary fixtures. Keep new confidential evaluation annotations and generated results in configured Git-ignored local locations, not new tracked files.

Contracts should include source IDs/hashes and periods; field/page locations and risk classification; proposed answer with evidence; explicit unsupported/conflict/mismatch outcomes; required signer roles; and run manifest/status. Keep non-applicable, unknown, false, zero, and technical failure distinct.

## 4. Milestones and acceptance criteria

### M0 - Foundation and feasibility

Dependencies: none for synthetic work. Real-document experiments require approved access to their data and model endpoints.

Deliverables:

- Select the Python minor version, SDK/framework approach, and PDF/layout/OCR approach using the compatibility and feasibility checks above. Document decisions rather than selecting by popularity alone.
- Add the Python package, venv/pip setup, pinned runtime/development requirements files, pytest, Ruff, strict mypy configuration, coverage reporting, and a minimal CI workflow using synthetic inputs only. Document exact setup/test commands in the README. Capture dependencies from a clean project venv, not an unrelated environment; review updates and validate fresh installs.
- Apply the first red-green-refactor cycle to an observable domain rule, such as unresolved source selection, rather than creating placeholder tests that assert nothing.
- Inventory the existing local forms, support-document naming, and independent evidence. Choose one readable PDF issuer family for development and designate other families for model selection/final evaluation. Missing network locations or folder-owner assignments do not block this inventory.
- Make local output/evaluation locations configurable and Git-ignored before generating artifacts. Leave existing tracked business documents untouched.

Acceptance:

- A clean environment can reproduce dependency installation and execute tests, lint/format, and type checks with the same documented commands as CI.
- The rule has an observed intended failing test followed by a passing implementation.
- A representative blank form can be read, written, and re-rendered without modifying its original or obscuring issuer content. A confidential OCR/model call is not needed for offline CI.
- Input-format gaps and any licensing or preview-runtime risks are documented; unavailable samples do not stop unrelated foundation work.

### M1 - Evidence inventory and deterministic rules

Dependencies: M0.

Requirements: FR1, FR4, FR7, FR10, FR11, FR15, FR16, FR18.

Deliverables:

- Define validated domain/tool schemas and an application-derived fact register with source/version/page and reporting context. Do not require humans to maintain duplicate identity/financial data or per-fact owner/reviewer metadata.
- Implement read-only source inventory and per-run source manifests, filename/period parsing, explicit requested-period matching, latest-applicable selection, and unresolved tie/unparseable outcomes.
- Make staleness thresholds configurable; pending sponsor approval, represent scoped defaults explicitly rather than silently treating them as approved policy.
- Implement evidence lookup, exact-value and cross-field consistency checks, and review-exception records. Keep prior packets separate from authoritative current evidence.
- Enforce configured source/output boundaries, including traversal and symlink checks, and make restricted-tier access unavailable through tools.
- Partition historical packets explicitly into permitted reference and held-out evaluation collections. Enforce reference access and duplicate-hash exclusions; keep derivatives/annotations out of model inputs via controlled dataset lineage. Start with a curated subset; unknown/unlisted content is not automatically reference material.

Acceptance:

- Parameterized tests cover competing periods, explicit unavailable as-of dates, stale sources, ties, missing files, malformed names, conflicting facts, invalid schemas, and disallowed paths.
- Missing evidence produces a blank/flagged outcome; relevant nonmatching evidence can be identified without claiming the requirement is met.
- All filled-value candidates have resolvable provenance; a fabricated source ID or unrelated citation is not accepted as grounding. Semantic evidence adequacy still requires evaluation in M3/M4.
- Historical discrepancies are review flags, not current factual authority or ground truth. Unknown/mismatched issuer/question/period/signer contexts are incomparable; identical answers are not an accuracy pass. Test evaluation text exclusion and duplicate-content leakage independently of model quality.

### M2 - Deterministic local packet assembly

Dependencies: M1. Use synthetic or independently annotated field/answer mappings before adding model interpretation.

Requirements: FR5, FR6, FR7, FR8, FR9, FR12, FR14, FR15, FR17, FR18.

Deliverables:

- Fill native fields and flattened overlays on original PDFs; handle text wrapping, checkbox marks, tables, rotations, and page-coordinate transforms.
- Produce required signer-specific copies, leave signatures and mandatory dates blank, append available attachments in checklist order, and generate bookmarks/page index after final page ordering.
- Produce the separate internal summary with evidence register, signer/date locator, changes against a configured prior packet, and prominent exceptions.
- Publish packet, summary, run manifest, and local archive as consistent per-run outputs. Model quality is not being claimed at this milestone.

Acceptance:

- PDF integration tests verify actual rendered output and field contents, not only mocked writer calls. Use synthetic visual baselines with documented tolerances and human inspection of representative approved samples.
- Test no clipped/overlapping answers, correct checkbox state, retained issuer content, final signature page references, correct attachment order, and blank signatures/dates.
- Test missing/unreadable pages, unresolved signer roles, stale/mismatched evidence, source changes during a run, and interrupted writes.
- Originals remain unchanged; the internal summary is never merged into the submission packet. Incomplete outputs are visibly identified, and failed publication never appears successful.

### M3 - Working local PoC: first grounded end-to-end agent workflow

Dependencies: M2; a configured approved Foundry endpoint and source set for live model experiments. Offline contract tests remain available without them.

Requirements: FR1-FR12, FR15-FR19.

Deliverables:

- Add the selected model adapter for page classification, field/checklist interpretation, and answer proposals with evidence references.
- Build the local end-to-end command: intake, source snapshot, interpretation, validation, filling, consistency/render checks, assembly, summary, archive, and explicit final status.
- Bound calls, tokens, elapsed time, and retries; validate outputs before deterministic tools run. Record model/prompt/schema versions in the run manifest.
- Treat legitimate issuer requirements as task data, while rejecting embedded attempts to override permissions or direct unrelated actions.
- After current evidence-backed proposals exist, add bounded reference-only historical comparison; never use prior packets to fill missing current facts.
- Add a bounded reviewer-revision operation against a packet/base version and answer IDs, before a hosted chat surface. Preserve evidence, distinguish reviewer assertions, revalidate/render affected outputs, keep unrelated answers unchanged, and return a versioned change summary. JSON records retain provenance without generating spreadsheet copies.

Acceptance:

- Demonstrate one issuer packet using a blank PDF from the repository and evidence/attachments from its local supporting-document folders, producing a grounded packet and separate summary in the configured local output location. Known unsupported fields remain blank, while supported attestations/disclosures are prepared for human confirmation.
- Contract tests cover invalid/truncated model output, nonexistent evidence, tool failures, rate limits, timeouts, cancellation, and exhausted budgets. Do not disguise any as unsupported business facts.
- Adversarial tests confirm document text cannot expand source access, choose external recipients, apply signatures, or invoke external submission.
- Human evidence review verifies the first live run's answers and rendered placement. Confidence or a second model's approval is not accepted as proof of correctness.
- A reviewer can repeat the PoC using documented local setup, data-path configuration, and execution commands, without any mapped network drive, storage synchronization, deployed application host, or production notification service. Local output paths and status provide the review handoff.
- Present the working PoC and its known gaps to the business sponsor before starting the deferred production/network integration work. M4 can continue locally without that integration.
- Test correct revision targets, missing/ambiguous references, unsupported factual requests, stale base versions, repeated/idempotent requests, failed publication recovery, and unchanged signatures/date prohibitions. Human-only assertions cannot become document-supported answers.

### M4 - Broader coverage and repeatable evaluation

Dependencies: M3 for live evaluation. Dataset curation and scorer tests can begin in parallel with M1/M2.

Requirements: FR2-FR12, FR16-FR18; scope Section 13.

Deliverables:

- Add representative issuer families, including signer-specific forms, scanned/flattened pages, and native fillable forms. Cover the scope's three-or-more-issuer layout tests without consuming the reserved final holdout.
- Collect the scoped additional packets and approved evidence; have humans validate field inventories, periods, expected answers, exceptions, and risk labels.
- Separate development, model-selection, and frozen final test partitions by issuer/template family; exclude held-out answers and derivatives from all answering inputs.
- Build deterministic scorer tests and a repeatable evaluation runner. Record dataset/split, source, prompt/model, schema/code versions, raw counts, denominators, and costs.

Acceptance:

- Report answer accuracy, high-risk accuracy, auto-fill/correct coverage, abstention precision/recall, exception reporting, attachment correctness, period selection, and signing preparation separately.
- Use the scope's proposed targets, subject to business-owner approval: zero unsupported answers; at least 95% answer accuracy and 85% auto-fill coverage; 100% high-risk answer accuracy and the specified exception/control measures. Abstention precision remains a reported metric with its target open.
- Required missing-source/unreadable/unresolved-signer test cases are present. Test scorers against hand-computed results and zero-denominator cases; never substitute abstention hits for answer accuracy.
- Run repeated live cases where necessary to expose nondeterminism. Retain failures; do not tune against final holdout answers. A new optimization cycle requires a refreshed independent final test set.
- Present pilot-size limitations, unresolved gaps, runtime/cost, and reviewer-time baseline. Do not claim universal zero hallucinations from a finite test set.

### M5 - Deferred production integrations and operational hardening

**Evidence/review production handoff requirement (supersedes maintained-workbook handoff):** configure access-controlled supporting evidence and separate reference/evaluation archives, plus internal JSON run/correction storage. Human-maintained Excel is not required; any Excel view is optional inspection/export, not a new workbook on every run. Enforce reviewer authorization, packet/base-version targeting, bounded evidence-backed revisions and visible change summaries through the eventual conversation surface. Keep issuer packets separate from confidential diagnostics and snapshots. Exclude synthetic artifacts and held-out answers/derivatives from production reference access. Review obsolete demo artifacts deliberately under retention policy rather than automatically deleting business records. Verify input identity, reference partitions, recovery/concurrency and reviewer-facing entry points before handover.

Dependencies: sponsor review of the working local PoC and agreement to proceed, plus the relevant M4 regression suite for each integration and IT-approved infrastructure/access. Network-drive mapping and network/sync design belong here, not in M0-M4; they are not prerequisites for demonstrating the PoC.

Requirements: FR1, FR13-FR15 and all runtime controls.

Deliverables:

- Connect designated folders using the approved network/sync pattern. Preserve source snapshot semantics, identity boundaries, and deterministic selection across adapters.
- Deploy the bounded workflow and deterministic tools using the agreed Foundry/compute approach; persist asynchronous run state and support safe resume/retry.
- Add internal notification to maintained verified recipients, falling back to the business owner/requester for unresolved signer roles. Surface notification failure separately from packet-generation status.
- Implement protected archive/audit handling, safe structured telemetry, retention configuration, and operator recovery procedures. Confirm retention requirements before production retention is configured.
- Add the approved Teams/Copilot front door after the core workflow works; request publishing approval early. Add local debug configuration appropriate to the chosen framework once runnable code exists.

Acceptance:

- Integration tests demonstrate read-only source access, allowed output destinations, restricted-tier denial, internal-only recipients, no signing/submission tools, and confidential-content exclusion from ordinary logs/traces.
- Test retries without duplicate notifications, job isolation, concurrent runs, process restarts, source-sync lag, permission failures, and archive/storage failures.
- A partial or failed technical run has an explicit status and recovery path; it is never reported as a complete packet. Business exceptions still allow supported work to reach human review.
- Approved cloud smoke tests run only with explicit credentials/configuration, separate from offline CI. IT validates networking, deployment rollback, operational ownership, and access policy.

### M6 - Deferred production parallel run and handover

Dependencies: M4 evaluation evidence, M5 operational readiness, and business-owner acceptance.

Requirements: all FR1-FR18 and scope review/go-live controls.

Deliverables and acceptance:

- Run incoming packets alongside the existing employee process; record reviewer corrections, unresolved requirements, review time, and operational failures.
- Turn corrections into governed rules or development regression cases, not unapproved automatic learning or contaminated holdout data.
- Have the business owner approve evaluation thresholds/results and supported issuer coverage, folder owners accept source maintenance, and an operator accept recovery/support ownership.
- Confirm a paperless signing method and issuer acceptance before operational handover. The builder still leaves signatures/dates blank and never submits externally.
- Document the manual fallback, outstanding exceptions, retention configuration, and go/no-go decision. No automatic go-live based only on green unit tests.

## 5. TDD and validation workflow

For each behavior:

1. Identify its requirement and observable acceptance case.
2. Add a synthetic or sanitized failing test and observe the intended failure.
3. Implement the smallest complete behavior through the domain/provider boundary.
4. Run the focused test, refactor, and run related unit/integration tests plus lint/format/type checks.
5. For prompt/model/retrieval changes, run the relevant versioned model-selection evaluation separately. Use frozen holdout evaluation only at the agreed acceptance checkpoint.
6. Update usage/contracts and report actual commands, results, and limitations.

Keep PR checks offline and reproducible. Schedule or explicitly trigger paid/live evaluations against approved data; do not expose confidential inputs/results as ordinary GitHub Actions artifacts. Measure branch coverage to find gaps, but do not equate an arbitrary coverage percentage with correctness. All critical rules need explicit positive and negative assertions.

Documentation-only changes require link/content and whitespace review, not an application test run. Exact executable setup, validation, and native-PDF demo commands are documented in the [README](../README.md); later milestone commands must not be implied to exist before implementation.

## 6. Decisions and business inputs to close

| Decision/input | Owner | Needed for |
| --- | --- | --- |
| Python/runtime, dependency licenses, PDF/OCR, SDK/framework | Technical sponsor with IT | M0 foundation and compatibility |
| First PDF issuer and treatment of legacy Word forms | Business owner and technical sponsor | M0 feasibility and supported input formats |
| Local fact-sheet content, available supporting records, naming, period/staleness approval | Business owner and technical sponsor | M1 local-source validation; use existing repository folders and flag evidence gaps without waiting for network paths |
| Independent blank originals and additional labeled packets | Business owner and technical sponsor | Start with existing local samples; collect additional packets for M4 evaluation, not as a gate to the first working PoC |
| Approved model endpoint, credentials, region, and model data handling | IT and technical sponsor | M3 live model experiments; distinct from network-drive mapping or production hosting |
| Network-drive paths/owners, network or sync access, production storage/compute and private networking | IT, folder owners, and technical sponsor | Deferred M5 work only after sponsor review of the working PoC |
| Recipient role/name mapping and notification channel | Business owner, Compliance, IT | M5 delivery; known-recipient fallback tested locally first |
| Confidential-input handling and draft/log/archive retention | Compliance and IT | Appropriate data handling and production retention, not exclusion of required sources or a classification gate to development |
| Accuracy/coverage/abstention targets and supported coverage | Business owner | M4 acceptance and M6 go-live |
| Electronic signing service or alternative and issuer acceptance | Business owner, IT, Compliance | M6 paperless handover; not builder development |

## 7. Engineering references

These support the baseline; they do not establish one mandatory universal agent framework:

- [pytest integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- [Ruff linting and formatting](https://docs.astral.sh/ruff/)
- [mypy type-checking guidance](https://mypy.readthedocs.io/en/stable/existing_code.html)
- [Pydantic validation](https://docs.pydantic.dev/latest/)
- [Python venv environments](https://docs.python.org/3/library/venv.html)
- [pip repeatable installs](https://pip.pypa.io/en/stable/topics/repeatable-installs/)

Consult current official Python and Foundry SDK documentation during M0 before choosing versions or implementing service-specific interfaces.
