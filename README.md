# agentic-bd-application-review
This agentic AI application reviews broker-dealer application requirements and constructs the application using supporting documentation such that it can be reviewed and submitted by signatories

## Project documentation

- [Phase 1 scoping document](Broker-Dealer%20Packet%20Automation%20Phase%201%20Scoping%20Document.md): business requirements, boundaries, and evaluation criteria.
- [Development plan](docs/development-plan.md): milestones, dependencies, acceptance criteria, and open implementation decisions.
- [Copilot coding instructions](.github/copilot-instructions.md): repository-wide Python, test-driven development (TDD), grounding, and data-handling standards.

## Development status

The foundation, local evidence inventory, native-PDF extraction, opt-in local OCR, bounded model proposals, blank-form discovery, visual mapping, and requirement-driven evidence retrieval are implemented. Retrieval routes questions to designated source families and bounded pages rather than extracting the entire supporting collection. This is not yet an automated application-completion workflow: approved fact release, integrated OCR grounding, general validated overlays, reviewer-summary generation, and packet assembly remain future increments.

The initial deliverable is a locally executed Python PoC using [blank forms](bd_agreements/Blank/) and [supporting documents](bd_agreements/supporting_data/) already in this repository. It calls a remote model through an approved Foundry endpoint, validates the results, and generates outputs locally; the model does not directly access the local folders. [Completed packets](bd_agreements/Completed/) support validated evaluation and wording precedent, not current factual authority. Network-drive mapping, cloud application hosting, Azure Blob document storage, and production integrations are deferred until the working PoC has been reviewed.

The offline foundation also includes strict requirement/proposal contracts, a manual-input review harness, and a fact-sheet **draft** validator. No fact-sheet approval, authorized release reader, or approved application filling is implemented; model-generated answers remain unapproved proposals.

**Latest agreed direction:** answers will come from supporting-document evidence, with conversational reviewer corrections and exception-only human involvement. A lightweight catalog describes likely document contents and conservative version rules; it is not a human-maintained fact sheet or a whole-drive index. Excel is optional inspection/export. Existing workbook commands remain earlier prototype tools, not the final user workflow. Targeted native-text proposals now exist; approved fact release and chat revisions do not. See the [evidence/revision/archive workflow](docs/evidence-review-workflow.md).

This increment adds explicit historical **reference versus evaluation** partitions and offline, manually supplied discrepancy checks. Historical packets can flag differences or inform wording, never establish current facts. Held-out packets are excluded from the reference reader; copies with identical hashes cannot cross partitions. No real archive was automatically assigned to a split.

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

Dependencies, including transitive packages, are pinned in [runtime requirements](requirements.txt) and [development requirements](requirements-dev.txt). Package metadata and tool settings live in [pyproject.toml](pyproject.toml). No uv, Azure credentials, or model access is needed for the offline commands or tests.

## Requirement-driven evidence retrieval

The [retrieval module](src/bd_packet_builder/retrieval.py) implements this bounded flow:

1. Take a supplied, reviewed `ApplicationRequirements` JSON, not an unapproved discovery/map dump. Automatic discovery-to-retrieval handoff is not implemented.
2. Ask the model to choose source-family IDs and an action per requirement: `fact`, `narrative`, `attach`, `read_attach`, or `unresolved`. This request contains requirements and catalog metadata only, not supporting-file contents or individual filenames.
3. Validate exact requirement coverage and family IDs locally. Code selects the document/version and enforces configured supporting/output paths; the model cannot choose paths or versions.
4. Inventory/hash only routed families, then read selected pages. Initial hints default to pages 1 and 2. If those do not contain the search terms, expand through the first four pages, stopping after a match. Hints are developer metadata, not per-application field mappings. Exact substring matches locate candidates; they do not prove answer support or completeness.
5. Separate attachment candidates from answer evidence. Attachment-only requests inspect the first hint, but that does **not** approve document identity, currency, or adequacy. Their text is excluded from answer requests.
6. Optionally request native-text answer proposals, enforcing each requirement's inspected source/page allowlist and rechecking quotations. All fill values remain null. Missing documents, ambiguous versions, unreadable pages, unmet periods, search limits and signing requirements remain visible exceptions.

The default catalog describes registration, SIPC membership, FOCUS reports, audited financials, firm services and settlement instructions. These descriptions are developer routing metadata, **not business approval**. A technical caller can supply a `SourceCatalog` JSON with `families`, each containing `family_id`, one-segment `folder`, `purpose`, `selection` (`single`, `monthly`, `annual`), and optional `page_hints`. Monthly/annual rules reuse the existing FOCUS/audited selectors. A `single` family containing multiple candidate files is unresolved: no modification-time guess is made. The business should confirm source authority and operational access/version conventions, not maintain answer values or map every source page.

### Fictional demonstration

This [reusable example](examples/retrieval_demo.py) creates five fictional supporting PDFs, six requirements and a known local evaluation under a fresh ignored output root. No existing business documents are read. Prepare inputs without credentials or model calls:

```bash
python -m examples.retrieval_demo --root . --prepare-only
```

Or explicitly authorize up to two paid synthetic calls: routing, then native answer proposals:

```bash
python -m examples.retrieval_demo --root . \
  --endpoint https://bd-application-builder-resource.openai.azure.com/openai/v1 \
  --deployment gpt-6.1-sol --allow-paid
```

The expected values/checks are not supplied to the model. The example checks a leading-zero identifier, supported service wording, missing tax identifier, wrong financial period, unresolved signature, separate attachment candidate, bounded reading, unrelated-family exclusion, unapproved answers and unchanged-context reuse with an assertion that no further model client is created. Results are written to `retrieval-evaluation.json` beside the first internal report. These are controlled-case assertions, not a general grounding or hallucination-rate evaluation.

### Caller-supplied requirements

After a technical caller supplies reviewed requirements under `outputs/`, automatic routing/proposals use:

```bash
bd-packet retrieve --root . --requirements outputs/requirements.json \
  --endpoint https://bd-application-builder-resource.openai.azure.com/openai/v1 \
  --deployment gpt-6.1-sol --allow-paid
```

This can transmit confidential selected native page text. The flag is an explicit execution opt-in, not permission to bypass business content authorization. Real supporting-document upload requires prior approval. `--catalog outputs/catalog.json` optionally replaces the default metadata.

For entirely offline local retrieval, also supply `--plan outputs/plan.json` and omit model configuration/`--allow-paid`. A developer plan matching a single supplied `crd` requirement has this shape:

```json
{"needs":[{"requirement_id":"crd","action":"fact","families":["registration"],"search_terms":["CRD"],"explanation":"Inspect registration evidence."}]}
```

Plans must cover **every** supplied requirement exactly. This manual plan is a development/offline interface, not a required business-authored mapping. Inputs must be bounded JSON files under the configured root's `outputs/`. A successful command publishes a unique `outputs/retrieval-.../retrieval.json`; exit 0 means the internal report was published, not that answers or a packet were approved.

### Limits, OCR and reuse

- Limits: 20 requirements, four routed families, 30 inventoried source files, eight distinct read pages, four candidate pages per source/need, and 20,000 native characters per page. The existing model wrapper separately rejects input above 64 KiB, bounds output and uses a 60-second HTTP timeout with retries disabled. This is not a hard total workflow deadline. Document hashing/PDF metadata still reads whole files within routed families; only text extraction is page-targeted.
- Search does not examine every page, resolve every contradiction, or dynamically browse a drive. A bounded miss is a review exception, not proof that the source lacks the fact. Broader search, source priority for ambiguous families, network-drive adapters and cross-form approved fact reuse remain later work.
- Requested financial periods cannot silently collapse multi-month/multi-year ranges to the ending period. Filename periods must be corroborated on inspected native pages; an explicitly requested ending/as-of day must also be observed. This does not establish complete semantic or reporting-period adequacy.
- Sparse native text or a dominant page image triggers an explicit OCR-needed condition. `--allow-ocr` permits the existing **local** Tesseract experiment on those selected pages, including displayed landscape/90-degree rotation. Detection is heuristic, not universal scan classification. OCR retains rendered-image fingerprints and separate reports; it is not promoted to native citations or sent to answer generation. Verified OCR-backed answers remain unfinished.
- `--cache outputs/retrieval-RUN_ID/retrieval.json` optionally reuses **unapproved native proposals** only when the requirements/application hash, catalog, route plan, source hashes, extracted page text, eligible requirements, prompt/schema and model configuration match. Substitute the actual prior report path. Sources/pages and quotations are rechecked; cached source/answer/input mutations cannot silently become approved facts. Invalid context is explicitly invalidated; malformed cache input is rejected, and failed citation checks are labeled rejected.
- Cache reuse requires the same model configuration/opt-in. It suppresses the answer call, not source/page rechecking, OCR work or automatic routing; supplying the existing plan also avoids another routing call. It is not a trusted universal answer sheet, signed fact register or cross-application approval mechanism.
- Internal reports/cache/OCR artifacts contain potentially confidential text and source metadata. Keep them out of submission packets, ordinary logs, source control and public artifacts. No approval, signatures, notification, PDF assembly or submission is introduced.

## Opt-in synthetic Foundry connection test

The local application sends versioned instructions from [the connection module](src/bd_packet_builder/foundry.py), not from the Foundry playground. This experiment does **not** create a hosted agent or change the workbook workflow. It sends only a fixed fictional company, a leading-zero identifier, conflicting fictional phone numbers, and an adversarial document instruction. It never reads application, support, archive or Excel files.

Use the authorized Azure CLI work-account sign-in (`az login` if needed). The identity needs an inference data-plane role on the model resource: **Cognitive Services OpenAI User** is the narrower OpenAI-specific choice; **Foundry User** is broader and has been verified for this development account. Ordinary Contributor management access alone is insufficient. Do not use resource keys or change permissions to bypass a failure.

After local setup, explicitly authorize one paid request:

```bash
bd-packet foundry-smoke --root . \
  --endpoint https://bd-application-builder-resource.openai.azure.com/openai/v1 \
  --deployment gpt-6.1-sol --allow-paid
```

Endpoint and deployment are nonsecret configuration, not credentials. Each invocation requires `--allow-paid` and uses `AzureCliCredential` only, with a 10-second credential-process timeout and the `https://cognitiveservices.azure.com/.default` scope verified against this resource. It makes at most one Responses request, with SDK retries disabled, a 60-second HTTP timeout and 2,048 output tokens maximum (including reasoning). The HTTP timeout is not a hard total workflow deadline. The input is fixed and bounded; output size is checked locally as well. No tools, uploads, conversation state or real document payloads are supplied. `store=False` requests no stored Responses object; it is not a guarantee about service-level retention or monitoring. The deployment's tokens-per-minute allocation is **not** a spending cap.

A completed call writes one internal `foundry-smoke.json` in a unique Git-ignored `outputs/foundry-smoke-.../` directory, never another spreadsheet. It records prompt/input/schema hashes, versions, requested limits, returned model and token usage, synthetic answers, and six deterministic checks: exact legal name/citation, exact identifier/citation, missing tax ID, conflicting phone numbers, blank signature and blank signing date. A failed check is recorded as failed and gives a nonzero exit code. Authentication, refusal, incomplete output, malformed output and technical failures produce an explicit error, not a successful report; retries must be deliberate.

**Connection verified October 23, 2026:** after assigning resource-scoped Foundry User, the standard `openai.azure.com` endpoint and Cognitive Services token audience succeeded: **6/6 controlled synthetic checks**, with 429 input tokens and 82 output tokens (511 total). The response identified `gpt-6.1-sol`; management metadata separately confirmed deployment version `2026-09-29` in `centralus`. The originally supplied `services.ai.azure.com` endpoint still rejected the Responses request with HTTP 401, and the newer `ai.azure.com` token audience was rejected even for model-list metadata. Use the tested endpoint/scope above; no automatic hostname or credential fallback is implemented. This one synthetic result does not establish general grounding, PDF completion, narrative quality or zero hallucinations. No real documents were sent.

## Synthetic PDF-to-proposals experiment

A **proposal** is an untrusted model-suggested answer, including its typed value, source/page/quote references, claimed reporting period where relevant, or an explanation for leaving it unanswered. It is not permission to fill an application.

From the repository root with development dependencies installed and the authorized CLI sign-in, explicitly run:

```bash
python -m examples.proposal_demo --root . \
  --endpoint https://bd-application-builder-resource.openai.azure.com/openai/v1 \
  --deployment gpt-6.1-sol --allow-paid
```

The [demo](examples/proposal_demo.py) creates four deterministic, fictional PDFs using the existing ReportLab development dependency: a blank questionnaire, company identity, conflicting contact record, and July financial report. You do not supply or maintain any test documents. It creates them beneath a unique Git-ignored `outputs/proposal-demo-.../synthetic-root/`, **never reads your real document folders**, and does not create Excel workbooks.

The application:

1. Inventories and extracts native text from the three generated supporting PDFs through the existing local code.
2. Sends nine predefined requirements and that extracted evidence in **one** Responses request. Expected answers and evaluation results are never included in the model request. This is not automatic question discovery from the blank form.
3. Requests a typed batch through [the proposal adapter](src/bd_packet_builder/proposals.py), then validates it against the existing `AnswerProposals` contract. The wire schema uses nondiscriminated `anyOf` for model API compatibility; application validation retains the discriminated value contract. Unknown/duplicate IDs and malformed values fail explicitly; missing proposals remain explicit missing-answer failures.
4. Runs the existing [review checker](src/bd_packet_builder/review.py) against the blank application's hash and returned citations. Exact source/page/offset/quote checks are deterministic. All fill values remain null; literal quotes, model confidence and schema validity are not semantic approval.
5. Separately scores nine controlled expectations: legal name and leading-zero CRD with supporting quotations; missing tax ID despite an adversarial instruction to invent one; conflicting phone numbers; September net capital requested but only July supplied (including an explanation of both periods); unresolved CCO; missing disclosure evidence rather than an invented “no”; and deferred signature/date.

Each run preserves the generated PDFs, internal requirements/proposals JSON, `review.json`, and `proposal-evaluation.json` together. The evaluation report is under the synthetic root's unique `outputs/review-.../` directory, printed by the command. It records source/application hashes, prompt/input/schema hashes, model/deployment, limits, usage, every proposal/check, and assertion denominators. Failed behavioral assertions are published as failed with a nonzero exit code. Technical/contract failures publish no final demo directory; staging is cleaned. Repeated runs are isolated and never overwrite an earlier run.

The shared connection boundary uses the same identity, `store=False`, timeout and no-retry behavior as the smoke test. This experiment allows up to **4,096 output tokens**, at most **64 KiB request JSON**, and **64 KiB parsed output**; native extraction is limited to 10 pages per document, 10,000 characters per page and 30,000 characters per run. An incomplete/refused response is an explicit failure, not a reason to silently retry or raise limits. These synthetic examples are not a general authorized upload interface.

**Live observation, October 23, 2026:** one synthetic case passed **9/9 requirement assertions**: 2/2 supported values with exact citations, 5/5 review exceptions, and 2/2 signing deferrals. The request used 2,175 input and 1,781 output tokens (3,956 total). This is a small controlled evaluation, separate from offline contract tests; it does not establish general semantic grounding, zero hallucinations, real-document accuracy, complete form discovery or PDF placement. No completed packet was produced and no business documents were sent.

## Real blank-form requirement discovery experiment

The [native discovery command](src/bd_packet_builder/discovery.py) reads **one explicitly selected blank PDF**, never a supporting-document or completed-packet folder. Obtain approval to send that blank's contents to Foundry first; a public website download may still contain prefilled personal/business data. Inspect it locally before authorizing a call.

```bash
bd-packet discover --root . \
  --source bd_agreements/Blank/Broward_County/BrokerDealerQuestionnaire.pdf \
  --endpoint https://bd-application-builder-resource.openai.azure.com/openai/v1 \
  --deployment gpt-6.1-sol --allow-paid
```

Unlike the synthetic proposal experiment, the model is **not given a hand-authored question list**. The command reads bounded native text and asks for exact question/label quotations, nearby section/question context, and candidate answer kinds. It makes at most one request per nonempty page, **five requests per run**, with 4,096 output tokens and a 60-second HTTP timeout per request, SDK retries disabled, and the shared 64 KiB JSON input/output bounds. Each request includes only the current page plus up to 2,000 characters from the previous page as continuation context. Source paths are confined to the blank tree; symlinks and concurrent source changes are rejected. `store=False` has the same retention caveat as the connection test.

Each finding must resolve to an exact native-text span, within the section boundaries available from the returned contexts. Repeated quotations without unique context, invented quotations and duplicate same-kind actions are flagged rather than promoted. A boolean attestation and initials may legitimately share the same source statement as distinct action kinds. Money questions without interpreted units/periods are withheld rather than assigned guessed metadata. Empty/textless pages are reported as needing review, with no model call for that page. Encrypted/unreadable PDFs or technical/model failures produce an explicit failure, no final report and no automatic retry.

The unique Git-ignored `outputs/discovery-.../discovery.json` contains the source hash, all findings and issues, candidate `ApplicationRequirements`, prompt/schema/input hashes, per-page usage and limits. The source PDF is unchanged. Candidate requirements remain **unapproved**: quotation existence does not validate meaning, answer kind, conditional dependencies, signer role, period interpretation, placement or completeness. No proposals, filled PDF, spreadsheet, supporting documents or historical references are involved in this command.

For evaluation, an independent checklist can optionally be supplied with `--checklist outputs/.../checklist.json`. It must match the blank's SHA-256 and contain unique `anchor_id`, `page`, exact `quote`, and optional exact `context` entries under `anchors`. Prepare it **before** the live call. Checklist contents/expected results are never sent to the model. The report scores literal anchor coverage separately from discovery validity; unmatched findings are review candidates, not automatically invented questions. Exit status is nonzero for flagged pages/findings or uncovered evaluation anchors. Even a zero exit status would not mean a form is completely understood or approved.

### Broward observation, October 23, 2026

With explicit user approval, the five-page public blank was inspected locally: native text on all pages, no AcroForm fields, and no apparent applicant-filled answers in the extracted text. Preprinted issuer contact names are task context, not evidence about the applicant. An independent **82-anchor** checklist was stored locally outside Git and withheld from both model runs.

| Run | Findings | Accepted literal anchors | Checklist coverage | Tokens |
| --- | --- | --- | --- | --- |
| Initial prompt v1 | 72 | 66; 2 duplicate-span actions and 4 ambiguous quotations flagged | 81/82 | 8,391 |
| Deliberate prompt v2 rerun | 72 | 71; 1 ambiguous `Other` blank withheld | 82/82 | 8,961 |

The initial report is preserved under its original validation rules. Synthetic regressions were added before fixing broad-context ambiguity and distinguishing checkbox attestations from signing actions on the same statement. Prompt v2 improved Yes/No classification and gave repeated follow-up questions exact preceding-question context. **Two runs / ten requests / 17,352 total tokens** were used; there were no automatic retries.

**This is not 100% discovery accuracy.** The checklist counts source anchors (including conditions/options), not an exhaustive number of independently fillable fields; several anchors can match one compound finding. The second run still has an ambiguous `Other` blank, classified part of an open-ended narrative as boolean, and does not explicitly link cross-page conditional dependencies. Relative periods, eligibility conditions and signer context remain quoted, not fully structured executable rules. Section boundaries also depend on model-supplied context and are not a layout parser. All 71 accepted candidates still require semantic review before driving answer generation. No applicant answers or submission packet were generated, and no supporting or completed documents were sent.

## Choice groups, write-ins, and narrative layout

The strict [requirement/answer contracts](src/bd_packet_builder/contracts.py) now distinguish:

| Answer kind | Contract |
| --- | --- |
| `single_select` | Explicit option identities and instructions; proposed answer selects exactly one |
| `multi_select` | Explicit option identities; proposed answer selects one or more distinct options |
| `narrative` | Complete supported prose, separate from its eventual placement |

Each option has its own instruction/conditions and a `write_in` flag. Proposed `write_ins` link text to an `option_id`; unknown choices, duplicate selections, missing required write-ins, unselected write-ins and write-ins on options that do not allow them are rejected. Absence of a selected option does not establish a negative fact. Selecting an eligibility label does not validate its business conditions; evidence/citation/semantic checks remain mandatory, and **all proposal fill values remain null**. The model wire schema and strict application validation both support the new types. Historical choice comparisons remain unsupported until option mappings are independently verified.

Native discovery prompt v3 can propose choice options/narratives instead of treating compound choices as plain text. It preserves candidate options in findings, but withholds choice findings from executable requirements with `choice_options_and_layout_need_interpretation`: text alone does not validate control geometry or grouped relationships. The earlier Broward discovery report remains unchanged; v3 is not claimed as a newly measured real-form discovery result.

### Local Broward layout example

From the repository root with development dependencies installed:

```bash
python -m examples.broward_response_layout --root .
```

This **offline** example reads only the previously inspected Broward blank and supports exactly its recorded SHA-256. It makes no model calls and does not read supporting/completed documents. It uses a developer-mapped subset, not an automatically learned template or a workbook the business must maintain:

- Q1: three radio-button options with eligibility wording preserved.
- Q2: twelve checkboxes across two columns; `other-instrument` and `other-agency` each own their text region.
- Q11: the full two-sentence narrative question and its writable area, rather than a standalone boolean.

The [layout validator](src/bd_packet_builder/layout.py) checks source version, instruction/option text, page dimensions, label text within visual regions, and option/write-in relationships. Coordinates are unrotated PDF points with bottom-left origin; rotated mappings fail explicitly. Rendered control appearance still needs visual verification; these checks do not automatically recognize bubbles/checkboxes, approve source facts or prove a whole form's coverage.

Outputs go to one unique Git-ignored `outputs/broward-layout-.../` directory:

- `response-layout.json`: the mapped subset and fictional narrative placement examples.
- Original and annotated PNGs for pages 2 and 4, identifying controls, write-ins and narrative region.
- `narrative-short-preview.pdf/.png`: a conspicuously synthetic one-page overlay preview of a readable inline answer and evidence reference.
- `narrative-overflow-preview.pdf/.png`: a synthetic preview of a supplemental-answer redirect. The full overflow text remains in JSON; it is not truncated. A supplemental answer PDF is not generated by this example.

These are **layout previews, not a completed application**. No applicant facts, signatures, dates or option marks are applied; the real blank remains unchanged. Manual inspection of the generated renders confirmed the three radio locations, twelve checkbox locations, separate write-in regions and Q11 narrative region. Automated synthetic PDF tests check the same contracts and actual narrative preview text placement without using the real business document as a test fixture.

The [narrative planner](src/bd_packet_builder/responses.py) measures text using supplied font metrics, including evidence references, at a fixed size of at least 10 points and line spacing of at least font size + 2. It uses the full inline answer when it fits. Otherwise it returns a readable "See Supplemental Answers, Question ..., packet page ..." marker and preserves the complete answer plus evidence references for a supplement. If even the marker cannot fit, it fails explicitly; it never truncates or silently reduces font size. Inline-plus-supplement hybrid delivery is supported at this level (form marker plus complete supplemental answer), but automatic meaning-preserving short summaries are not generated.

`PacketPagination` resolves 1-based page references from ordered form/supplement/evidence sections. It rejects missing/out-of-range/wrong-role references and does not accept reviewer-summary sections. Internal source/version/page citations remain unchanged. **The example uses hypothetical pagination** to demonstrate the rule; a real packet must supply the actual assembled order, paginate the full supplement, resolve references and verify final renders before publication. The helper alone does not verify PDF contents, source hashes or evidence support, and actual packet assembly remains unfinished.

### Synthetic model evaluation for structured answers

The existing fictional proposal demo has an opt-in extension:

```bash
python -m examples.proposal_demo --root . \
  --endpoint https://bd-application-builder-resource.openai.azure.com/openai/v1 \
  --deployment gpt-6.1-sol --structured-responses --allow-paid
```

This adds a documented eligibility category, a multi-select product list with a required Other description, and a short narrative to the original nine cases. One synthetic-only live call passed **12/12 requirement assertions**, including all three new response cases, exact citations and the existing exceptions/signing deferrals. Usage: 3,120 input + 2,544 output = **5,664 tokens**. The fixed 4,096 output-token ceiling, no-retry/explicit opt-in behavior and no-packet status are unchanged. The original nine-case demo remains the default. This does not measure real eligibility determination, general visual discovery, narrative quality or zero hallucinations; no additional real blank/evidence content was uploaded for this increment.

## Automatic visual mapping of blank pages

The [visual mapping workflow](src/bd_packet_builder/visual.py) proposes a map for unfamiliar blank forms without importing an issuer-specific coordinate template. It sends each selected rendered page image, with optional native text, to the existing model. Supporting documents, completed packets, applicant answers and local reference maps are never included. This is a mapping experiment, not an answering or packet-generation command.

```bash
bd-packet map-visual --root . \
  --source bd_agreements/Blank/Broward_County/BrokerDealerQuestionnaire.pdf \
  --pages 2 4 \
  --endpoint https://bd-application-builder-resource.openai.azure.com/openai/v1 \
  --deployment gpt-6.1-sol --allow-paid
```

Use only explicitly authorized blank forms. This opt-in permits paid model requests and transmission of the selected page images and embedded text. The same authorized Azure CLI identity, endpoint validation and no-key-fallback behavior apply. No Azure document storage, hosted agent, new service or dependency is added. `store=False` is not a guarantee about service-level retention.

### Outputs and checks

Each unique ignored `outputs/visual-map-.../` directory contains:

- `visual-map.json`: source/prompt/schema/image fingerprints, page dimensions and rotation, model usage, proposed questions/options/regions, explicit review flags and optional reference scores.
- `page-N-original.png` and `page-N-annotated.png`: source renders and visible proposed boundaries. Annotations are conspicuously unapproved; no fields are answered or marked.

The proposal distinguishes question wording, control rectangles, label rectangles, narrative/text answer regions and option-linked write-in regions. Conditions remain separate from short option labels. It has no applicant-answer fields. IDs are local to a page and source version; repeated questions across pages are not automatically linked.

Coordinates are integers 0-1000 relative to the **displayed page image, top-left origin**. Metadata records actual image dimensions, displayed PDF dimensions and source rotation. Evaluation converts these to displayed page points. This is deliberately not the unrotated bottom-left coordinate contract used by the earlier developer mapping/writer; no automatic conversion to a fillable layout or approval occurs.

The application checks strict structure, positive in-bounds rectangles, unique IDs, option relationships, and native wording/label presence when available. For unrotated pages with embedded text, it also checks labels inside proposed label regions. Rotated native-region verification is flagged as unimplemented. For image-only pages, lack of native text is a review flag, not a reason to skip the page. Model-reported uncertainty, unreadable pages and answer regions shorter than a 12-point readable line are explicitly flagged. Native matches, valid geometry and model assertions do not prove semantic correctness, complete detection or safe writing space. No separate OCR text is added to scanned blanks by this workflow; image interpretation is supplied by the multimodal model.

**Bounds:** at most five distinct pages and one request per page; 2x rendering, at most 4 million pixels and 2 MiB PNG per page, at most 20,000 native characters per page and 64 KiB text request, 4,096 output tokens per request, 60-second HTTP timeout and zero automatic retries. These are fixed experiment limits; the HTTP timeout is not a hard total-run deadline. Omit `--pages` only for documents of five pages or fewer. Oversized/encrypted inputs, invalid selections, incomplete/refused/malformed responses, changed sources/references and I/O failures produce explicit failure without publishing a successful run. Earlier unique runs remain intact. Dense pages can exceed the output limit; this workflow does not silently drop fields or automatically retry a larger request.

### Independent evaluation

`--reference outputs/reference.json` accepts a local, hash-bound `MappingReference`: page number, an independently prepared expected `VisualPage` and `exhaustive` (true by default). The reference must be prepared before the call and is never supplied to the model. Business users do not need to maintain references for every form; they are development/evaluation answer keys, not runtime templates.

Questions are matched one-to-one by whitespace/case-normalized identifying wording, not predicted IDs. Kinds and option labels are assessed separately from geometry. Control rectangles require the correct control type and at most 6 points error on every edge; label regions allow 12 points; writable/write-in regions allow 8 points. Missing/extra questions and options fail exhaustive references. Subset references score only specified questions and explicitly count other questions as unscored. Reference instruction-box geometry and full condition meaning are not scored. A passing subset is not evidence of whole-form completeness or source grounding.

Exit status is 0 only when an independent reference evaluation passes. No reference or a failed evaluation returns 1 **after saving the unapproved report**. A technical failure returns 1 without a successful report. In every case, maps remain unapproved and cannot trigger filling, signing or submission.

### Fictional PDF evaluation

Generate a new fictional four-page PDF and its withheld reference locally, without model calls:

```bash
python -m examples.visual_mapping_demo --root . --prepare-only
```

Or explicitly authorize four model calls and evaluate the generated forms:

```bash
python -m examples.visual_mapping_demo --root . \
  --endpoint https://bd-application-builder-resource.openai.azure.com/openai/v1 \
  --deployment gpt-6.1-sol --allow-paid
```

The [generator](examples/visual_mapping_demo.py) constructs the reference from known drawn geometry **before** any call. It uses three question designs (single-choice, two-column multiple-choice with two Other write-ins, and narrative) in four representations: digital portrait, digital landscape, image-only portrait, and image-only with 90-degree rotation. These are controlled feasibility cases, not a broad held-out document corpus. Offline tests use controlled responses for boundary/reliability checks; those tests do not establish model quality.

### Live observations, October 26, 2026

| Version / case | Question kinds | Controls | Label regions | Linked write-ins | Narrative regions | Result |
| --- | --- | --- | --- | --- | --- | --- |
| v1 real blank subset, pages 2/4 | 3/3 | 15/15 | 14/15 | 2/2 | 0/1 | Failed |
| v2 same real subset/reference | 3/3 | 15/15 | 15/15 | 2/2 | 1/1 | Passed subset |
| v2 four fictional representations | 12/12 | 28/28 | 28/28 | 8/8 | 4/4 | Passed controlled case |

The v1 real result included qualifying bullets in a label box and excess space above narrative writing lines. V2 clarified these general boundary rules without changing the reference or tolerances. One intervening v2 invocation failed strict schema validation and published no map; a deliberate rerun produced the published result. Failure usage was unavailable, so successful-report totals do not represent all paid attempts.

V2 usage: real subset 4,586 input + 4,848 output = **9,434 tokens** across two calls; synthetic 7,844 input + 5,583 output = **13,427 tokens** across four calls. The earlier v1 reports remain unchanged. The real evaluation covers Q1/Q2/Q11 only, not nine other proposed items, unselected pages, or all cross-page conditions. Continued answers without their prior page and overly thin single-line regions illustrate remaining review needs. Images and native text from only the authorized blank pages were uploaded; no supporting/confidential business evidence or completed packets were sent.

The next work remains independent verification and broader forms, cross-page interpretation, scanned supporting-evidence reading, approved-answer gates and deterministic packet assembly. A passing geometry evaluation does not approve facts, eligibility or a generated packet.

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

## Application requirements and answer proposals

The [contracts module](src/bd_packet_builder/contracts.py) defines the offline boundary between application interpretation and future answer generation. The local review command below exercises it with manually supplied data; it is not an automated form reader and does not extract application questions yet.

- `ApplicationRequirements`: one application hash/version and unique requirement IDs. Each requirement retains the issuer instruction, one-based page, answer/attachment/signing kind, explicit financial units, optional requested reporting-period start/end, and optional required signer role. The supplied instruction and location remain unverified until checked against the actual application.
- `AnswerProposal`: a requirement ID, explicit outcome, typed value, source/page/quote citations, optional claimed reporting period, and model confidence. A proposed answer requires citations and confidence. Missing/conflicting evidence, unreadable forms, unsupported requirements, unresolved signers, and signing deferrals require an explanation and no answer value.
- Typed values: text, string identifiers preserving leading zeros, boolean, ISO date, explicit-unit money, or attachment source identity. Money uses a plain decimal string at the JSON boundary and exposes `Decimal` internally; floats, comma formatting, exponents, and non-finite values are rejected. Attachment proposals do not accept arbitrary file paths or destinations.
- `check_proposal`: checks requirement identity, value kind/units, attachment citation identity, and exact native-text source/page/quote resolution through the existing read-only inventory. Unknown citations or altered quotes reject the proposal; source mutation and I/O failures remain technical exceptions. A requested period is compared to the proposal's claim, but neither a claim nor filename proves the actual reporting period.

These frozen Pydantic contracts are strict, versioned, reject unknown fields, and generate JSON Schema using `model_json_schema()`. Use `model_validate_json()` for untrusted JSON; strict Python validation expects actual date/tuple types rather than coercing strings/lists. Resource/call/payload-byte limits remain the responsibility of the future adapter; collection/string bounds here are not a complete model budget.

For example, a synthetic proposed money value has this shape:

```json
{"kind": "money", "amount": "1234.50", "unit": "USD"}
```

A citation identifies the inventory's path-and-content source ID and a one-based page, with `start`, `end`, and `quote` into normalized native text. The quote length must match the offsets and the resolver must find the exact text in the unchanged source. OCR and vision citations are not accepted through this native-text route. An attachment currently also requires a native-page citation; image/DOCX and textless attachment validation remain deferred.

**No proposal is approved or fillable by this increment.** Check results are `rejected`, `unanswered`, `deferred_to_signing`, or `review_required`, and `fill_value` is always `None`. Even a real, exact citation retains explicit unverified semantic support, source approval, and application-requirement issues. Signer roles and requested reporting periods remain unverified; signatures and signature dates are always deferred to human signing. A true/false attestation can be proposed with evidence, but missing evidence never becomes a false answer.

This deliberately separates a well-formed proposal from a grounded, approved answer. Approval, source governance, financial exact-value/consistency validation, semantic support evaluation, signer resolution, PDF placement, and the application-driven end-to-end workflow still need implementation. Do not bypass validation with Pydantic `model_construct()`/unchecked updates or log untrusted payloads/validation error structures; structured errors can still contain input data even though rendered validation messages hide inputs.

Pydantic and its transitive dependencies are now pinned in the runtime requirements; rerun `python -m pip install -r requirements-dev.txt` in an existing venv. Python 3.12 compatibility and a fresh venv installation were validated. No Foundry SDK, endpoint, or model call is introduced.

## Local requirement/proposal review

The [review harness](src/bd_packet_builder/review.py) connects the contracts, native citation resolver, and internal report publication. It is an implemented developer tool, not itself a pytest test runner. To run the automated synthetic integration tests, with the venv activated:

```bash
python -m pytest tests/integration/test_review.py -v
```

Those tests create their own temporary PDFs and JSON inputs, execute the review workflow, and check its outputs. No manual input preparation or business documents are needed.

**The following is a usage template, not a ready-to-run demo.** First prepare both JSON files as described below; the repository does not include or automatically generate them. Running the template without those files results in an I/O error. After preparing them, run this from the repository root:

```bash
bd-packet review --root . \
  --source "bd_agreements/Blank/New_Mexico_State/NMSTO - FY26-27-B_D-Application.pdf" \
  --requirements "outputs/review-inputs/requirements.json" \
  --proposals "outputs/review-inputs/proposals.json"
```

All input paths are relative to the explicit root. The application must be a readable, nonempty, unencrypted PDF in `bd_agreements/Blank/`. JSON input files must be under the local `outputs/` tree; absolute paths, traversal and symlinks are rejected. The PDF limit is 64 MiB and each JSON file limit is 2 MiB. Keep these manually prepared inputs confidential and Git-ignored.

Prepare the requirements file as `{"schema_version": 1, "requirements": [...]}`, with each entry following `Requirement`. Each entry must use the actual SHA-256 of the selected application and a valid one-based page. For example, **replace the placeholder hash, page, and instruction with your actual reviewed requirement**:

```json
{
  "schema_version": 1,
  "requirements": [
    {
      "requirement_id": "firm-name",
      "application_sha256": "<actual 64-character lowercase SHA-256>",
      "page": 1,
      "instruction": "Name of Firm",
      "kind": "text"
    }
  ]
}
```

The placeholder is intentionally invalid; it must not be treated as a verified application identity. A hash can be calculated with standard-library `hashlib.sha256(path.read_bytes()).hexdigest()` or your platform's SHA-256 utility. The command verifies the hash/page, not that the supplied instruction actually occurs there or that every question has been found.

Prepare proposals as `{"schema_version": 1, "proposals": [...]}`. Each proposal follows `AnswerProposal`, including source-version/page/exact-quote citations for proposed values. An empty `proposals` array is valid: it produces unanswered records for supplied answerable requirements, not invented values. Duplicate proposals and IDs not present in the requirements are input failures. An unanswered item can instead carry an explicit `missing_evidence`, `conflicting_evidence`, or other contract outcome with an explanation.

The command publishes a unique `outputs/review-<run-id>/review.json` containing:

- Application identity/page count and hashes of both input JSON files.
- Each supplied requirement in order, its proposal or absence, check issues, and status counts.
- Explicit missing proposals and human-signing deferrals; bad citations reject only their own proposal while other supplied requirements are still checked.
- Potentially confidential values, instructions, quotes, and reviewer explanations. Console output contains only the number of supplied requirements and output location.

**This is an internal diagnostic JSON report, not the scoped reviewer-summary PDF or a completed packet.** Coverage is explicitly limited to supplied requirements. All `fill_value` fields remain null; a successful command means the report was saved, not that its answers passed review. No PDF is filled, merged, approved, signed, or submitted. The input PDF is preserved even when it is unreadable; in that case the command fails explicitly rather than claiming a report/completed packet.

The application/JSON versions and inventoried supporting sources are rechecked around atomic publication; detected changes or I/O failures prevent a successful published report and clean staging on normal exceptions. This is not immutable archiving or a filesystem isolation boundary. No human source-approval workflow, semantic support decision, per-field placement, automatic requirement extraction, OCR citation support, or model adapter is added. Different issuer questions are data, not new hardcoded question lists.

## Offline historical-reference checks

Run the self-contained synthetic tests (no real archive inputs or model access):

```bash
.venv/bin/python -m pytest tests/integration/test_history.py -q
```

The [workflow guide](docs/evidence-review-workflow.md) documents strict schemas, partition trust/limitations, and the developer-only `history-check` command for manually prepared JSON pairs. It writes internal JSON only, never Excel or a packet, and never replaces current answers with historical values. Exact quote resolution or matching old answers is not proof of correctness.

## Earlier Excel fact-sheet prototype (retained, not the target workflow)

**Superseded design:** the following commands still work as implemented, but a maintained workbook is not required by the agreed evidence-first target. They do not implement model extraction or conversational corrections. Do not populate a parallel spreadsheet merely to make progress on the target workflow.

### Earlier prototype workflow: one maintained workbook

**Edit only `outputs/maintained/fact-sheet.xlsx`.** Save your changes, then run the PoC. It reads that exact workbook each time; it does not search demo outputs or regenerate facts. The business owner edits/checks/saves Excel, with no code or separate auditor required.

One-time **technical setup** (refuses to overwrite an existing workbook):

```bash
bd-packet poc-init --root .
```

This creates a blank template, not synthetic business facts. Fill in `Details > steward` and at least one row in Facts, with evidence in Evidence as available. An incomplete template is rejected rather than counted as a successful run.

**PoC entry point**, run by the local operator after saving Excel:

```bash
bd-packet poc --root .
```

Evaluation defaults to today's local date; operators can supply `--as-of YYYY-MM-DD` for reproducible checks. Intake validates the workbook automatically. The command prints a link/path to **`validation.html`**, showing per-record exceptions. A zero exit status means validation results were saved, not that all facts are correct or that a packet was generated.

Continue editing the same maintained file after every run. The application never overwrites it, and its Checks sheet is not refreshed. Read the separate HTML results instead. Exact input bytes are archived as `input.snapshot.xlsx` beside internal `fact-sheet-check.json` and `validation.html` under unique `outputs/fact-sheet-check-<run-id>/` directories. Those are internal run records, not alternate current workbooks; no `fact-sheet.xlsx` is generated there by `poc`.

**Current limit:** this PoC entry point implements fact-sheet intake and validation only. Model interpretation, answer generation, packet assembly and answer-level fact-sheet provenance are not yet implemented. This provides the intended single-workbook interaction now without pretending the end-to-end packet workflow exists.

### Developer-only Excel round-trip experiment

A fact sheet records recurring firm information with an owner, review dates, effective dates, and supporting evidence. The first [draft schema and validator](src/bd_packet_builder/fact_sheet.py) cover firm identity and named signer roles only. Real financial extraction, disclosures, contact delivery, and approved release management remain deferred.

The business-facing deliverable is **`fact-sheet.xlsx`**, not JSON. Business users edit the **Facts**, **Details**, and **Evidence** sheets in Excel. **Instructions** explains the fields; **Checks** contains dated validation results, not approval. Identifiers are text-formatted to preserve leading zeros, with dropdowns for categories/value types. Source hashes are application-maintained in a hidden evidence column; users do not type offsets or JSON.

**Ready-to-run synthetic demo**, with the development venv activated:

```bash
python examples/fact_sheet_demo.py
```

It creates its own fake source PDF and Excel draft under a unique local `outputs/` run, validates three facts, and reports one deliberately overdue review. It uses a fixed synthetic evaluation date and does not read real business documents. Open the **Excel file** printed by the script to inspect/edit values, evidence, and checks.

**Manual-input usage template**, after preparing a draft under `outputs/`:

```bash
bd-packet fact-sheet-check --root . \
  --source "outputs/fact-sheets/draft.xlsx" \
  --as-of 2026-10-21
```

This checks schema, exact native evidence quotes, current effective dates, review dates/annual scheduling, and overlapping/conflicting versions of the same fact key. Missing evidence is visible, not invented. It preserves every supplied record and writes a **new Excel workbook** with updated checks, alongside an internal `fact-sheet-check.json` for application diagnostics. Never edit the JSON to maintain facts. A successful command means the files were saved, not that the draft was approved; all facts stay unfillable.

When revalidating the synthetic demo, set `--root` to the printed run's `synthetic-root` directory and `--source` to the workbook path **relative to that root**. Do not move its evidence into the real supporting-data directory. Editing a workbook makes its existing Checks sheet stale until validation runs again. The input workbook is never overwritten.

The business owner maintains and checks the workbook; **no separate auditor or second-person fact-sheet approval is required**. `Reviewed by` may be the same person as `Owner`. Business maintainers save Excel and do not run code or edit technical hashes. Normal PoC intake now validates automatically through `bd-packet poc`; the separate `fact-sheet-check` command and synthetic generator above are developer tools, not the maintenance workflow. A graphical launch/upload interface is not implemented.

The owner is responsible for accurate source data. Mechanical checks cannot reliably detect a plausible typo. Future answers must trace to the exact workbook version/record/value used so a fact-sheet error can be identified rather than confused with a generation error. Conflicting evidence still requires an explicit exception, and packet signatories still review generated applications. The current validator does not generate answers or authorize filling. Controlled workbook access and input version tracking remain technical work, not a requirement for an additional human approver.

See the [fact-sheet workflow guide](docs/fact-sheet-workflow.md) for the fields, exact date/conflict rules, validation limits, and proposed steward/domain-reviewer/approver responsibilities. Excel support uses pinned openpyxl, et-xmlfile, and defusedxml dependencies; no remote service is involved. After pulling dependency changes, install `requirements-dev.txt` in the development venv as described above.

See the [foundation decision record](docs/decisions/0001-local-foundation.md) for library choices, verified behavior, and remaining work.
