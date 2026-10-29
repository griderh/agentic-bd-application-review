# Phase 1 development plan

Status: implementation roadmap, rebaselined October 28, 2026.

**October 29 priority clarification (supersedes hosted-first PoC sequencing below):** the immediate working PoC may execute locally using the authorized developer identity, with external Foundry inference and Azure Blob inputs/results. A deployed agent identity and Copilot publication are future deployment acceptance, not blockers to demonstrating the PoC. The ultimate workstation-independent Foundry/Copilot architecture remains the target. Prioritize a substantial real-document application-run attempt over additional tiny synthetic demonstrations; keep focused offline tests as regression safeguards.

## 1. Purpose and boundaries

Implement the [approved Phase 1 scope](../Broker-Dealer%20Packet%20Automation%20Phase%201%20Scoping%20Document.md) in independently testable increments. Follow the [repository coding instructions](../.github/copilot-instructions.md). This plan adds an implementation sequence; it does not approve new business capabilities or replace the scope's open decisions.

**Product outcome:** build an end-to-end application whose agent orchestration runs in Microsoft Foundry. A requester selects a staged blank issuer document through the intended Microsoft 365 Copilot/Teams front door; direct file/image attachments are not supported on the selected custom-engine path. From that point, the application—not a developer, chat assistant, or manually prepared request—must perform the complete bounded workflow: interpret the form, locate and inspect permitted supporting evidence, propose grounded answers, validate them, write and assemble the packet, and return a packet plus internal reviewer summary with explicit status and exceptions. Every prompt, workflow step, schema, policy, and deterministic tool required at runtime must be versioned in this repository and deployed as part of the application. No answer, field map, citation, review decision, or orchestration step may be supplied just in time by an external coding agent.

The target architecture is a Foundry-hosted agent that orchestrates repository-defined prompts and narrowly scoped deterministic document tools, with Microsoft 365 Copilot/Teams as the user-facing entry point. PDF manipulation, source/version selection, evidence checks, path/access enforcement, consistency validation, and publication remain tested code, not model behavior. The exact Azure compute hosting pattern for these tools and the authorized source-document access pattern must be selected and validated with IT before that integration is built. The scope recommends Azure Functions or Container Apps for tools and identifies approved network access or controlled SharePoint/Blob synchronization as source-access patterns; this plan does not assume either is already configured.

### Terminology and execution environments

- **Local development** means repository code runs on a developer workstation for coding, offline tests, or explicitly authorized live tests. It may call a remote Foundry model API. “Local” does not mean offline or model-free.
- **Local application/PoC** means the application workflow itself runs on the developer workstation. This is useful for component development and testing, but it is not the target deployed application.
- **Foundry-hosted application** means the deployed Foundry agent executes the application workflow and model orchestration in its hosted runtime and invokes its configured deterministic tools. Turning off a developer's workstation must not stop a deployed run.
- **M365 Copilot/Teams front door** means the requester can select a staged blank application and interact with the deployed agent through the approved published experience. Tenant publishing, document selection and authorized result delivery must be verified; they must not be inferred from local tests.

The immediate PoC's defining acceptance is an application-run end-to-end test, not a document completed by a person or by an AI agent outside the repository. Local execution with Foundry inference and Blob storage is acceptable for this milestone. It does not establish hosted operation, Copilot publication or production readiness; these remain separate acceptance gates.

### Development data and scope

| Local folder | PoC use |
| --- | --- |
| [Blank issuer forms](../bd_agreements/Blank/) | Application inputs; choose a supported PDF form for the first end-to-end run |
| [Supporting documents](../bd_agreements/supporting_data/) | Read-only evidence and attachments, with explicit source provenance and period selection |
| [Completed packets](../bd_agreements/Completed/) | Explicit reference partition for wording/historical discrepancy checks, separate held-out evaluation partition; never current factual authority or held-out answer input |

Use repository-relative paths for checked-in development data, resolved from an explicit repository/data root rather than the caller's working directory. Preserve source inputs unchanged. Local developer outputs belong in a separate configured, Git-ignored location. In the deployed application, use configured, access-controlled storage and allowed destinations; never assume the deployed agent can read a developer workstation or repository checkout. Maintain dataset partitions so completed holdout packets cannot leak into answering inputs.

Offline unit and synthetic integration tests remain required. Live model tests require explicit authorization, approved credentials, and appropriate data handling. The technical sponsor authorized staging designated real supporting documents and the selected Broward blank in Blob and sending relevant text/page images to the configured Foundry model on October 29. Completed packets, held-out answers/derivatives and restricted financial-reporting sources remain excluded. Production private networking, business-source connectivity, durable storage, notifications, signing integration, hosted operation and Copilot publication remain separate future gates.

**Sequencing:** M0-M2 establish and test deterministic components; M3 integrates and hosts the complete Foundry-orchestrated application and connects the intended Copilot/Teams entry point; M4 broadens coverage and evaluation; M5 hardens required production integrations and operations; M6 conducts parallel run and handover. M3 is the working PoC acceptance milestone, not a local-only PoC milestone.

Implementation started with the [foundation increment](decisions/0001-local-foundation.md): Python 3.12 tooling, offline synthetic tests, a deterministic monthly source-selection rule, and a narrow native-field PDF read/write/render demo. These were development components, not hosted acceptance. Current integration/deployment status is recorded per slice in the M3 backlog below; Copilot publication, business-source connectivity and signing integration remain unimplemented.

**Status at rebaseline:** the repository has useful local components and separate bounded Foundry API experiments, but M0-M2 acceptance is not fully complete and M3 has not started. There is no repository-defined, deployed workflow that accepts a blank form, autonomously interprets it, processes the approved evidence set, and returns a packet through Foundry/Copilot. The 75-page Broward artifact described below used request/proposal/review inputs prepared manually by an external chat agent; it is an assembly experiment only and does not count toward M3 acceptance. The next implementation objective is M3's integrated hosted vertical slice—not another disconnected local experiment. Follow the [M3 implementation backlog](#m3-implementation-backlog-october-28-2026), starting with slice 1.

**Earlier experiment history—not the current next-step instruction:** while M2 deterministic packet assembly remained unfinished, the approved experiment was a [synthetic-only Foundry connection test](../README.md#opt-in-synthetic-foundry-connection-test). The pinned OpenAI SDK and Azure Identity used explicit Azure CLI authentication, versioned repository instructions, strict structured output, one paid request with no retries, and fixed synthetic evidence/expectations. This checked connectivity and six narrow behaviors, not document extraction or packet filling. It sent no business or historical/evaluation documents. Live verification on October 23, 2026 passed 6/6 controlled assertions after assigning resource-scoped Foundry User and using the standard Azure OpenAI hostname with the Cognitive Services token audience (511 total tokens). The originally supplied hostname still rejected Responses access; the README records the tested configuration. This does not complete M1, M2 or M3, change their acceptance criteria, or establish general model-quality performance.

**Earlier experiment history:** the [synthetic PDF-to-proposals experiment](../README.md#synthetic-pdf-to-proposals-experiment) used generated fictional PDFs, native evidence extraction, nine predefined requirements, one bounded model request, strict application proposal validation, existing citation/review checks, and a separate known-answer evaluation. All fill values remained null; no source approval or general semantic-support gate was implied. The initial live case passed 9/9 requirement assertions (2 supported values, 5 exceptions, 2 signing deferrals; 3,956 total tokens). Offline mutation, schema, missing-answer, failure-publication and isolation regressions remain separate from that model result. This did not complete packet assembly, automatic requirement discovery, real-document interpretation, archive retrieval or conversational revision.

**Earlier experiment history:** the [real blank-form discovery experiment](../README.md#real-blank-form-requirement-discovery-experiment) used the public Broward questionnaire. Its bounded command discovers native-text requirement candidates without predefined questions, verifies exact quotations/contexts, and publishes unapproved `ApplicationRequirements` plus flagged findings. Supporting/completed documents are never read or sent. Two five-page runs used an independent pre-request 82-anchor local checklist withheld from the model: initial coverage 81/82; revised coverage 82/82, with 71 of 72 findings literally anchored and one ambiguous `Other` blank withheld. The initial report remains unchanged. This is anchor coverage, not semantic/completeness accuracy: a narrative classification and cross-page conditional linking remain unresolved. Quoted relative periods, signer context and eligibility rules are not yet fully structured. Do not wire these candidates directly into answer generation as approved requirements. The experiment does not complete M1/M2/M3.

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

**OCR citation gate:** answer proposals and the reviewed draft now support a distinct OCR-citation contract. Each citation binds an inventoried source hash, page, exact OCR-artifact hash, reproducible rendered-page hash, and a contiguous OCR word range/quotation. The writer validates OCR configuration, word/image bounds, reconstructed line text and source rendering. Release of a cited OCR answer additionally requires explicit human confirmation of the report subject, OCR visual match, evidence support, source approval and mapped field placement. `check_proposal` does not automatically approve OCR; OCR remains unverified until the separate draft review. The development review JSON is not authenticated authorization.

The user supplied separate FINRA BrokerCheck PDFs for the firm and Qualified Representative. They are 24 and 11 pages, displayed at 90 degrees, with little or no usable native text. The covers and targeted registration sections were OCR-processed locally and visually inspected. The user confirmed the two report subjects and the representative's Primary Representative/Qualified Representative role for this Broward trial only; this role assignment is not reusable by default. The inspected sections show distinct registration information. The firm report summary also indicates one regulatory event; its detailed event information was not inspected and remains a reviewer exception.

A controlled real-evidence draft now writes only four page-one identity fields and appends the firm and individual reports as separate, ordered attachments. It is 40 pages total (five application pages followed by the 24-page firm report and 11-page individual report). The checklist entry remains unchecked; its FINRA-related attachment appears responsive to the displayed registration information, subject to human review and without a legal/compliance determination. The firm-event disclosure note is in the separate internal reviewer summary; related disclosures/attestations, Sales Associate/Backup details, signatures, dates and all other unattempted fields remain unresolved. No model calls, uploads, approval or submission occurred, and neither source PDF was modified.

Evidence routing is subject-specific: never substitute an individual BrokerCheck for the firm's or vice versa. A checklist is useful when present but is not assumed to be the only source of attachment requirements. Confirm whether the Primary Representative and Qualified Representative/signatory are the same for each packet; a Sales Associate/Backup report is not required by default.

**Remaining boundaries:** local review JSON is trusted technical input, not authentication/production source authorization. The current real-evidence draft is a manually reviewed, four-field slice, not full-form completion; the disclosure-event details and remaining fields still require review. No automatic semantic release, automatic OCR use, general scanned/rotated blank writing, money/date/table rendering, full-form completeness assurance, signer-specific copies, archive comparison, reviewer chat, notification, signing or submission is added. Existing model/retrieval proposals remain unapproved absent the separate reviewed-draft handoff. This partially implements M2; it does not complete M2/M3 or change their acceptance criteria.

**Verification observed October 27:** the full deterministic suite after the reviewer-note change passed 617 tests, with four opt-in tests skipped. The preceding coverage run reported 92%; coverage was not recollected for this small change. Ruff lint/format, strict mypy over 22 source files, changed-file Pylance diagnostics, and diff hygiene passed. The earlier fictional-draft tests still verify five supported answers, blank DTC/signature/date, actual inline and overflow packet pagination, and zero changed form pixels outside writable regions.

The OCR-citation path was also checked against the two newly supplied local FINRA reports: source/version metadata, actual rendered-page fingerprints, four exact cover-page OCR ranges and candidate pixel bounds validated. Only pages 1-2 of each report were inspected. The firm and individual report subjects and CRDs remain unapproved candidates; no real answer was written and no packet assembled. No model calls or uploads occurred. The remaining report pages, broader registration/certification sufficiency, and business field/role approval remain open.

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

**Implemented developer-only fact-sheet prototype:** `poc-init` creates one blank `outputs/maintained/fact-sheet.xlsx` without overwriting an existing workbook. `poc --root .` reads and validates it during intake. This is a separate prototype, not the broker-dealer packet agent, its Copilot interface, or a required runtime workflow. Production permissions/retention, packet generation and answer-level provenance remain outstanding.

The [local review harness](../README.md#local-requirementproposal-review) now exercises the contracts with a selected blank PDF and manually prepared requirements/proposals. It verifies application hash/page bounds, resolves native citations, reports every supplied requirement (including missing proposals), and publishes a separate internal diagnostic JSON with no fillable answers. Supplied-question coverage is not full-form detection, and this is not the scoped reviewer-summary PDF. Application interpretation and approved-answer generation remain future increments; there are no new model calls or OCR changes.

The offline [application-requirement and answer-proposal contracts](../README.md#application-requirements-and-answer-proposals) are now implemented using strict, versioned Pydantic schemas. They preserve issuer instructions/locations, requested periods, typed values/units, exact native-text citations, explicit unanswered outcomes, and signing prohibitions. A proposal checker resolves citations but always leaves values unfillable pending semantic support, source approval, and application validation; a model's reporting-period claim cannot verify a period. This does not implement application interpretation, governed facts, answer approval, or end-to-end filling. Foundry vision comparison remains deferred until the first approved endpoint integration; OCR remains separate and experimental.

There is no single universal agentic Python stack. The baseline is TDD, strong contracts, a deterministic core, constrained model interactions, and measured evaluations.

| Area | Baseline or decision |
| --- | --- |
| Language | Python 3.12, initially validated with 3.12.13 and the selected native-PDF tools. Recheck compatibility when the Foundry SDK/framework, OCR approach, and production runtime are selected |
| Dependency management | Standard-library `venv` plus pip. Commit version-pinned `requirements.txt` and `requirements-dev.txt`, including transitive dependencies; development requirements include runtime requirements. Use `pyproject.toml` for package metadata and tool configuration; no uv or separate lockfile tooling |
| Quality tooling | pytest; Ruff for lint, imports, and format; strict mypy for application code; branch coverage reporting for deterministic rules |
| Data contracts | Dataclasses for internal domain values; Pydantic for external inputs/configuration and model/tool responses; Protocol-based provider boundaries |
| Orchestration | Foundry-hosted agent executes the repository-defined bounded workflow, one packet per run, with deterministic state transitions; no developer-side/external-agent orchestration and no multi-agent architecture unless an evidenced requirement justifies it |
| Model integration | Foundry-backed adapter isolated from domain logic. Compare a thin supported SDK integration and Microsoft Agent Framework in M0; document compatibility, maintenance, preview risk, and the reason for the choice |
| Model deployment | Configuration, not a hardcoded model name. Benchmark candidates on the model-selection set; reserve the final holdout for evaluation |
| PDF/layout/OCR | Native-field feasibility uses pypdf and pypdfium2/PDFium, with Pillow for image handling; ReportLab creates synthetic test fixtures only. Opt-in local Tesseract 5.x supports single-page OCR feasibility; integrated accuracy/layout validation, flattened overlays, and production compatibility remain open |
| PoC entry point | Microsoft 365 Copilot/Teams front door to the Foundry-hosted agent. A local command may remain for developer tests, but it is not the user-facing PoC or proof of end-to-end acceptance |
| Runtime/tool hosting | Foundry-hosted orchestration plus narrowly scoped deterministic Azure compute tools, as recommended by the scope. Select Azure Functions versus Container Apps and verify Foundry-to-tool connectivity before implementation; do not move exact PDF/source rules into prompts |
| Business source access | Read-only access to the approved supporting-document set, including necessary confidential documents, through an IT-approved network or controlled synchronization pattern. Resolve source identity, auth, access and allowed output locations before live hosted packet runs |
| Front door | M365 Copilot/Teams is the intended user interface. Verify tenant publishing approval, PDF upload support, authentication and result-link access; record an external tenant/admin dependency explicitly if publication is blocked |
| Production hardening (later) | Durable storage/archive, production private networking, source synchronization, internal notifications, retention, recovery and operational ownership are M5 work; they do not defer the M3 hosted end-to-end PoC |
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

**Implementation update — full local Broward attempt:** the deterministic writer now accepts hash-bound additional issuer forms and supports up to 100 requirements and 100 packet pages. A manually prepared request and review record produced a 75-page incomplete packet: five questionnaire pages, two Authorization-to-Trade pages, and four evidence attachments (32-page FOCUS, 24-page firm BrokerCheck, 11-page representative BrokerCheck, one-page public-funds overview). Thirteen of 61 declared requirements were written; the checklist marks only the attached FOCUS and FINRA-registration documents. Question 2 was left blank because its supporting overview lists products but does not establish that they are offered regularly. Other unsupported and conditional items remain blank, and signatures/dates remain untouched. The internal summary is separate. Visual render checks reported zero changed pixels outside reviewed writable regions; representative form pages were visually inspected. Sources were not modified, and no model call, external upload, signing or submission occurred.

This is a local assembly attempt, **not completion of M2 acceptance criteria or M3**: the request/review were manually prepared, the form was not completed, signer-specific duplication and the full reviewer workflow are absent, and no end-to-end agent or model grounding was exercised. The final output remains explicitly incomplete and must not be submitted. See the [documented packet attempt](../README.md#full-local-broward-packet-attempt) for the packet order and reviewer exceptions.

### M3 - Foundry-hosted end-to-end PoC with Copilot front door

Dependencies: M0-M2; selected Foundry project/model; approved live-test data handling; an available deployment path for deterministic tools; and an IT-approved source-access method for the PoC evidence set. Identify tenant/admin requirements for M365 Copilot publishing at the start of M3. If publication approval is unavailable, complete and test the hosted Foundry workflow and document that external gate; do not describe an unpublished/local run as Copilot integration.

Requirements: FR1-FR12, FR15-FR19.

Deliverables:

- Put the runtime prompts, model configuration, agent instructions, tool schemas, workflow implementation, and version identifiers in this repository. The Foundry agent—not an external developer assistant—must orchestrate the application steps.
- Implement the user intake through the intended Copilot/Teams experience: receive the blank issuer PDF and permitted run context, create a run identity, and pass only bounded, validated inputs to the workflow.
- Connect the model-driven form interpretation to the existing deterministic discovery/layout, evidence retrieval, proposal validation, and draft/assembly components. The running application must generate its own requirements, mappings, evidence proposals, attachment selections, and reviewer report; no manually prepared request/review JSON, hand-authored per-run answers, field placements, citations, or external-agent analysis may be required.
- Attempt every detected answerable field, including supported attestations and disclosures. Route questions to the designated source families, inspect relevant current documents, and include required available attachments in checklist order. The model proposes answers with source/page/period evidence; application code resolves and validates the citations and exact values before writing. Missing/conflicting evidence, unreadable content, unsuitable periods, or unresolved roles remain explicit exceptions and do not discard supported work.
- Use deterministic code for access control, path confinement, source/version snapshots, period selection, writable-region validation, signatures/date protection, PDF writing/merging, page references, consistency/render checks, safe publication, and explicit run status. The model cannot select arbitrary files/destinations, modify sources, approve its own answer, sign, notify external parties, or submit.
- Deploy the Foundry orchestration and deterministic tools to the selected supported runtime. Use asynchronous run state where needed so long packet jobs are not constrained to one chat-turn duration. Return the packet and separate internal summary/status to the requester through the approved Copilot/Teams experience or its access-controlled result link.
- Bound model/tool calls, tokens/output size, elapsed time and retries; validate all model outputs before deterministic tools execute. Record model, prompt, schema, code and source versions in the run manifest. Treat issuer instructions as task data, never as authority to expand permissions or trigger unrelated actions.
- Retain bounded reviewer revisions against an exact packet/base version and answer IDs only if they fit the first vertical slice; otherwise defer them explicitly without blocking the core upload-to-packet workflow. Any revision must preserve provenance, distinguish reviewer assertions, revalidate/render changed outputs, leave unrelated answers unchanged, and return a versioned change summary.

M3 implementation order:

1. Confirm with IT the Foundry project/model and identity, deterministic tool runtime, permitted evidence set and access mechanism, and Copilot/Teams publishing/upload path. Record choices, blockers and security boundaries in a decision record; do not silently substitute developer-local paths or manual inputs.
2. Define the end-to-end run contract, versioned prompts/schemas, tool contracts, status/error model and per-run provenance manifest in repository code. Add offline contract tests and synthetic integration cases before live calls.
3. Implement the Foundry agent orchestration and connect the repository's existing discovery, retrieval, validation, and writer components through narrowly scoped deterministic tools. Model proposals are untrusted; code retains all access, validation, signing and publication controls.
4. Deploy the application workflow to Foundry and the selected tool runtime. Verify a run can finish when the developer workstation is disconnected.
5. Connect and test the approved Copilot/Teams user journey, including blank-PDF upload, run status, and access to the resulting packet and internal summary. Separate tenant/admin publishing blockers from application defects and keep the acceptance item open until the user journey works.
6. Run the controlled Broward case through that user journey using authorized data. Inspect actual traces, source/page usage, written answers, abstentions, attachments, rendered output and reviewer exceptions; fix gaps in application code/prompts and rerun. Do not repair a run with external-agent reasoning or manually supplied intermediate artifacts.

Acceptance:

- A requester can start a run through the hosted Foundry agent and intended Copilot/Teams front door by providing a blank PDF; the application runs without a developer workstation or a developer/Copilot coding agent.
- From that blank and the approved evidence set, the deployed application automatically interprets the form, searches the configured source set, attempts every answerable field, validates citations, assembles all supported answers and required available attachments, and returns a separate reviewer summary with prominent unresolved items and accurate incomplete/complete status.
- Run a real controlled Broward end-to-end case using repository prompts/code and authorized supporting documents. Demonstrate and retain the actual Foundry/tool traces and run manifest proving that the deployed application made the model calls and executed the tools. Report which documents/pages were read, attached, or neither; per-field answer/abstention results; model/prompt/schema/code versions; and actual usage. Never count assistance supplied by a developer or external chat model as application behavior.
- No request-specific interpretation, requirement list, field map, citation, proposal, review decision or answer is prepared outside the deployed application. Human signatory review remains the final business gate, not a substitute for application processing.
- The packet preserves signatures and mandatory dates blank, contains no unsupported answer, and does not include the internal summary. All required exceptions are visible. A form that is wholly unreadable is preserved unchanged and the output is explicitly incomplete.
- Contract tests cover invalid/truncated model output, nonexistent/unrelated evidence, tool failures, rate limits, timeouts, cancellation, exhausted budgets, untrusted document instructions, prompt injection, access boundaries, retries, and partial publication. Do not disguise technical failures as unsupported business facts.
- Adversarial tests confirm document text cannot expand source access, choose external recipients, apply signatures, or invoke external submission.
- A human reviewer verifies the first live run's answers and rendered placement. Confidence or a second model's approval is not proof of correctness.
- A developer can reproduce the deployed workflow from documented repository code/configuration and approved deployment instructions; local tests remain offline by default. Local execution is not accepted as proof of hosted runtime, Copilot publication, business-source access, or production readiness.
- The M3 demonstration includes a documented working path through M365 Copilot/Teams when tenant publication is approved. If blocked by tenant/admin or infrastructure access, identify the exact external prerequisite, demonstrate the hosted Foundry workflow separately, and keep the front-door acceptance explicitly open.
- Test correct revision targets, missing/ambiguous references, unsupported factual requests, stale base versions, repeated/idempotent requests, failed publication recovery, and unchanged signatures/date prohibitions. Human-only assertions cannot become document-supported answers.

### M3 implementation backlog (October 28, 2026)

This backlog turns the M3 implementation order into code slices. Work the slices in order; each slice follows the TDD workflow, runs offline by default, and must not depend on manually prepared per-run JSON. A slice is not done until its listed tests pass and the README documents any new command.

**Gap analysis against existing code.** These components exist and are reused, not rewritten: inventory and evidence selection ([inventory.py](../src/bd_packet_builder/inventory.py), [sources.py](../src/bd_packet_builder/sources.py)), native text and quote resolution ([evidence.py](../src/bd_packet_builder/evidence.py)), opt-in OCR ([ocr.py](../src/bd_packet_builder/ocr.py)), native and visual form discovery ([discovery.py](../src/bd_packet_builder/discovery.py), [visual.py](../src/bd_packet_builder/visual.py)), the source catalog and retrieval planner ([retrieval.py](../src/bd_packet_builder/retrieval.py)), structured model calls ([foundry.py](../src/bd_packet_builder/foundry.py), [proposals.py](../src/bd_packet_builder/proposals.py)), proposal/citation checks ([contracts.py](../src/bd_packet_builder/contracts.py)), layout validation ([layout.py](../src/bd_packet_builder/layout.py)), narrative planning ([responses.py](../src/bd_packet_builder/responses.py)), and the PDF writer/assembler ([draft.py](../src/bd_packet_builder/draft.py)). The gaps that forced the Broward attempt to use externally prepared inputs are:

| Gap | Current behavior | Required change |
| --- | --- | --- |
| G1 Run identity | No run contract; each CLI command reads/writes its own JSON files | One run contract, run state machine, isolated run workspace, and provenance manifest |
| G2 Form-to-layout | `ResponseLayout` accepts only `developer_mapped_subset_not_automatic_discovery`; visual maps are never converted | Deterministic conversion of validated visual maps (normalized display coordinates) into `Requirement` plus `MappedResponse` placements, with native-anchor checks and explicit flags for rotated or unmappable items |
| G3 Writing gate | `DraftDecision` requires a human to confirm support, source and placement **before** writing | An application validation record produced by code checks; human review happens on the generated output, as the scope requires. The manual review path remains for development tests |
| G4 Evidence access | Retrieval runs as a developer command over a local tree; OCR is never automatic | Tool-callable evidence search/read over an approved evidence set, with automatic OCR for textless pages and OCR citations treated per the existing OCR evidence rules |
| G5 Orchestration | No agent; steps are chained by a person | Repository-defined agent instructions and narrow tools; tools enforce step order through run state |
| G6 Hosting and front door | No hosted entry point, storage adapter, or Copilot/Teams path | Hosted agent entry point on the Python 3.13 code runtime, storage port with local and Azure adapters, then publication |

**Design rule for orchestration.** The Foundry model decides which tool to call next and authors interpretations and proposals. Tools are coarse, typed, and stateful per run: each validates its inputs, rejects calls that are out of order for the run state, and records its result in the manifest. The model therefore cannot skip validation, write unvalidated answers, or publish an unchecked packet even if it calls tools in the wrong order. No tool exposes arbitrary paths, shell, network, email, signing, or submission.

**Slice 1 - Run contract, run store, and state machine (first slice; offline only).** New module `run.py` with:

- `RunRequest` (blank PDF bytes or reference, evidence-set ID, requester identity, optional requested as-of date), `RunId`, `RunStatus` (`created`, `form_interpreted`, `evidence_collected`, `answers_validated`, `packet_assembled`, `published`, plus terminal `failed`/`cancelled`), `RunOutcome` (`complete`/`incomplete` kept separate from technical failure), and `RunManifest` recording input hashes, evidence-set snapshot, prompt/schema/model/code versions, every tool call, limits, and exceptions.
- A `RunStore` protocol and a filesystem adapter that creates one isolated, path-confined workspace per run, snapshots the blank and evidence references by hash, writes atomically, and refuses to overwrite a completed run. Allowed transitions are enforced in code; an illegal transition is a typed error, not a silent no-op.
- Tests: legal and illegal transitions, idempotent retry of a completed step, refusal to overwrite published output, traversal/symlink rejection, source change during a run, manifest completeness, and incomplete versus failed outcomes.

Slice 1 has no model call, SDK, or Azure dependency. It is first because every later tool reads and writes through it.

**Slice 1 status (October 28, 2026): implemented.** [run.py](../src/bd_packet_builder/run.py) provides the run contracts, a `RunStore` protocol, and `FileRunStore`. Decisions made while building it:

- An identical retry of the latest completed step, including `publish`, returns the recorded manifest unchanged. A retry with different artifacts, exceptions, or outcome is a `RunConflictError`.
- Artifacts are stored content-addressed (`artifacts/<sha256>`) and named only in the manifest, so an interrupted write cannot block a retry or replace a recorded artifact. Exporting human-readable packet files belongs to publication (slices 7-8).
- A `complete` outcome is rejected while any review exception is recorded; a technical or budget failure sets `failed` with no outcome, never `incomplete`.
- Step-count and elapsed-time budgets are enforced; model token budgets are recorded and enforced with the agent in slice 5.
- The per-run lock uses POSIX `flock`, which suits macOS development and the Linux hosted runtime. Windows remains unvalidated.
- Evidence bytes are not read by the store; slice 4 tools must call `EvidenceSnapshot.verify` on every read.

Validation: 45 new tests in [test_run.py](../tests/integration/test_run.py); the full offline suite (663 passed, 4 opt-in skipped), Ruff and strict mypy pass on Python 3.12 and 3.13. No CLI command was added; the store is an internal boundary for later tools.

**Slice 2 - Automatic form-to-layout conversion (closes G2).** Convert validated `VisualPage` output into `ApplicationRequirements` and a `ResponseLayout` with a new scope value marking automatic, unapproved mapping. Convert normalized display coordinates to unrotated PDF points using recorded page size and rotation; rotated pages and items without a writable region become explicit exceptions, not guesses. Detect signature and signature-date items as protected regions. Tests use synthetic PDFs and canned visual maps, including columns, write-ins, image-only pages, rotation, and unreadable pages.

**Slice 2 status (October 28, 2026): implemented.** [form_layout.py](../src/bd_packet_builder/form_layout.py) provides `build_form_layout(blank_bytes, {page: VisualPage})`, which returns a `FormInterpretation`: optional `ApplicationRequirements`, an optional `ResponseLayout` (scope `automatic_visual_mapping_unapproved`), signing `protected_regions`, and review exceptions. It never contains answers. Decisions made while building it:

- Each item's question wording, option conditions, and option labels are anchored to the page's native PDF text. Matching ignores case, whitespace, and punctuation at the edges of words, and the stored wording is the exact native substring, so `validate_layout` and the writer accept it. Wording that cannot be anchored (paraphrased, image-only page) stays as a requirement with the model's wording, is not placed, and gets a `placement_not_native_anchored` exception (or a page-level exception).
- Items the existing writer would reject are screened out, so a bad item never aborts the draft. The cases are:
  - rotated, cropped, or non-standard pages (`page_geometry_unsupported`)
  - image-only pages (`image_only_placement_unverified`; OCR anchoring is deferred)
  - answer areas shorter than 12 points (`answer_region_too_small`)
  - answer areas that cover printed issuer text (`answer_region_overlaps_issuer_text`)
  - overlapping answer areas, or answer areas over signing areas (`placement_conflict`; all conflicting items are excluded, and the signing area keeps its protection)
- Kind handling:
  - A Yes/No `boolean` with two or more controls becomes `single_select`.
  - A standalone attestation checkbox is kept but not placed (`boolean_placement_unsupported`).
  - `money` is not converted, because no unit may be invented (`financial_units_unresolved`).
  - Attachments become requirements with no placement.
  - Signature and signature-date items become requirements plus protected regions, or `signing_location_unmapped` when no location is visible. No signer role is inferred.
- Pages without a visual map (`page_not_interpreted`) and unreadable pages (`unreadable_page`) are explicit page-level exceptions. An unreadable, encrypted, or out-of-range PDF is a technical `FormLayoutError`.
- Exception messages name requirement IDs and page numbers only, never issuer wording.

Validation: 21 new tests in [test_form_layout.py](../tests/integration/test_form_layout.py), including a converted layout passing the existing `validate_layout`. The full offline suite (684 passed, 4 opt-in skipped), Ruff, and strict mypy pass on Python 3.12 and 3.13. Slice 3 still has to adapt `validate_layout` and the draft writer to read the blank from run-store bytes instead of `bd_agreements/Blank`. The writer-to-converter round trip is also verified there.

**Slice 3 - Application validation gate (closes G3).** Add an application-produced validation record that the writer accepts in place of `DraftReview` for application runs. An answer is writable only when code confirms: the cited source is in the run's evidence snapshot, the page and exact quote (native or reviewed OCR policy) resolve, values pass type/unit/period checks, the placement passed layout validation, and the requirement is not a signature or signature date. Every other proposal is withheld with a reviewer exception. Model confidence never satisfies a check. Tests cover fabricated source IDs, unrelated quotes, period mismatch, signature targets, and the unchanged manual-review path.

**Slice 3 status (October 28, 2026): implemented, with two deferred items.** [gate.py](../src/bd_packet_builder/gate.py) provides `validate_answers(root, request, request_sha256)`, which returns the same `DraftReview` record the writer already consumes (reviewer `application_validation_gate_v1`, version `answer-gate-v1`), and `run_application_draft(root, request_path)`, which runs the gate and then the existing writer with no human pre-write step. `run_draft` was split so both paths share `publish_draft`; the manual-review path is unchanged. Decisions made while building it:

- A decision is `draft_verified` only if every check passes: not a signature/date item; outcome is `proposed`; native quotes resolve in the version-bound sources (`check_proposal`); the answer kind, units, and choice structure match; a placement exists; the requested period matches when one is required; every cited source is in the request's attachments; an identifier appears verbatim in a cited quote; a free-text value appears (case and whitespace normalized) in a cited quote. Anything else is `withhold` with the failing codes in `reason`. Model confidence is ignored.
- Attachment selection is derived: only sources cited by a verified answer are attached.
- The "confirmed" flags in a gate-made decision mean "code checks passed", not human approval. The reviewer name and `reason` prefix mark which path produced a record.
- A passed gate does not prove that a narrative is supported by its quote or that a business answer is right. Narrative support is evaluated separately (slice 6), and the draft stays "incomplete, not for submission" until a human reviews it.
- Deferred 1: answers cited to OCR evidence are withheld (`ocr_evidence_requires_machine_verification`) until slice 4 adds automatic OCR with machine verification.
- Deferred 2: the gate and writer still read the blank, evidence and outputs through the `root` directory layout, not run-store bytes. Slice 5 or 7 adapts them when storage is chosen; the code checks themselves do not depend on it.

Validation: 14 new tests in [test_draft.py](../tests/integration/test_draft.py) (gate), plus the existing 38 draft tests unchanged. The full offline suite (698 passed, 4 opt-in skipped), Ruff, and strict mypy pass on Python 3.12 and 3.13.

**Slice 4 - Evidence tools (closes G4).** Typed tools over the run's evidence snapshot: list catalog families, search pages for a requirement, read a page (native text, automatic OCR fallback for textless pages), and select attachments. Reuse `plan_retrieval`, `retrieve_evidence`, `select_evidence`, and `run_ocr`. Bound pages, characters, and calls per run. Tests cover missing families, stale/mismatched periods, textless pages, and prompt-injection text inside documents.

**Slice 4 status (implemented, with deferred items).** [evidence_tools.py](../src/bd_packet_builder/evidence_tools.py) provides `EvidenceTools` with `list_sources`, `search_pages`, `read_page`, `locate_quote` and `select_attachment`. Tools accept only inventory source IDs (never paths, URLs or recipients), verify the inventory against the run's `EvidenceSnapshot` at construction, and label returned text `untrusted_document_text`. `read_page` falls back to OCR for sparse/textless pages; OCR text is returned but `citable=false`, and `locate_quote` refuses OCR pages. A requested period that is unavailable returns the latest source with the `requested_period_unavailable` flag, and the gate withholds mismatched periods. Budgets (`EvidenceLimits`: calls, pages read, pages searched, hits, characters, OCR pages, attachments) raise `ToolLimitError`; counters are in memory per tool instance, so a restarted hosted runtime must reconstruct them. `retrieval.read_page` was made public for reuse.
- Deferred: machine verification of OCR citations (the gate still withholds them), and run-store-bytes access.
- Validation: 30 new tests in [test_evidence_tools.py](../tests/integration/test_evidence_tools.py); full offline suite (728 passed, 4 skipped), Ruff and strict mypy pass on Python 3.12 and 3.13.

**Slice 5 - Agent definition and offline orchestration test (closes G5).** Versioned agent instructions and per-step prompts under the package, tool registration for slices 1-4 plus `assemble_packet` (wrapping the existing writer) and `get_run_status`. Choose the agent SDK at this slice after checking Python 3.13 compatibility and pinning it in the requirements files; Agent Framework with the Foundry hosting adapter is the leading candidate from runtime research, not yet adopted. Test with a scripted fake model that issues tool calls, including out-of-order calls, malformed arguments, exhausted budgets, and injected instructions, and assert the run still ends in a correct state.

**Slice 5 status (implemented, with deferred items).** [agent.py](../src/bd_packet_builder/agent.py) holds the versioned instructions (`packet-agent-v1`), per-status guidance, the 11 typed tools (`get_run_status`, `interpret_form`, the five evidence tools, `finish_evidence`, `submit_answers`, `assemble_packet`, `publish_results`), and `run_packet_agent`, which runs them on Microsoft Agent Framework. Decisions:
- **SDK decision:** Microsoft Agent Framework is adopted (`agent-framework-core==1.23.0`, `agent-framework-foundry==1.15.0`, with transitive dependencies pinned in `requirements.txt`; verified on Python 3.12 and 3.13). The framework owns the model/tool loop and Foundry transport; `PacketAgentTools.call` remains the single authority for step order, argument validation, budgets and failures, and its call/error limits fire before the framework's. The framework rejects malformed JSON, schema-invalid arguments and unknown tools itself with plain-text errors. The hosting adapter `agent-framework-foundry-hosting` is pre-release only (`1.0.0b261022` verified to install on both versions) and is pinned at slice 7 when first used.
- **Code owns order and safety:** the run store's status gates every tool; out-of-order, unknown-tool and malformed-argument calls return a structured error and change nothing. Signature and signature-date requirements are filled with `deferred_to_signing` by code, and a model proposal for one is rejected. Requirements the model skips become `missing_evidence` exceptions. The slice 3 gate decides what is written, and `assemble_packet` runs the existing writer in a temporary staging root built from run-store bytes and snapshot-verified evidence, so the writer is unchanged.
- **Failure vs exception:** a page-mapping failure, changed evidence, a gate or writer error, an early stop, a turn limit, or too many invalid calls ends the run as `failed` with a code. An unreadable form is returned unchanged with an incomplete outcome and an internal summary.
- Deferred: `PageMapper` has only a test fake; the real Foundry mapper and the Foundry chat client are slice 6. Selected attachments and evidence budgets are in memory per agent instance, so a restarted runtime must rebuild them. The evidence root is still a local directory until the IT storage decisions.
- Validation: 23 tests using a scripted chat client inside the real framework loop in [test_agent.py](../tests/integration/test_agent.py), including a full run whose answer is gate-verified and appears in the packet; the full offline suite (751 passed, 4 opt-in skipped), Ruff, and strict mypy pass on Python 3.12 and 3.13.

**Slice 6 - Live synthetic run from a developer workstation.** Run the same agent code against the authorized Foundry model with the synthetic fixtures. This is development evidence only and does not satisfy M3 acceptance.

**Slice 6 status (implemented; live synthetic run succeeded).** [live.py](../src/bd_packet_builder/live.py) adds `FoundryPageMapper` (one visual-mapping call per blank page, reusing the existing mapping prompt and request limits; at most 5 pages for now), `build_live_client` (Agent Framework `OpenAIChatClient` over the Foundry endpoint with Azure CLI sign-in, 60 s timeout, no automatic retries), `prepare_live_run`/`run_live`, and the `bd-packet agent-run` command (requires `--allow-paid`; run store under `outputs/agent-runs/`). The current cap is 35 agent turns plus at most five page-mapping calls, with `store=False` for model requests. Findings from live runs against `gpt-6.1-sol` with a fictional one-page form and one fictional evidence PDF (kept outside the repository):
- **Result:** the model, driving only repository-defined tools, interpreted the form, listed and read the evidence, located exact quotations, and submitted answers. Legal name, CRD (leading zeros preserved) and phone were written with gate-verified citations; the EIN was reported as `missing_evidence`; signature and date were left to human signing; the run ended `published`/`incomplete` with a separate reviewer summary. This is one synthetic form, not an evaluation: run-to-run variance and answer quality are untested.
- **Defect found and fixed:** the model issued parallel tool calls, the framework ran them on threads, and pdfium crashed intermittently (segfault). `PacketAgentTools.call` is now serialized, with a regression test.
- **Usability fix:** schema-invalid `submit_answers` calls initially gave the model no detail and cost retries. `invalid_arguments` now lists field paths and error types, never submitted values. The model still needs 1-2 retries to produce a valid submission; improving the instructions or schema is future prompt work, to be measured in slice 9.
- **Content-free tool trace:** `PacketAgentTools.trace` records tool names and error codes/messages; the CLI prints it.
- **Source-folder gap (fixed):** evidence tools now see only designated source families, so a stray folder is neither listed nor readable, instead of failing the run later in the writer.
- **Mapping variance:** a second live run returned the form unchanged because the model's page mapping produced answer areas the validator judged too small. Same inputs, different result. Measuring and reducing this is slice 9 work (retry, prompt or sizing changes).
- **Not yet done:** per-call token/cost accounting in the manifest, multi-run variance measurement, forms over 5 pages, and the opt-in `BD_RUN_LIVE=1` test needs a richer fixture. Live runs use workstation storage and Azure CLI identity; this is development evidence only.

**Slice 7 - Hosted deployment (closes G6, part 1).** Uses the accepted PoC decisions in [decision 0002](decisions/0002-agent-hosting-and-copilot-front-door.md): existing Foundry project/model, beta hosting adapter, staged-ID intake and authenticated Blob storage. Add the storage adapter, deploy to the Foundry hosted code runtime, and prove a run completes with the developer workstation disconnected.

**Priority update:** Blob-backed local execution is the immediate PoC path. Hosted acceptance remains open and does not block the next real-document run. Use the complete approved library, including irrelevant/older candidates; discover requirements and select evidence/attachments at runtime without a manually supplied question/answer map. The first case is the full five-page Broward questionnaire; the separate two-page authorization form is not included in that first run.

**Real-document evidence (October 29):** the authorized five-page Broward blank and all 11 designated supporting PDFs were staged in Blob and exercised through the local application backend. Three whole-form attempts failed before evidence retrieval: 60 s request timeout, strict `json_invalid` response rejection at 180 s, then strict `value_error` rejection with a larger 16,384-token mapping allowance. No packet was generated, and no question/answer coverage or grounding-quality success is claimed. Preserve failures under `outputs/broward-agent-20261029/`. Complete-form interpretation and actionable page-level model/schema diagnostics are now the immediate bottleneck, ahead of more synthetic identity demonstrations or cloud deployments. See the [real-run record](../README.md#authorized-real-broward-attempt-october-29).

**Mapping triage:** protected raw-response diagnostics isolated a completed page-5 response that violated the attachment-item contract in six checklist rows (options on `attachment` items). Prompt `visual-map-v3` corrects that instruction ambiguity without relaxing the schema. Actual real-page verification now passes all five pages (69 items). Exact-input, prompt/schema/model-bound page caching preserves successful maps across attempts; failures remain explicit. Deterministic layout conversion still accepts only seven placed responses, with 50 native-anchor placement exceptions and two unsupported standalone boolean controls. Do not equate schema success with useful filling coverage; placement/native-anchor handling is the next demonstrated limitation. See [mapping triage usage](../README.md#mapping-triage-and-resumable-page-maps).

**Resumed real run:** attempt 4 (`d97bb56e8e3d4d2dbed08cc80ff74964`) completed application orchestration and published a seven-page **incomplete** packet plus separate internal summary. Three answers were written; 66 remained blank. Two one-page supporting attachments were included; FOCUS and FINRA selections were omitted by the existing gate. Artifact hashes and automated render-difference checks passed; pages 1, 4 and 5 were inspected locally with signature/date/checklist areas left blank. This is the first application-produced real Broward artifact in this sequence, not satisfactory PoC coverage, complete attachment handling or exhaustive grounding evaluation. Retain `outputs/broward-agent-20261029/attempt-4/` and prioritize native-anchor/placement support and required-attachment omissions. Regression validation for this triage: 799 passed, 5 skipped on Python 3.12 and 3.13; Ruff and strict mypy passed.

**Slice 7 status (implemented; hosted acceptance blocked on agent permissions).** [blob_storage.py](../src/bd_packet_builder/blob_storage.py) stages approved originals with immutable hash/size manifests, verifies downloaded bytes, rejects duplicate request execution, and separates packet from internal-review publication. [hosted.py](../src/bd_packet_builder/hosted.py) implements strict build/status commands over Responses and managed-identity model/storage clients. The local HTTP/Blob synthetic run `synthetic-host-smoke-20261028-1` wrote legal name, leading-zero CRD and telephone, left EIN/signatures/date blank, and retained readable artifacts under `outputs/hosted-smoke/`. This proves local HTTP orchestration and Azure data access, not cloud-hosted completion.

The `bd-packet-builder` code deployment reached `active` in the existing project (final tested deployment: version 3). The hosted build fails reading the input manifest with HTTP 403; the instance identity (`9b23162c-2c31-4880-8562-2c5b94eae6bb`) has no assigned storage roles. The developer's new Storage Blob Data Contributor role successfully permits staging and downloading, but does not transfer to that identity. An administrator must grant the container-scoped input/output roles and model access listed in the [README](../README.md#blob-staging-and-foundry-hosting-slice-7). Do not close G6 or call slice 7 complete until an actual hosted packet run is verified.

Runtime safeguards found during integration: custom `SupportsAgentRun` hosting requires agent-owned history and outer `store:true`; inner model calls still use `store=False`. SDK-managed telemetry export must be disabled explicitly, since the beta server otherwise enables content capture despite `OTEL_SDK_DISABLED`. Unexpected execution failures are marked failed before publishing available diagnostics, without suppressing the original error. The live budget now reserves five mapping calls by allowing at most 35 orchestration turns, keeping the total at 40 rather than the earlier 40-plus-mapping limit. Crash resume, production retention and per-requester ACLs are not implemented. Automated evaluation generation was explicitly deferred; offline tests are not model-quality evaluation.

Final deterministic validation: 790 passed, 5 skipped on each of Python 3.12 and 3.13; Ruff lint/format and strict mypy passed. Fresh Python 3.12 hosting installation and Python 3.13 dependency installation passed `pip check`. The deployment archive was inspected against a source-only allowlist before upload. This does not substitute for hosted end-to-end acceptance or model-quality evaluation.

**Slice 8 - Copilot/Teams front door (closes G6, part 2).** Publish the hosted agent, select staged blank/evidence IDs conversationally, report run status, and return the packet and separate reviewer summary through access-controlled results. Direct custom-engine Copilot file/image attachments are unsupported; do not substitute File Search text for the original PDFs required by tools. Keep tenant/admin blockers separate from application defects.

**Slice 9 - Controlled Broward acceptance run.** Run the real Broward case through the front door with authorized evidence and verify against the M3 acceptance criteria above. Fix gaps in repository code or prompts and rerun; never repair a run with external reasoning or hand-built intermediate files.

The IT confirmation in M3 step 1 can start now in parallel; it blocks slices 7-9 only. Slices 1-5 are offline and can proceed without Azure access.

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

### M5 - Production integrations and operational hardening

**Evidence/review production handoff requirement (supersedes maintained-workbook handoff):** configure access-controlled supporting evidence and separate reference/evaluation archives, plus internal JSON run/correction storage. Human-maintained Excel is not required; any Excel view is optional inspection/export, not a new workbook on every run. Enforce reviewer authorization, packet/base-version targeting, bounded evidence-backed revisions and visible change summaries through the eventual conversation surface. Keep issuer packets separate from confidential diagnostics and snapshots. Exclude synthetic artifacts and held-out answers/derivatives from production reference access. Review obsolete demo artifacts deliberately under retention policy rather than automatically deleting business records. Verify input identity, reference partitions, recovery/concurrency and reviewer-facing entry points before handover.

Dependencies: M3 hosted vertical slice and M4 regression/evaluation evidence for each integration, plus IT/Compliance approvals. The M3 PoC must already run as a Foundry-hosted application; M5 improves it for production operations and connects the durable business data/access patterns.

Requirements: FR1, FR13-FR15 and all runtime controls.

Deliverables:

- Extend the PoC source adapter to approved production folders using the selected network or synchronization pattern. Preserve source snapshot semantics, identity boundaries, least privilege and deterministic selection across adapters.
- Harden Foundry/tool deployment, durable asynchronous run state, safe resume/retry, concurrency and recovery for production workloads.
- Add internal notification to maintained verified recipients, falling back to the business owner/requester for unresolved signer roles. Surface notification failure separately from packet-generation status.
- Implement protected archive/audit handling, safe structured telemetry, retention configuration, and operator recovery procedures. Confirm retention requirements before production retention is configured.
- Complete production publication/tenant governance for the M365 Copilot/Teams front door and operational ownership. Add local debug configuration appropriate to the chosen framework once runnable code exists.

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
| Approved Foundry project/model, deployment, identity, region and model data handling | IT and technical sponsor | M3 hosted agent and live end-to-end run |
| Deterministic tool runtime choice (Azure Functions or Container Apps), identity and Foundry connectivity | IT and technical sponsor | M3 hosted end-to-end PoC; verify supported deployment/connectivity before selecting |
| PoC evidence source, read-only permissions, source owners and approved access/sync method | IT, folder owners, business owner | M3 hosted run; the deployed application cannot depend on developer workstation paths |
| Copilot/Teams publishing approval, PDF upload support, authentication and result access | Tenant administrator, IT and technical sponsor | M3 user-facing acceptance; record tenant/admin blockers separately from application code |
| Independent blank originals and additional labeled packets | Business owner and technical sponsor | Use Broward for M3 integration; collect additional packets for M4 evaluation |
| Production source locations, durable storage/archive, private networking, retention and recovery | IT, Compliance, folder owners and technical sponsor | M5 production hardening after hosted PoC |
| Recipient role/name mapping and internal notification channel | Business owner, Compliance, IT | M5 delivery; never enable external issuer notifications |
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
