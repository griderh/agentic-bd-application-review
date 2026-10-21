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
| [Completed packets](../bd_agreements/Completed/) | Human-validated comparison/evaluation and permitted development precedent for wording only; never current factual authority or held-out answer input |

Use configurable repository-relative paths, resolved from an explicit repository/data root rather than the caller's working directory. Preserve these inputs unchanged. Write generated packets, reviewer summaries, manifests, and evaluation results to a separate configured, Git-ignored local output location. Maintain dataset partitions so completed holdout packets cannot leak into the answering workflow.

**Not part of initial PoC development:** network-drive mapping, VPN/ExpressRoute, SharePoint/Blob synchronization, production private networking, cloud hosting, Teams/Copilot publishing, production notification delivery, and signing-service integration. Do not implement these or make their design/access decisions prerequisites for the local PoC. Keep a narrow local filesystem boundary so source locations can be changed or an adapter added later without rewriting business rules; do not build speculative network adapters now.

**Agreed PoC architecture:** The Python application runs on the developer's computer, reads documents from the local repository folders, and calls a remotely hosted model through an approved Foundry endpoint. The application sends only the relevant document text or page images needed for interpretation, validates the returned results, and generates the packet and reviewer summary locally. The model does not need direct filesystem access to the repository.

Live interpretation requires endpoint reachability, approved credentials, and appropriate handling of the document content sent to Foundry. This is model API access, not application hosting or network-drive integration. No local model, Foundry-hosted application, or Azure Blob document upload is required for the PoC. Unit and synthetic integration tests remain offline; cloud application hosting and document storage can be considered later.

**Sequencing:** M0-M3 establish the working local PoC; M4 broadens local coverage and evaluation. M5-M6 are a deferred production roadmap, not PoC completion criteria. Begin production/network integration planning and implementation only after the business sponsor has reviewed the working PoC and agreed to proceed.

Implementation has started with the [local foundation increment](decisions/0001-local-foundation.md): Python 3.12 tooling, offline synthetic tests, a deterministic monthly source-selection rule, and a narrow native-field PDF read/write/render demo. This does not complete M0 or the end-to-end PoC: SDK/framework and OCR/overlay choices remain open. No Azure application deployment, model integration, or signing integration has been implemented.

The first M1 slice now adds a read-only supporting-document metadata inventory, source hashes/identities, PDF page counts, duplicate-content flags, monthly FOCUS and annual audited-financial filename selection, and version/page reference checks. The [README](../README.md#local-supporting-document-inventory) documents the runnable command and limits. This is a metadata snapshot, not an immutable source archive or approved fact sheet. Content-period verification, staleness policy, external/model contracts, fact extraction, consistency checks, and semantic evidence adequacy remain outstanding; M1 is not complete.

A second M1 slice adds bounded native-PDF page text, exact-substring quote resolution, and narrow labeled reporting-date comparison against filename periods. The [evidence command](../README.md#native-pdf-text-and-reporting-date-evidence) writes confidential text only to local Git-ignored outputs. It preserves textless/error pages and does not promote incomplete coverage to verified evidence. The local corpus yielded native text on 124 of 195 PDF pages; all six financial-document period checks remain unverified. This establishes an OCR feasibility dependency, not a reason to infer missing dates or claim M1 complete. Governed facts, general financial extraction, semantic support, and broad date/layout interpretation remain outstanding.

An approved [local Tesseract experiment](../README.md#opt-in-local-ocr-feasibility) now renders and recognizes one explicitly selected supporting PDF page. Tesseract is an optional system dependency; OCR output remains separate and unverified, with source/page provenance, rendered-pixel word boxes, engine confidence, and explicit limits/failures. One clean synthetic scanned page recovered 6/6 target strings; a local FOCUS page produced text but has no annotated accuracy result. Automatic fallback, OCR quote validation, financial/table accuracy, rotation/handwriting coverage, and integration into period/answer checks remain outstanding. This is a feasibility candidate, not the final production OCR decision or completion of M0/M1.

## 2. Engineering decisions and remaining choices

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

- Define validated domain/tool schemas and a governed fact-sheet format with owner, review date, and source provenance.
- Implement read-only source inventory and per-run source manifests, filename/period parsing, explicit requested-period matching, latest-applicable selection, and unresolved tie/unparseable outcomes.
- Make staleness thresholds configurable; pending sponsor approval, represent scoped defaults explicitly rather than silently treating them as approved policy.
- Implement evidence lookup, exact-value and cross-field consistency checks, and review-exception records. Keep prior packets separate from authoritative current evidence.
- Enforce configured source/output boundaries, including traversal and symlink checks, and make restricted-tier access unavailable through tools.

Acceptance:

- Parameterized tests cover competing periods, explicit unavailable as-of dates, stale sources, ties, missing files, malformed names, conflicting facts, invalid schemas, and disallowed paths.
- Missing evidence produces a blank/flagged outcome; relevant nonmatching evidence can be identified without claiming the requirement is met.
- All filled-value candidates have resolvable provenance; a fabricated source ID or unrelated citation is not accepted as grounding. Semantic evidence adequacy still requires evaluation in M3/M4.

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

Requirements: FR1-FR12, FR15-FR18.

Deliverables:

- Add the selected model adapter for page classification, field/checklist interpretation, and answer proposals with evidence references.
- Build the local end-to-end command: intake, source snapshot, interpretation, validation, filling, consistency/render checks, assembly, summary, archive, and explicit final status.
- Bound calls, tokens, elapsed time, and retries; validate outputs before deterministic tools run. Record model/prompt/schema versions in the run manifest.
- Treat legitimate issuer requirements as task data, while rejecting embedded attempts to override permissions or direct unrelated actions.

Acceptance:

- Demonstrate one issuer packet using a blank PDF from the repository and evidence/attachments from its local supporting-document folders, producing a grounded packet and separate summary in the configured local output location. Known unsupported fields remain blank, while supported attestations/disclosures are prepared for human confirmation.
- Contract tests cover invalid/truncated model output, nonexistent evidence, tool failures, rate limits, timeouts, cancellation, and exhausted budgets. Do not disguise any as unsupported business facts.
- Adversarial tests confirm document text cannot expand source access, choose external recipients, apply signatures, or invoke external submission.
- Human evidence review verifies the first live run's answers and rendered placement. Confidence or a second model's approval is not accepted as proof of correctness.
- A reviewer can repeat the PoC using documented local setup, data-path configuration, and execution commands, without any mapped network drive, storage synchronization, deployed application host, or production notification service. Local output paths and status provide the review handoff.
- Present the working PoC and its known gaps to the business sponsor before starting the deferred production/network integration work. M4 can continue locally without that integration.

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
