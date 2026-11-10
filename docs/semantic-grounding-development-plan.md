# Semantic reuse with verifiable evidence

Status: Slice 1 implemented November 6, 2026; Slices 2-5 remain planned. This document
records the sponsor's agreed direction. Semantic model-quality evaluation has not started.

## 1. Objective

Complete previously unseen applications using applicable approved current and historical
evidence, without requiring identical question wording. Preserve precise source verification,
historical provenance, business prohibitions and a separate internal reviewer summary.

The simplest effective first implementation is:

**Verified source readings + model-assisted question correspondence + extractive answers +
deterministic policy checks + explicit reviewer exceptions.**

Do not add a second agent, vector database, universal fact ontology, new model provider,
embedding pipeline or separate semantic judge. Reuse the existing discovery, grouped
answering, typed proposals, evidence receipts, gate and writer.

This implements the [Phase 1 scope](../Broker-Dealer%20Packet%20Automation%20Phase%201%20Scoping%20Document.md),
particularly Section 6's historical and cross-municipality policies. It does not authorize new
document access, paid calls, signatures, submissions or changes to financial-period rules.
The [existing development plan](development-plan.md) remains the overall roadmap.

## 2. What support means

Treat these as separate decisions, not one boolean called "grounded":

| Decision | Question | Consequence |
| --- | --- | --- |
| Source fidelity | Does the approved source actually contain the cited content or selected answer? | Unresolved material reading/selection errors require reconciliation or an exception for that content. |
| Applicability | Does that content address the target question's entity, role, scope, conditions and period? | Applicable content can proceed; uncertain or incompatible content cannot be silently treated as applicable. |
| Coverage | Which requested parts have an applicable answer, and which do not? | Fill supported parts when the output can represent partial coverage honestly. |
| Reuse eligibility | Does business policy permit this historical representation here? | Enforce signatures, disclosures, periods, contradictions and issuer-specific restrictions. |
| Currency | Is continued validity currently corroborated? | Eligible historical answers may remain draft prefills with continuity explicitly unconfirmed. |

An old approved answer is evidence of that historical representation. Missing current
corroboration alone is not missing evidence and must not automatically block eligible historical
prefills. No contradiction is not proof of current truth.

Examples:

- Historical specialization wording answers a differently worded specialization question:
  reuse the verified wording with historical provenance and continuity warning.
- Specializations plus daily trading volume requested; only specializations available:
  fill the specialization portion and identify volume as unanswered.
- Current-period financial quantity requested; only an older-period figure available:
  do not enter that figure as the requested value. Report the available period and gap.
- A municipal-products-only question cannot receive an undifferentiated firm-wide product
  description just because both mention specialization.
- An old "No" disclosure does not automatically answer a new disclosure question.

For composite narratives, "partial" describes the answer's coverage, not a weak confidence
score. For indivisible yes/no questions or certifications, partial support is not a complete
answer: do not assert compliance with an unmet requirement.

## 3. Existing mechanisms to retain and change

| Surface | Retain | Change |
| --- | --- | --- |
| [Historical extraction](../src/bd_packet_builder/historical_context.py) | Approved source hashes, OCR/native citations, page geometry, original readings and bounded reconciliation | Classify harmless question presentation differences separately from material source-reading differences. |
| [Control inspection](../src/bd_packet_builder/historical_controls.py) | Pixel-based selection and control-to-label relationship checks | No detector redesign in this increment. Semantic similarity must never choose a checkbox. |
| [Contracts](../src/bd_packet_builder/contracts.py) | `HistoricalBasis`, `HistoricalCorrespondence`, typed answers and citations | Add only the bounded applicability/coverage information actually consumed by validation and review. |
| [Answering](../src/bd_packet_builder/agent.py), [grouped workflow](../src/bd_packet_builder/grouped.py) | Existing bounded model calls, verified evidence handoff and recovery checkpoints | Produce correspondence and coverage in the existing answer call; expose the actual source and target questions. |
| [Historical policy](../src/bd_packet_builder/history.py) | Reuse restrictions, current contradictions, roles and explicit currency warnings | Separate applicability uncertainty from unconfirmed continuity. |
| [Gate](../src/bd_packet_builder/gate.py), [writer](../src/bd_packet_builder/draft.py) | Independent receipt/policy rechecks, exact value support and protected output regions | Stop treating incidental lexical mismatch as a universal semantic decision. Both must consume the same typed contract and shared checks. |
| Reviewer summary | Separate internal artifact with sources and exceptions | Show correspondence, coverage gaps, currency and extraction disputes as distinct findings. |

Exact matching still belongs in source IDs/hashes, citation resolution, structured references,
identifier/money/date checks and extractive answer verification. An exact target question in a
contract can bind the assessment to the actual form; that is not a requirement that the
historical question have the same wording.

There are also two different relationships:

1. **Within a historical packet:** does this main-form question point to this supplemental answer?
2. **Across applications:** does that verified historical answer address the new question?

Do not use a cross-application applicability assertion as proof that a historical navigation
pointer belongs to a particular supplement.

## 4. Implementation sequence

Each slice uses TDD: focused failing tests, smallest complete implementation, then gate/writer
integration tests. A slice is complete only when its observable contract is verified.

### Slice 1 - Stabilize historical question links without broad fuzzy matching

**Implemented:** agent v31/gate v20/writer v15. Added 38 cases covering presentation,
protected conditions/values, forged links, native versus image-only truncation, and
gate/independent-writer behavior. Both supported Python suites pass 1,480 tests with
42 opt-in skips. Saved-run gate replay restores Q3 in `df859ab2...` (46 -> 47 accepted)
and retains all 45 accepted decisions in `0b42eb8b...`. Independent writer replay of the
latest run adds only Q3, preserves Q1/Q10 and all other written answers, and changes no
pixels outside allowed regions. Rendered Q3 placement and supplement were inspected.
Original run/source artifacts are unchanged; no paid calls were made.

Replay exposed a required compatibility case: a supplement prints a shortened heading
ending `-:`. The implementation permits a longer linked question only for an explicit
terminal `-:` or `...` marker, matching substantive prefix and compatible numbering,
with independent native-PDF verification of that heading. Arbitrary unmarked prefixes
and image-only truncated headings reject. This proves source navigation, not full semantic
coverage of the longer question; applicability remains a separate assessment.

No per-link model correspondence schema was needed for this presentation-only slice.
Differently worded links remain unresolved until the semantic-applicability implementation.

**Purpose:** fix the observed Q3 failure and remove harmless presentation instability.

1. Extend the existing supplemental-pointer integration tests with punctuation, line breaks,
   capitalization, numbering included/omitted, and explicitly conflicting numbering.
2. Introduce one shared question-presentation helper. Extract a leading question number only
   from a recognizable number label; normalize presentation in the remaining wording.
   Do not strip numbers embedded in financial periods, quantities, conditions or identifiers.
3. When both sides have explicit question numbers, reject a conflict. When one side lacks a
   number, require matching substantive wording and the existing verified packet/role/pointer
   checks. An omitted number alone is not evidence of a different question.
4. Preserve rejection of different questions, altered negation, missing receipts, forged hashes,
   wrong roles and navigation pointers inserted into answer text.
5. For differently worded links, add a bounded per-link correspondence record only when needed.
   Bind it to the exact pointer and supplemental receipts, and have the existing answer call
   assess that relationship separately. Ambiguous numbering or multiple plausible supplements
   remains an exception, not a "best match wins" choice.

**Acceptance:** the latest Q3 numbering variant passes the complete gate/writer path; conflicting
numbers and different-question controls still fail. Saved evidence replay retains previously
accepted Q1 and Q3 cases. No changed source files, saved-run manifests or paid calls.

**Stop rule:** do not add edit-distance thresholds, question-specific regex repairs or
issuer-specific synonym lists to solve this case.

### Slice 2 - Make semantic applicability explicit in the existing answer contract

**Mid-word truncation follow-up:** gate v23/writer v18 accept a truncated heading whose final
word is cut off (`public-:` before `public-sector`) only when all earlier words match exactly and
every existing native/pointer/source/role check passes.

**Source-presentation follow-up:** agent v34/grouped answers v6/gate v22/writer v17
share a question-only presentation comparator upstream and in source navigation. Punctuation,
case, wrapping and missing question labels do not become unresolved factual conflicts when
substantive wording agrees. Conflicting explicit labels, values, conditions and identifiers
remain protected. Resolved discrepancies are derived handoff annotations; source readings,
context-v8 hashes and schema-2 proposals stay immutable. Truncated headings retain independent
native-region confirmation and pointer/source/role checks. This is source-fidelity handling,
not an expansion of semantic reuse eligibility or partial writing.
Validation: 1,564 passed, 46 skipped on each Python target, including 57 new synthetic cases;
lint, format and strict types pass. No paid evaluation or fresh Q10 coverage measurement.

**Implementation status:** implemented in agent v32, gate/reviewer v21, grouped answers v4
and writer v16. New agent requests use schema 2; explicit legacy requests can retain schema 1.
Under `answer_first_review`, source-backed proposals must include an exact-target assessment.
Applicable extractive answers retain continuity warnings without a mandatory current
corroboration prerequisite. Partial/uncertain/incompatible/missing assessments withhold
individual answers and report explanations and gaps internally; partial writing is not enabled.
Existing conservative-policy behavior is unchanged. The new `partially_applicable` label
withholds under all schemas/policies; it cannot bypass the deferred partial-writing work.

The existing handoff already carries target instructions, checked historical question/answer
associations and current evidence. Correspondence is produced and archived in the same
grouped answer call, then rechecked by the final gate and independent writer. No extra
semantic judge, dependency, call or retrieval mechanism was added.

The lexical audit retains source-only question/supplement navigation and literal-value
checks. A disputed historical selected-control question can still require source-reading
reconciliation bound to a verified native target; semantic correspondence does not bypass
that restriction. Multi-piece composition retains its existing same-source/role relationships.
Cross-packet composition and structured partial-coverage spans remain Slice 3 work.

Validation: 16 new offline contract cases include all assessments, missing correspondence,
grouped schema-2 publication/archiving, target mismatch, altered receipt, role mismatch,
period mismatch, current contradiction, legacy/conservative compatibility and prevention of
partial-writing bypass through those compatibility paths. Gate plus
independent-writer cases verify extraction, blank behavior and separate continuity/applicability
review messages. Full suites: **1,496 passed, 46 skipped on Python 3.12 and 3.13**; Ruff
lint/format, strict mypy on both targets and whitespace checks pass.
Offline gate replay preserves all 48 latest accepted answers (`f1833520...`) and all 46
previously accepted answers plus Slice 1's Q3 (`df859ab2...`) under both request schemas;
original artifact hashes remain unchanged. Four synthetic model-evaluation cases were
prepared before the prompt change but **not executed**. These offline results establish
contracts and replay compatibility, not model semantic quality or zero hallucinations.
Use a fresh versioned run for separately authorized paid validation.

**Purpose:** implement new-form reuse, rather than just make identical forms less brittle.

1. Reuse `HistoricalCorrespondence`; require a target-bound assessment for historical proposals
   under the new contract version. Preserve source question and answer receipts.
2. Extend the assessment to distinguish applicable, partially applicable, uncertain and
   incompatible. Make meaningful differences explicit: entity/role, requested information,
   product or business scope, period, qualifications and conditions.
3. Feed the existing answer call the actual target instruction, relevant historical questions,
   verified answer content and available current evidence. Do not give held-out expected answers.
4. Return correspondence with the proposal in that same call. No extra semantic-model call
   by default. A valid schema or an "applicable" label is not proof that the interpretation is right.
5. Code checks exact references, source approval, available explicit entity/role/period constraints,
   contradictions and business prohibitions. Model interpretation handles meaning that code
   cannot honestly establish from lexical rules.
6. An uncertain applicability decision remains an explicit exception. A confident statement
   does not override a known period mismatch, contradiction or forbidden act.
7. Route material source-transcription disputes through existing reconciliation, not through
   semantic correspondence. Do not use the target's desired wording to manufacture historical text.
8. Audit lower-level lexical checks along this path. Retain those proving source identity or
   literal answer support; replace only those incorrectly deciding question equivalence.
   Document any source-layout restriction that legitimately prevents transfer.

**Acceptance:** production gate/writer tests support unseen paraphrases with verified historical
answers, reject misleading near-matches, and show continuity warnings without unnecessary
current-evidence rejection. A contract test alone does not establish semantic quality;
Slice 5's model evaluations are required before claiming this works reliably.

### Slice 3 - Support partial answers with source-extractive content

**Purpose:** answer available parts without implying that the complete request was satisfied.

1. Add a small bounded coverage list to correspondence, not a separate fact database.
   Each entry identifies the requested part using an exact target-instruction span, its coverage
   status, supporting receipt/citation references and the gap if unanswered.
2. For proposed text, use verified source answer spans or contiguous excerpts. Existing citation
   offsets/word spans should carry those excerpts; add a locator only where existing contracts
   cannot express it. Code verifies that excerpts belong to the checked answer region.
3. Assemble narrative content from those verified excerpts using fixed separators, preserving
   dates, qualifications, negation and context. Navigation pointers are never answer pieces.
   Do not introduce unrestricted paraphrasing or model-written factual transitions.
4. Start with individual sources and the already-supported multi-piece composition path.
   Where cross-packet composition is needed, bind each piece to its own checked relationship;
   reject conflicts rather than pooling unrelated passages. No new general synthesis engine.
5. Render supported narrative parts in the existing field/supplement mechanism. If the form
   cannot represent partial content without implying full compliance, leave that response
   unanswered and show supported evidence in the internal summary.
6. Coverage for checkbox/boolean/certification fields is all-or-nothing unless the form provides
   separately answerable subfields. Never select a "Yes" because only some conditions are supported.
7. Preserve draft/incomplete status for unresolved parts. Use the existing reviewer summary to
   state what was filled, what remains unanswered and why; do not insert internal review notes
   into submission attachments.

**Acceptance:** a composite specialization/volume question fills specialization only, preserves
its provenance and flags missing volume. Qualifiers remain intact, financial periods do not
roll forward, and partial evidence cannot create an unsupported certification.

**Deliberate limitation:** copying/excerpting can produce awkward prose. Accept that initially
when it is clear and faithful. Add paraphrase only if demonstrated form-fit/usability cases
cannot be solved by excerpts and existing supplemental layout.

### Slice 4 - Wire review, replay and version compatibility end to end

**Purpose:** avoid a proposal that passes one layer but is silently lost in another.

1. Carry correspondence, coverage and source references through discovery/handoff, grouped
   response parsing, staging, final validation, writer request, audit and reviewer summary.
2. Keep gate and writer deterministic checks in shared helpers. The writer rechecks source
   evidence and policy, not a new model opinion; it must not blindly trust a saved gate verdict.
3. Report separate findings for extraction failure, applicability uncertainty, partial coverage,
   historical continuity, contradictions and technical failures. Preserve actionable diagnostics.
4. Version changed schemas, answering instructions, applicability behavior, agent and gate.
   Preserve immutable old evidence receipts when their source meaning is unchanged; avoid
   retroactively rewriting old run artifacts. New behavior requires a fresh versioned run.
5. Preserve conservative-policy behavior. Enable the new historical-prefill behavior through
   the existing explicitly recorded `answer_first_review` policy, not a second feature-flag system.
6. Add recovery round-trip tests for the new proposal metadata. Do not relax resume compatibility
   or repeat completed paid work to migrate old runs.
7. Update the README and directly affected scope/plan terminology only where clarification is
   necessary. Surface a business-policy conflict instead of silently rewriting the scope.

**Acceptance:** a synthetic new-form run reaches a rendered incomplete packet and separate
reviewer summary with the same accepted content and gap status across all layers.
Verify output placement and protected regions, including supplemental answers.

### Slice 5 - Prove effectiveness before adding more mechanisms

**Purpose:** measure the actual new-form requirement, not just the observed Q3 repair.

Prepare the synthetic evaluation cases before changing prompts, then keep an unseen test
subset separate from implementation examples. Default tests remain offline; model evaluation
and approved real-document checks require explicit opt-in.

| Case family | Required result |
| --- | --- |
| Identical questions with presentation variants | Same applicable answer despite omitted numbering or formatting differences. |
| Unseen synonymous wording | Correct extractive answer, cited to the approved historical source. |
| Narrower/broader product scope | Supported subset or explicit gap; no misleading full answer. |
| Composite question with a missing part | Supported narrative portion filled; missing portion reported. |
| Similar question with changed negation/condition | No unsupported transfer. |
| Financial/reporting-period mismatch | No old value represented as the new requested value. |
| Wrong issuer-specific role or entity | No improper transfer; appropriate exception. |
| Current contradiction and conflicting historical sources | No convenient-source selection or unsupported answer. |
| Missing current corroboration | Eligible historical prefill with continuity warning, not automatic rejection. |
| Corrupt citation, unresolved mark or reading disagreement | Existing evidence safeguards remain effective. |
| Signature, personal acknowledgment and negative disclosure | Existing prohibitions remain effective. |
| Unreadable form and layout failures | Preserve inputs, expose incomplete/failure status and do not claim successful filling. |

Run the smallest relevant tests during each slice. Before completion, run the full offline
suite on supported Python versions, Ruff lint/format, strict mypy and diff checks.

Then run a fixed opt-in model evaluation: at least 30 synthetic cases, including at least
10 positive unseen rewordings, 10 incompatible/safety cases and 5 partial-coverage cases.
Use three independent runs of that fixed set to expose variation. Report case-level and
run-level denominators; repeated calls are not additional independent examples.

Report separately:

- Source-citation validity and literal answer fidelity.
- Applicability accuracy and wrong-transfer count.
- Eligible-answer coverage, including supported-part coverage.
- Unsupported assertions and missed contradictions.
- Correct abstention and false-abstention counts.
- Historical-status/partial-gap reviewer-summary completeness.
- Rendering/protected-region checks.
- Calls, latency and recovery behavior versus the baseline.

Initial acceptance gate: all curated safety cases reject prohibited transfer; all emitted
answers have valid source support; all intended partial cases represent gaps correctly;
at least 90% of eligible unseen rewording cases succeed in each evaluation run.
Report counts, not just percentages. These are release checks for this bounded increment,
not proof of zero hallucinations or a replacement for the scope's held-out evaluation.
No eligible cases or unexecuted paid evaluations means "not measured," never "passed."

Finish with an explicitly authorized fresh application-run check on the selected Broward
inputs, inspecting Q1/Q3 and the entire packet for regressions, then an unseen synthetic form.
Identical-form recovery alone is not the new-form acceptance criterion.

## 5. Priority and stop rules

Implement in order: **stable links -> semantic applicability -> partial extractive answers ->
end-to-end integration -> evaluation**. Build the Slice 5 case set at the start, not after
seeing model outputs. Do not stop after the numbering repair and describe it as semantic reuse.

Prefer a few coherent changes to the existing modules over a new subsystem. Introduce one
small shared helper module only if gate/writer reuse would otherwise create duplication or
an import cycle. No dependency additions are expected.

Do not widen access to real documents, add a retrieval service, or increase model-call budgets
by default. If approved evidence is present but discovery fails to retrieve it, measure that
separately; only then consider a bounded retrieval improvement. If semantic errors persist,
inspect failed cases before considering an extra judge, larger model or ontology.

Out of this increment: title transcription repairs, sleep/time-limit recovery, infrastructure,
signing/notifications, unrestricted paraphrase, arbitrary fact synthesis and general OCR
redesign. Preserve existing independent protections and do not silently tighten or loosen
the current discrepancy-tolerant policy. Any necessary behavior change gets its own regression
case and explicit explanation.

## 6. Definition of done

The application, without externally supplied answers or review decisions, completes supported
parts of an unseen synthetic form from approved historical evidence; validates actual source
content and reuse policy; preserves unsupported parts and human-action fields; and publishes
a correctly rendered incomplete draft plus a separate traceable reviewer summary.

All implementation, contracts, prompts and tests are committed/versioned through the normal
review process. Offline tests, saved-evidence replays and paid semantic evaluations are reported
separately. This document itself does not claim any of those future results.
