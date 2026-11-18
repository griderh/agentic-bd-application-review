# Native-first historical answer extraction

Status: v56 private run published with five regressed blanks and an internal note in the
packet; v57/context v14 correction complete and offline verified. Live acceptance pending.
Last updated: November 17, 2026.

Parent: [Phase 1 roadmap](development-plan.md).
Business authority: [Phase 1 scope](../Broker-Dealer%20Packet%20Automation%20Phase%201%20Scoping%20Document.md).

## Reviewer dashboard

- [x] Milestone 1: reproduce the failure family with focused failing regressions.
- [x] Milestone 2: extract complete bounded native answers first.
- [x] Milestone 3: reconcile whole readings with bounded conditional recovery.
- [x] Milestone 4: carry the same evidence through handoff, gate, writer and review.
- [x] Milestone 5a: complete offline tests, static checks and read-only saved-evidence replay.
- [ ] Milestone 5b: obtain approval and execute paid synthetic evaluation.
- [ ] Milestone 5c: obtain approval and validate a fresh private packet.
- [ ] Review evaluation results and decide whether the change is ready for live acceptance.

**Next action:** review the v57 correction below, then separately authorize a fresh
agent-v57 private run. Synthetic paid evaluation remains separately gated. Neither paid
operation is authorized by this checklist. The v55 failure and the v56 run below remain
failed acceptance results, not passed rollout gates.

### v56 published run: five regressed blanks and an internal note printed in the packet

User run `a0116aa0...` published an incomplete draft with **43** written fields versus
**47** in v54 run `c69444c3...`. It gained Q12 but lost exactly five fields: Primary
Representative address and city, Sales Associate address, Q3 and Q10. Every other blank
matched v54. The packet also printed "Historical draft basis; internal reviewer
confirmation required." beside Q12 and on the supplemental page, and the inline Q12 lines
kept the historical form's line breaks, so they ended well short of the available width.

Plain-language causes, with the tool or method behind each step:

| Field | What the image model read | What the PDF's embedded text (pdfium) held | Why the v56 comparison rule blocked it |
| --- | --- | --- | --- |
| Addresses and city | Same text | Same text | One comma or "y" tail hung 0.7-1.25 pt below the image model's answer box. The boundary rule called any glyph more than 0.5 pt outside the box "clipped", even though the glyph's center was inside. |
| Q3 | `conciergelevel service` | `conciergelevelservice` | The word-by-word comparison treated a missing space as a missing word. OCR and a focused image reread also lacked the space. |
| Q10 | Table read row by row | Same words, stored column by column | The word-order comparison reported omitted words and a substantive conflict even though every word, including every digit, matched. |
| Q12/supplement note | n/a | n/a | When an answer had only historical citations, the writer substituted an internal review note for the "Supporting evidence" line. This predates native-first (v54 printed it on the supplement too). |

The model left Q10 blank (`conflicting_evidence`) because its historical candidate was
withheld; the four other fields failed the gate's reading-resolution check.

- [x] Measure every flagged glyph in the private source locally: all three overhangs have
  centers inside the answer box. No document text was logged.
- [x] Add failing regressions first: historical-only inline and supplement narratives print
  no reviewer text and reflow source wrapping; descender overhang is not clipping; a
  spacing-only difference and a column-ordered table resolve; changed letters or digits
  in native text or OCR stay blocked. Each positive case failed under the v13 rules.
- [x] Writer: historical-only answers print no evidence line; reviewer provenance stays in the
  internal summary. Inline narratives use the same source-wrapping reflow as supplements.
- [x] Context v14: a glyph counts as clipped only if its center lies outside the box; omission
  checks ignore differences that disappear when spaces are removed; same-word/different-order
  native text becomes `native_reading_order_differs`, which only resolves through the image
  reading when confident OCR agrees with it exactly. v12/v13 receipts keep their rules.
- [x] Replay all 70 saved checks offline (no model calls): all 70 v13 receipts still recheck;
  under v14 exactly the five reported fields change from disputed to resolved, and no other
  check changes. This is extraction evidence, not a regenerated packet.
- [x] Run both full offline suites, Ruff lint/format, strict mypy and whitespace checks
  (results below).
- [ ] Obtain approval for a fresh agent-v57 private run; verify the five fields, Q12 layout,
  and that no internal review text appears anywhere in the packet.

Offline results: **1,940 passed, 81 skipped** on each of Python 3.12 and 3.13; Ruff lint/format,
strict mypy on both targets and whitespace checks pass. Two existing supplement tests had
overflowed only because of the old note line and preserved source line breaks; their inputs now
overflow for a real reason: a smaller region and a paragraph break. Their assertions are unchanged. Rollback to v54 was not chosen: it would lose the Q12
recovery and would still print the internal note, which predates native-first.

### Subsequent v56 run: transport failure before historical extraction

User run `69d15909...` loaded agent v56/context v13, then failed at
`2026-11-17T20:16:06Z` during the second `inspect_attachment_page` tool call. The preceding
attachment image inspection succeeded; the failing call lasted approximately 4.6 seconds.
No historical-page read or answer publication was reached. The SDK connection exception was
converted to the generic connection message; the underlying DNS/socket/TLS cause was not
retained, so the saved artifacts cannot establish which transport condition occurred.
This is not a schema-validation or image-budget failure, and it does not validate the
corrected historical extraction or final coverage. No additional paid call or network
configuration change was made during read-only diagnosis.

### Later v56 run: escaped follow-up failure left a nonterminal status

User run `ef5d5333...` read all six historical pages and retained **70/73** historical
extraction candidates. Discovery used 14 independent image calls, not the exhausted
20-call budget seen in v55. Seven answer groups were staged but not finally validated.
At `2026-11-17T20:35:45Z`, a follow-up verification for `p2.q1_eligibility` started;
approximately 4.7 seconds later a connection exception escaped, ending execution.
The saved status remained `evidence_collected`, with no failure record or packet.
That is a failure-reporting defect, not an intentionally successful or renamed outcome.

- [x] Reproduce the escaped Foundry exception in an offline failing regression.
- [x] Catch Foundry failures at the grouped follow-up boundary and checkpoint a technical
  `group_verification_failed` attempt; let existing orchestration terminate as
  `failed / answer_groups_incomplete`, not a successful unresolved answer.
- [x] Verify explicit recovery preserves existing checkpoints, and an interrupted
  verification is not automatically repeated when its paid outcome is unknown.
- [x] Retain only safe exception types/cause classes in diagnostics, not exception messages.
- [x] Verify this saved run's configuration, 32 source snapshots and 54 artifact hashes
  read-only. All 114 inspected run files remain unchanged.
- [x] Run both full offline suites: **1,932 passed, 81 skipped** per Python target;
  Ruff lint/format, strict mypy on both targets and whitespace checks pass.
- [ ] Obtain explicit paid recovery authorization; inspect final validation and packet coverage.

The original saved run is deliberately unchanged, including its nonterminal status.
Local explicit recovery already accepts a checkpointed `evidence_collected` run after
source/configuration checks. The fix preserves those contracts and component versions;
it does not repair connectivity, automatically resume this run or certify its answers.

## Live regression: dense form boundaries and recovery budget

The user-reported v55 run `fad8f7c3...` wrote 24 fields versus 47 in `c69444c3...`.
Only one historical form page reached the checked handoff, versus six previously; independent
image use reached 20 calls versus 12 previously. Fifteen `native_region_possible_continuation`
warnings came from characters owned by neighboring fields, not missing answer text. Sixteen
plain answers were returned with uncertain coverage. These are observed extraction/budget
failures, not evidence that the underlying business facts disappeared.

- [x] Compare saved-run counts and receipt outcomes without changing either run.
- [x] Trace false continuation warnings to adjacent field geometry.
- [x] Reproduce dense neighboring-field and shared-budget interactions with synthetic tests.
- [x] Distinguish grounded neighboring fields from unassigned answer continuations.
- [x] Avoid crop calls for boundary defects a crop cannot resolve; retain explicit uncertainty.
- [x] Verify supported legacy receipt replay and packet-wide saved evidence without inference.
- [x] Run focused/full offline checks and record exact results and remaining live gates.

The v56/context-v13 correction checks neighboring question/role/answer relationships against
native citations or localized OCR before excluding their native characters from continuation
detection. It uses actual cited geometry where available, not arbitrary model boxes. A broad,
invented or ungrounded neighbor cannot hide a continuation. Genuine clipping and unassigned
nearby text remain unresolved; a same-sized crop cannot repair those boundaries, so no paid
crop is requested for them.

Interleaved table rows need separate handling: the full native region can be sound even when
its text is not contiguous in the PDF's page-wide reading order. If citation order is the
only native issue, complete, confident OCR matching the page-image observation can supply the
source citation. Other coverage/conflict flags still prevent that shortcut. Original native
citation limitations remain on the receipt. The source-anchor checks are shared rather than
duplicated between target fields and their neighbors.

Correction verification:

- Dense rows, columns, mixed raster labels/native answers and interleaved tables retain
  **80/80 expected synthetic answers** across two pages per layout with a two-call image
  budget. No focused crop calls are needed. Invalid neighbors and genuine omissions remain
  rejected. These are controlled offline observations, not model-quality evaluation.
- Latest saved page: **30/33** supported candidates versus **17/33** before the correction.
  Running the real extraction path with saved observations uses **one page-image call and
  zero crop calls**, within a five-call test limit. The earlier live run exhausted its
  overall 20-call image limit and the next five historical-page attempts failed.
- Previous saved packet: replay every historical page, not only Q12. **70/73** candidates
  supported versus **71/73** before native-first; the extra refusal is a clipped answer
  region, deliberately not bypassed to restore a count. All three interleaved reference rows
  remain supported. Q12 retains **361 characters / 52 words**.
- Latest page retains three review exceptions: clipping; uncertain encoding/citation with
  omitted observed text; and a nearby-text ownership check lacking sufficient corroboration.
  This correction does not claim that every blank is now fillable.
- All **106 old receipts and 106 newly derived receipts** recheck without inference.
  Hash checks confirm **354 saved run files and 32 source files** unchanged.
- Both full offline suites: **1,931 passed, 81 skipped** per Python target (3.12 and 3.13).
  Ruff lint/format, strict mypy on both targets and staged/unstaged whitespace checks pass.
- No paid calls, rebuilt private packet or fresh answering run were performed by this
  correction. Supported extraction candidates are not predicted final populated-field counts.

## Objective and boundaries

Extract the complete source-backed answer associated with a question without requiring the
image model to reproduce native PDF spelling. A matched excerpt must not be mislabeled as
a complete recovered answer.

Scope: historical plain text answers and narratives, including native, raster and mixed
regions and their question/role associations. Preserve financial/period rules, digit-only
identifier reconciliation, graphical choices and linked write-ins, historical eligibility,
source/path protection, signing prohibitions and output layout.

No new extraction engine, dependency, majority voting, arbitrary region expansion or
token-by-token composite answer. Preserve eligible historical review candidates without
claiming independently verified agreement or current business confirmation.

## Milestone 1: regression and acceptance contract

- [x] Preserve pending cleanup and scan-resilience changes.
- [x] Observe failures before the relevant production changes.
- [x] Cover image spelling errors plus missing OCR text; missing first/middle/final lines;
  lists and qualifiers; joint image/OCR omissions where native content supplies a signal.
- [x] Cover hidden/stale native text, clipped/overbroad regions, neighboring roles,
  numeric/negation disagreements and protected existing choice/write-in paths.
- [x] Cover full, partial, third, unreadable, invalid and budget-exhausted focused readings.

Acceptance: test source-location validity, association, coverage and disagreement resolution
separately from historical reuse eligibility. Do not equate populated-field counts with
complete answer correctness.

## Milestone 2: native-first extraction

- [x] Use the Foundry image model to propose the question/answer/role relationship.
- [x] Use PDFium through pypdfium2 to extract all embedded text in the bounded answer region,
  with an exact source citation and character geometry, rather than find a model-supplied string.
- [x] Check association, neighboring fields, character clipping, possible continuation,
  unique citation, encoding, invisible text and observable substantive conflicts.
- [x] Support native question/role citations without artificial OCR receipts.
- [x] Route mixed-content fields through the same workflow; do not treat native text presence
  or a successful extraction as proof of completeness.

## Milestone 3: completeness-aware recovery

- [x] Retain Tesseract words, confidence, positions and original quotations for raster or
  questionable-native regions.
- [x] Use existing PDFium/Pillow rendering/cropping and a blind focused Foundry reread only
  where needed, sharing existing budgets and caches.
- [x] Compare complete readings; do not accept a reread agreeing only with an OCR prefix
  when a longer answer has been observed.
- [x] Allow corroborated complete visible readings despite missing OCR lines or stale hidden text.
- [x] Keep technical failures, uncertain coverage, exhausted recovery and absent business
  evidence distinct. Preserve the existing schema-invalid transcription retry.

## Milestone 4: acceptance, publication and reviewer visibility

- [x] Extend the existing versioned receipt with selected text, method and coverage issues.
- [x] Share deterministic receipt rechecks across handoff, gate and independent writer.
- [x] Require complete checked narratives rather than merely supported substrings.
- [x] Verify actual synthetic PDF text and untouched form pixels; inspect rendered output.
- [x] Name PDFium, Tesseract and focused Foundry/Pillow checks in the internal summary.
- [x] Test restart without inference, tampering and source mutation.
- [x] Advance agent to v55/context to v12; retain supported legacy replay and the v10 exclusion.
- [x] Correct dense-form regression in v56/context v13; preserve v12 hashes and replay behavior.

Current-path plain-answer reconciliation replaces the OCR-targeted recovery. Compatibility,
controls, linked write-ins and digit-only identifier paths deliberately retain their checks.

## Milestone 5: validation and acceptance

- [x] Full offline suites after correction: **1,931 passed, 81 skipped** on each of
  Python 3.12 and 3.13.
- [x] Ruff lint/format, strict mypy on both targets and staged/unstaged whitespace checks passed.
- [x] Final focused reviewer-summary regression confirms exhausted recovery is explicit.
- [x] Inspect a rendered three-part synthetic supplemental answer and preserve every expected
  answer line in gate/writer tests.
- [x] Replay saved Q12 read-only: select 361 native characters/52 words instead of the old
  283-character passage; old and new receipts recheck without inference. All 75 inspected
  saved files remain unchanged. This did not regenerate a packet or run the answering agent.
- [x] Define 12 opt-in extraction evaluations: native, raster, mixed and hidden-layer layouts,
  three repetitions each.
- [ ] Obtain paid-evaluation approval and execute those cases.
- [ ] Report full-answer correctness/coverage, unsafe acceptance, correct abstention, fallback
  use, image calls and latency with denominators. Record actual cost if available; do not infer
  provider billing from call counts.
- [x] Record user-reported v55 private-run failure; live acceptance was not met.
- [x] Record v56 attempt blocked by a connection failure before historical extraction.
- [ ] Obtain separate approval for a fresh corrected v56 private real-packet run.
- [ ] Inspect rendered Q12 and protected choice/narrative answers plus reviewer explanations,
  using independent human source annotations.
- [ ] Record findings, remaining limitations and the live-acceptance decision here.

Paid extraction cases executed: **0/12**. Model-quality results are not applicable, not a pass.
Prior packets and their derivatives are not independent held-out answers. Correlated image/OCR
omissions without an observable source signal can still escape detection.

Stop live acceptance for silently omitted substantive text accepted as complete, unsupported
additions, wrong associations or protected-rule regressions. Do not certify the change from
one successful Q12 or claim a finite suite proves zero extraction errors.

## Implementation and evidence links

- [Historical extraction and receipts](../src/bd_packet_builder/historical_context.py)
- [Gate](../src/bd_packet_builder/gate.py), [writer](../src/bd_packet_builder/draft.py)
  and [reviewer summary](../src/bd_packet_builder/reviewer_summary.py)
- [Offline historical regressions](../tests/integration/test_historical_context.py)
- [Opt-in historical evaluation](../tests/integration/test_historical_equivalence_eval.py)
- [Plain-language workflow and validation commands](../README.md)
