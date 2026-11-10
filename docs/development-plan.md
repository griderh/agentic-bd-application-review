# Phase 1 development plan

Status: implementation roadmap, rebaselined October 28, 2026.

**Slice 4 withdrawn (agent v39/groups v11):** the business owner approved removing the new
layout veto after v38 run `a3fec3e3...` withheld Q3/Q10/Q11/Q12 and generated no supplement.
Restore scan v6/context v9/gate v24/writer v19: remove layout-based approval, completeness
schema/prompt additions and related reporting. Preserve Slices 1-3, narrative rereading,
historical safeguards and evidence-phase continuation. Existing native/image/OCR verification
remains responsible for answers; weaker layout signals no longer add a blanket veto.
Synthetic regression coverage includes native-backed narratives with low-confidence or partial
OCR, table order, actual supplemental rendering and corroborated focused recovery.
Do not rewrite or resume v38/context-v10 runs; restart workers and start a fresh run.
No paid calls. Broader multiline extraction is deferred pending a demonstrated failure.
Rollback validation: 1,689 passed, 51 skipped on each Python target (3.12 and 3.13);
Ruff lint/format, strict mypy and whitespace checks pass. Model quality remains unverified
until the fresh real-packet run.
Next: fresh paid packet verification of the restored baseline before further development.

**General supporting-document recommendations (agent v40/source-context v8):** introduced
cross-municipality selection using current requirements, answer-support needs, inspected
candidate contents and approved packet precedents. Catalog purposes remain discovery cues;
historical attachment sets are not copied automatically. A fresh v40 run demonstrated that
prompt guidance alone did not ensure coverage: relevant candidates remained unassessed and
attachment-planning calls failed validation. The v40 results did not meet the intended behavior.

**Enforced candidate coverage (agent v41):** the agent now pages through every source in the
approved supporting-document catalog and records one include, exclude or review-required
decision per source in batches of up to 50. Evidence collection cannot finish until all candidate
pages have been listed and every candidate has a decision. Include and review-required decisions
must identify source pages actually read; code validates the page references. The coverage gate
does not force inclusion, copy historical packets or expose the restricted financial tier.
Missing required support and unresolved relevance remain reviewer exceptions. The private
attachment manifest v3 holds the full audit; reviewer summaries remain concise. The catalog stays
general-purpose; no issuer- or document-specific attachment rule was added.

Six synthetic paid recommendation cases cover varied support types and confidential settlement
instructions; paid evaluation remains 0/6 executed. Runs
`d541ac696bba4eb9851b1f884c4136ca` and `c9630b8e779648e69d87b42620c3ecd9` failed before evidence
handoff without planning calls. Run `18112502b289447fbab7ff72bf9d1c81` confirms it loaded agent
v42/groups v12; run `6e73ae20d11d49938617c1bd95f45261` loaded v43, but still repeated candidate
listings and failed before handoff. The v43 code blocked general `list_sources`, but duplicate
candidate-list calls returned success-shaped empty pages. In v44, repeated pages are rejected
with explicit next-step guidance, and the private progress log includes safe validation details
for rejected `finish_evidence` and repeated candidate listing. Candidate decisions remain model
driven. Run `b39367debf3d4a6dbf60bf24f199853b` loaded v44 but records only “started” for its
candidate-list calls, with no tool completion or validation event; `finish_evidence` then reports
that candidate enumeration was never initialized. An unexpected exception inside candidate
listing is plausible but not proven because no exception details were persisted. Agent v45 now
fails closed at the tool boundary and records only the tool name and exception class, avoiding
arguments, document text and exception messages. Run `bf67cb3a7c454562b0b955d2db000975` then
confirmed `list_attachment_candidates` failed with `ValidationError`. A synthetic regression
reproduced it: catalog family folders such as `Business Continuity Statement` contain spaces,
but source-summary and family-query schemas used the stricter identifier pattern `^[\w.-]+$`.
The shared `SourceFamilyName` contract now permits safe single-folder names, and agent v46 records
the updated tool schema. Run `d2fad40c616a48baac154b0126d40e68` loaded v46/groups v12 and
completed candidate enumeration. The first answer pass staged 13 of 14 groups; group 12 returned
invalid JSON, then explicit recovery staged it successfully. Final deterministic validation found
that 11 selected supporting documents exceeded `DraftReview.attachment_source_ids`' limit of 10,
inconsistent with the 20-source request/gate/evidence limits. The review limit is now 20, and
answer-submission validation failures support explicit recovery with safe field-path/type
diagnostics. The existing run's saved groups were reused on final recovery without another
answer-generation call.

Run outcome: published a 95-page incomplete draft, 47/69 requirements written, 11 selected
supporting documents, zero unassessed candidates; not for submission. Candidate coverage ran
successfully, but semantic recommendation quality remains unverified. The first paid recovery
retried only the malformed group. Targeted draft/run/agent/grouped/live tests passed 233 with one
skip; Ruff lint/format, strict mypy and whitespace checks pass.
The duplicate-listing regression first failed against v43; the affected attachment/grouped/live
suites passed 83 tests with one skip on v44. A new synthetic unexpected-exception regression
passes on v45. V46 validation: the affected attachment/grouped/live/agent suites passed 126 tests
with one skip on Python 3.12 and 3.13; the full Python 3.12 suite passed 1,699 tests with 57
skipped. These offline tests do not establish live semantic recommendation quality.

**Evidence-phase continuation (groups v9):** a model text reply before `finish_evidence` no
longer fails the run immediately. Code resumes the same local conversation with a fixed prompt
at most twice, within the original evidence model-call and elapsed-time budgets; repeated stops
fail explicitly. Model text is not logged. Validation: 1,683 passed, 51 skipped on each Python
target; Ruff, strict mypy and whitespace checks pass. Three new offline cases; no paid calls.

**Malformed answer JSON resilience (groups v13):** one automatic regeneration per answer group
for JSON syntax errors only. Reuse the same requirements and checked evidence with validation
feedback; never repair or salvage partial JSON. The retry shares the existing three attempts per
group, cumulative group-model limit and elapsed-time budget, including the per-call timeout.
Successful groups remain saved; schema, citation and grounding checks are unchanged. Transport,
timeout, deterministic validation and finalization failures do not trigger this retry. A second
JSON syntax failure or exhausted budget retains explicit recovery without publishing a packet.
Durable request markers preserve retry accounting across interruptions and resume.
Content-free progress/application logs report retry starts, outcomes and limit skips. Private
attempt records include response byte size, allowlisted SDK completion reason and retry origin.
Existing answer plans remain immutable; start a fresh v13 run rather than upgrading older runs.
Offline tests cover recovery, repeated failures, unchanged evidence, unsupported-answer withholding,
budgets, interrupted recovery, safe logs and SDK completion metadata. No paid calls are needed
for this implementation; synthetic recovery tests are not model-quality evaluation.
Validation on Python 3.12: full offline suite **1,718 passed, 57 skipped**; Ruff lint/format,
strict mypy and whitespace checks pass. No paid model calls were made.

**Historical narrative recovery (agent v37/groups v8/context v9):** extend existing bounded
printed-wording recovery to plain historical answer text, including narratives, before handing
candidates to answering. Require an established question/role relationship; preserve selected
control checks. Try localized source-native text, otherwise one blind answer-region reread
within the shared scan budget. Accept only OCR corroboration under existing confidence checks.
Disagreement, unreadability, insufficient confidence and budget exhaustion remain explicit
unresolved outcomes, not permission to choose either reading. Retain original readings and
hashed receipts; gate/writer replay without new calls. Context v8 hashes and control-only
behavior remain compatible. This resolves transcription only, not current continuity,
applicability, financial periods or missing support. No paid calls or edits to original runs.
Validation: 1,680 passed, 51 skipped on each Python target; Ruff lint/format, strict mypy and
whitespace checks pass. Seventeen new offline cases cover recovered and unresolved narrative
output, shared budgets, native recovery, replay, low confidence and tampering. Two new
synthetic narrative transcription evaluation cases remain unexecuted (0/2); no live model
quality claim is made.
Slice 4 was withdrawn above; confirm the restored baseline and narrative recovery in a fresh run.

**Representative details, Slice 3 (writer v19):** implemented. Short single-box text answers,
issuer-form fields and write-ins keep 10 pt when they fit, otherwise use the largest size down to
a 6 pt minimum (approved by the business owner) that fits, wrapping within the reviewed box
height. Only answers that do not fit at 6 pt use the supplement. Placements record fit, size and
line count; the internal summary lists non-standard fits for legibility review. Rendered checks
are unchanged and accept PDFium's line-ending hyphen marker inline. Validation: 1,663 passed,
49 skipped on Python 3.12 and 3.13; Ruff, strict mypy clean; 0 paid evaluations executed.
Next: one fresh live run covering Slices 2 and 3.

**Representative details, Slice 2 (agent v36/gate v24/groups v7/source context v7/bios v2):**
implemented. Discovery maps each representative's text title/telephone/email requirements to
the bio link. Code extracts the printed name/title/contact card as exact rechecked spans and,
at submission, deterministically reconciles mapped fields: bio titles take precedence; contacts
keep a prior answer containing a bio value (phones keyed by digits, email exact
case-insensitive) and report historical-only details such as mobile numbers; otherwise the bio
value is used. Every selected bio is attached once with a manifest reason. Card absence is a
review exception; a post-selection bio change fails the run. Reconciliation is recorded in
`representative_contacts.json` and the internal summary, never as currency confirmation. The
gate accepts multiline quotes rendered with ", " separators. Validation: 1,658 passed,
49 skipped on Python 3.12 and 3.13; Ruff, strict mypy clean; 0 paid evaluations executed.
Slice 3 (above) then added inline short-field placement and wrapping.

**Representative details, Slice 1 (November 9, 2026; agent v35):** add bounded, typed
representative-to-bio identity resolution to discovery, not a second employee database or agent.
Keep application role assignment separate from biography identity: require explicit source
assignment or a rechecked historical name/role receipt, preserving unconfirmed continuity.
Match complete native subject headings or independently verified OCR identity/subject evidence;
never select by filename, similar names or incidental prose mentions. Record source hashes,
deduplicate identical bytes and hold distinct matching versions for review rather than choosing
by filename/date. Missing/ambiguous/unverified/budget-limited results and recognizable omitted
representative-name requirements are explicit per-role review exceptions. Persist links in
private evidence artifacts, answering handoff and the internal summary; do not approve answers
or claim current currency. Existing source boundaries, budgets and source-change failures apply.
Source context v6 reflects separate role evidence rather than demanding a current roster to
record a historical identity link. Full offline validation: 1,616 passed, 49 skipped on each
Python target; Ruff lint/format, strict mypy and whitespace checks passed. Python 3.13 used a
fresh pinned-requirements venv with clean `pip check`. Autonomous model selection is unmeasured;
no paid calls or original-run modifications were made.
Three opt-in synthetic role-selection evaluation cases were added; 0/3 executed.

Slice 2 (above) then coupled bio-grounded title/contact selection with mandatory attachment.
Compare contacts individually, preserving historical-only mobile details without treating absence
as contradiction. Then add safe inline short-field placement, general multiline historical
extraction improvements and end-to-end rendered-packet validation. Slice 1 intentionally does not
change field values, attachment inclusion requirements, font sizing or narrative overflow.

**Mid-word truncated headings (gate v23/writer v18):** a truncated supplement heading may end
inside its final word (`public-:` for `public-sector`). Earlier words must match exactly, the final
partial word must be a prefix and the full question must be longer; all native, pointer, numbering,
source and role checks remain.

**General question presentation (agent v34/grouped answers v6/gate v22/writer v17):**
share question presentation comparison across extraction handoff and source navigation.
Resolve punctuation/case/wrapping/omitted-number differences upstream as derived annotations,
not new source transcriptions; preserve original context-v8 receipts and hashes. Explicit
conflicting labels, substantive wording, numeric values/signs/operators/units and identifiers
remain significant. Truncation permits varied terminal dash/ellipsis punctuation but still
requires native source-region confirmation and existing pointer/source/role checks.
Do not use presentation normalization for answer values or semantic approval.
Synthetic tests cover handoff, selected controls without extra rereads, and gate/writer output.
Validation: 1,564 passed, 46 skipped on both Python targets; Ruff, strict mypy and whitespace
checks pass. No paid calls, scripts or original-run edits; fresh autonomous Q10 output remains
unmeasured. Start a fresh run after component changes.

**Q1 follow-up correction (agent v33/grouped answers v5):** keep the minimum criterion
and report-line selection tied to the assigned application question, but validate the
report field label against the source row rather than requiring it in the issuer wording.
Preserve source/subject/row/unit checks. Answer calls expose their remaining budgets.
Complete proposals returned with blocked follow-up requests retain explicit verification
failure notes and undergo the normal gate/writer; unverified content stays unsupported.
Incomplete responses still fail for recovery. No increase to call/request limits.
Eleven regression cases cover the two failures and their safety/replay boundaries.
Validation: 1,507 passed, 46 skipped on both Python runtimes; Ruff, strict mypy and
whitespace checks pass. No paid calls, ad hoc scripts or saved-run edits. Fresh runs
are required after the version change; the exhausted `b5f81fc6...` group cannot resume.

**Next grounding increment (November 6, 2026):** follow the
[semantic reuse development plan](semantic-grounding-development-plan.md). Separate source
fidelity, semantic applicability, partial coverage, reuse eligibility and currency. Reuse
existing bounded answering and evidence contracts; start with extractive answers, not a new
agent/retrieval subsystem. Slice 1 is implemented (agent v31/gate v20/writer v15): numbering
is separate from substantive wording, and only native-verified explicit supplemental
truncation permits a longer linked question. Saved-run replay restores Q3 without losing
Q1/Q10 or other written answers. Both Python suites pass 1,480 tests with 42 opt-in skips.
Slice 2 is implemented (agent v32/gate v21/grouped answers v4/writer v16). New schema-2
`answer_first_review` proposals require exact-target correspondence assessed in the existing
answer call; applicable extractive content can be written with unconfirmed continuity.
Partial, uncertain, incompatible or missing correspondence is an explicit per-answer exception.
Source fidelity, business prohibitions and deterministic role/period/conflict checks remain.
Schema-1 replay/conservative behavior is preserved. Saved-run replay retains all 48 latest
accepted answers under both schemas and preserves Slice 1's Q3 recovery. Validation:
1,496 passed, 46 skipped on each Python target; Ruff, strict mypy and whitespace checks pass.
No paid model evaluation ran; semantic-quality effectiveness is unmeasured. Continue with
Slice 3 for partial extractive writing, followed by the remaining wiring/evaluation slices.

**Historical-control pixel stability and label grounding (v30):** evaluate rectangle, circle and connected-check
evidence together within a bounded hint neighborhood. Anchor intact circles to pixel
components, group overlapping fits on one physical outline, and discount small contained
loops only when their ink belongs to the independently verified check component. Estimate
check arms from supported component columns and use component-height fit tolerance, avoiding
single-column antialiasing and hint-padding classification changes. Separate competing
controls/marks still require review; sparse ink stays ambiguous.
The saved Q1 mark is selected in 81/81 recorded-box/shift/padding/resolution combinations,
with identical detected bounds per resolution. All 24 previously matching controls among
28 saved receipts remain matched; two mismatches now match. Synthetic gate/writer cases
preserve output-region limits. These are offline verification results, not autonomous
coverage recovery. Q2 and Q3 remain separate issues. Control-label relationships use the
pixel-located mark and the cited label's OCR/native bounds, not model box edges: same-line
base alignment, bounded gap (wider only across blank space), and no control wholly between.
Saved-run replay fixes Q1, keeps 449 decisions, and rejects four merged-OCR p2 marks whose
label side is ungrounded. Agent v30/gate v19 record control-pixel version v3; context v8 and
legacy receipt hashes stay unchanged. No paid calls, dependencies
or source/run mutations; any separately authorized live test must start a fresh run.
Validation: 1,414 passed, 42 skipped on Python 3.12 and 3.13 (79 new synthetic cases);
Ruff lint/format, strict mypy on both targets and whitespace checks passed. Model-quality
and held-out accuracy evaluation were not performed.

**Targeted printed-wording resolution (v28):** for selected historical controls in
`answer_first_review`, resolve question/option transcription independently from the selection.
Use geometrically checked source-native text agreeing exactly with localized OCR; otherwise
attempt one blind crop reread within the existing image allowance. Do not supply expected
wording or OCR alternatives to that reread. Exact agreement is required, with confidence 90
or higher on disputed OCR words; lower-confidence unchanged words require original-image
agreement too. No fuzzy digits, altered conditions or target-to-history copying. Cache the
attempt, preserve original readings and retain explicit unresolved/budget exceptions.
Historical context v8 stores source-native citations or crop hashes/transcripts; gate v17 and
the independent writer reproduce checks, retain mark/applicability/policy validation and keep
legacy receipt hashes stable. Agent v28/question-reading v2 expose resolved wording to answering.
The scanned Q1/Q7 regions have no native text: fresh focused readings remain unmeasured, not
silently replaced by historical successful model outputs. Offline saved-run revalidation
retains all 44 accepted answers; Q2 is unchanged. Synthetic production gate/writer cases cover
both resolution paths and rejection/tampering. Five new paid synthetic evaluation cases remain
unexecuted (0/5); no paid calls or new dependencies for this increment. Full offline validation:
1,335 passed, 42 skipped on Python 3.12 and 3.13; Ruff lint/format, strict mypy for both targets
and whitespace checks passed.

**Supplemental-answer question links (v27):** keep navigation pointers out of answer
composition. `HistoricalBasis.question_links` holds checked main-form pointers to supplemental
answers; only `prior_question` and `additional_contexts` are answer pieces. Gate v16 and the
writer recheck links and require the same packet/role, no control, an undisputed short pointer
phrase and a matching question prefix; links never count as answer evidence. Saved-run
reconstruction of `90c316ca…` fills Q10 (46 populated, none lost); this is not a fresh model run.

**Bounded question-reading reconciliation (v26):** separate question transcription from answer
text and selected-control verification. Discovery and grouped answering receive target-bound
reconciliation metadata only when the image question matches unique native text in the exact
hashed blank and bounded local OCR alignment passes. Normalize spacing/punctuation; allow one
lowercase truncated word in a sufficiently long question, not arbitrary spelling correction.
Protected negation, operators, numbers/signs, periods and conditions cannot change. Require at
least 12 tokens, an original word of at least 8 characters, a 3-character minimum fragment no
longer than 60% of the word, and at least 94% character similarity; none is sufficient alone.
Entity fragments, deleted/changed conditions, multiple defects and interleaving still withhold.
Do not fuzz answer values, identifiers or financial figures.

Gate v15 and the independent writer rederive alignment against the actual blank and recheck
original source receipts and selected marks. Historical context v7 receipt hashes remain
unchanged. Conservative policy, contradictions and personal-act safeguards remain. Reviewer
notes distinguish question versus answer/control disputes and show the final reconciliation,
the original question readings and the historical selected answer. An already reconciled
question does not authorize filling an abstained proposal or requesting unnecessary new
business evidence just to repair OCR.

An isolated saved-evidence reconstruction fills Q6 No and retains all 45 prior populated answers:
46 populated of 69, 4 conditional not-applicable, 7 human-action and 12 unresolved. The affected
rendered page was inspected; outside-region changed pixels are zero. Original run/source
artifacts are unchanged. This is not a new autonomous model run or an independent accuracy
evaluation; no paid calls or new dependencies. Full offline validation: 1,316 passed,
37 skipped on Python 3.12 and 3.13; Ruff lint/format, strict mypy for both targets and whitespace
checks passed. Four new opt-in synthetic reasoning cases remain unexecuted (0/4).
A separately authorized fresh v26 run is needed to measure live model behavior.

**Saved-run extraction/reference repair (v25):** the v24 live run still left eligibility and
instrument choices blank and regressed three previously populated answers. Padded control hints
now resolve against actual bounded outlines; unboxed check arms are measured against the mark,
not hint whitespace. Competing controls still reject. Digit-only image misreadings reconcile
only against agreeing exact native text and high-confidence local OCR in the same answer box,
without relaxing identity matching or historical/current policy. Original readings remain
auditable; low-confidence OCR, native/OCR disagreement and forged writer reviews are covered.
Full OCR references can resolve a copied render hash only through a unique checked receipt
whose remaining fields, artifact hash and exact word span all match.

The isolated production gate/writer reconstruction has 45 populated of 69 requirements,
restoring Q1, all ten Q2 choices plus the write-in, Q4, employee discipline and primary CRD.
No populated answer from either the 40-answer v24 or 42-answer v21 run is lost. Affected rendered
pages were inspected and outside-region changed pixels are zero. Fourteen unresolved,
seven human-action and three conditional not-applicable requirements remain, including
eligibility-proof/period review concerns. Original run artifacts and sources remain unchanged.
This is saved-evidence reconstruction, not new autonomous-model coverage or held-out accuracy.
No paid calls were made. Full offline validation: 1,278 passed, 33 skipped on Python 3.12 and
3.13; Ruff lint/format, strict mypy for both targets and whitespace checks passed.
Provenance is agent v25, historical context v7, answer groups v3 and checked-citation resolution
v2, with stable legacy receipt hashes; institutional knowledge remains v2. A separately authorized
fresh v25 live run is still needed before claiming autonomous recovery.

**Historical-confirmation conflict cleanup (v24, domain knowledge v2):** removed the residual
blanket historical-boolean exclusion for eligibility/disclosures. Checked historical reading
and current-truth confirmation are explicitly distinct. Current-source inspection is attempted
within budget but is not an acceptance prerequisite under `answer_first_review`; empty current
checks and failed/unavailable current corroboration remain reviewer gaps, not contradictions.
Grouped compound-condition instructions and native proposals preserve the same historical path.
Existing deterministic gates were not weakened. Tests cover no-current-inspection eligibility,
noncorroboration versus actual contradiction, and sensitive historical booleans in both policies.
Full offline validation: 1,264 passed, 33 skipped on Python 3.12 and 3.13; Ruff and strict mypy
for both targets passed. Four additional paid reasoning cases were added but not executed
(0/4). The subsequent v24 live run exposed the extraction/reference failures described above;
offline success was not a model-quality result.

**Applied institutional knowledge (v23):** one packaged, versioned reference now owns curated
document interpretation and sponsor policy, replacing the source-context business-rule dictionary
and overlapping prompt blocks. Document routing metadata and verified source facts remain separate.
Each entry records authority, applicability and limits. Both discovery and answering use it;
the run records version/hash, and evidence handoff persists its snapshot. Recovery rejects
reference changes. Per-answer IDs, reasons and hashes survive grouped staging into the internal
audit/summary as model-reported use, not proof of reasoning or evidence approval.

Historical eligibility without fresh per-condition corroboration still writes a flagged draft
when the checked prior question/selection is applicable; real contradictions still block.
BrokerCheck status dates alone do not prove uninterrupted registration or business operations.
No new knowledge service, automatic learning, dependencies or weaker evidence gates were added.
Offline validation: 1,255 passed, 29 skipped on both Python 3.12 and 3.13; Ruff and strict mypy
for both targets passed. Wheel/resource loading was independently verified. Four new synthetic
reasoning cases are opt-in and unexecuted (0/4); live v23 answer coverage remains unmeasured.

**Bounded v22 completion repair:** local pixel inspection now supports an unboxed two-arm
checkmark without classifying empty/ambiguous regions as unselected. Historical control labels
can reconcile localized OCR control/bullet artifacts only when all substantive option words
match and local mark inspection succeeds. Original readings remain in the audit. Instructions
explicitly use checked, context-matched historical eligibility as draft evidence without
demanding current re-certification of each condition; contradictions and incompatible conditions
still block, and all current uncertainty is prominently retained for human review.

The actual firm BrokerCheck body uses hundreds of vector paths with only native footer text,
not a dominant bitmap. Sparse-native/vector-heavy pages now trigger the existing local OCR
reader within its existing budget. Local reading of PDF pages 3, 12 and 13 produces substantive
firm-profile/operations text. This is discovery text, not independent evidence approval.

A separate local reconstruction from the latest saved run uses the rechecked historical Q1
selection and unchanged Q2 proposal. Both pass the production gate and independent writer.
The rendered PDF was inspected: regional dealer is selected and all ten instrument selections
plus the Other write-in are present; zero pixels change outside allowed regions. There are
43 written answers of 69 requirements overall; other blanks and signing deferrals remain.
This is explicitly a local reconstruction, not a fresh model execution or a claim that the
entire form is complete. Original run artifacts remain unchanged; no paid calls were made.
Three opt-in synthetic eligibility interpretation cases were added but not executed.
Validation: 1,249 passed, 25 skipped on Python 3.12 and 3.13; Ruff lint/format,
strict mypy for both target runtimes and whitespace checks passed.

**v21 live-run correction:** run `a130f735ae704cf98a3be2d9e5c7d408` proposed all ten Q2
selections and the exact write-in, but its explicit write-in `additional_contexts` reference
was rejected as an unsupported text-composition kind. The earlier synthetic tests and manual
reconstruction omitted that legal-looking reference and therefore missed the producer/consumer
contract mismatch. The shared gate/writer verifier now accepts these references only if they
match independently verified choice-linked write-in receipts. It does not treat them as free
text composition or waive selection/text/source checks. Tests cover with/without explicit
contexts, unrelated contexts and forged positive reviews.

The exact saved live request passes the updated gate and isolated production PDF writer,
including the ten selections, native write-in text and zero outside-region changes. No
model calls were made; original run artifacts remain unchanged. Q1 remains blank: this run
did verify the page-8 capital threshold, but historical extraction still reports an unresolved
control outline and option-text discrepancy; the model also requires confirmation of the
remaining eligibility conditions. A local crop shows a visible checkmark. The Q2 contract
correction is not a Q1 extraction/policy fix and must not be reported as one.
Validation: 1,231 passed, 22 skipped on each of Python 3.12 and 3.13; Ruff lint/format,
strict mypy for both target runtimes and whitespace checks passed. Paid evaluation was not run.

**Historical complete-choice repair:** agent v21 / scan and historical-context v6 separate
control, printed option label and entered write-in. Answering receives an explicit linked
write-in citation instead of having to rediscover its relationship. Tight adjacent native text
can recover omitted write-ins and corroborate an OCR token merged across the label/write-in
boundary; original readings remain in the audit. No issuer, instrument or entered value is
hardcoded. Missing/unsupported mandatory write-ins still withhold the whole choice question;
the gate and writer independently verify source text, layout and the complete selected set.
Legacy receipt hashes remain stable. Fresh execution is required for the new prompt version.
Synthetic tests cover alternate wording, right-column and wrapped write-ins, missing/invented
values, omitted selections and forged receipts/reviews, including rendered output. Three
opt-in synthetic image-evaluation cases were added; paid evaluation is not run by default.
This repair does not resolve Q1's separate undiscovered-evidence-page limitation.

Offline validation: **1,201 passed, 22 skipped on each of Python 3.12 and 3.13**;
Ruff lint/format, strict mypy for both target runtimes (40 application files) and whitespace
checks passed. A read-only reconstruction of saved Q2 evidence passes the historical verifier
with all ten selected options and the exact linked write-in. This is not a paid model run or
a regenerated real packet. Synthetic writer tests verify complete rendering, whole-question
withholding and zero outside-region changes, including attempts to bypass the gate with a
forged positive review. Three new paid image-evaluation cases remain unexecuted (0/3).

**November 3 complete evidence handoff and bounded follow-up:** approved increment implemented
as agent v20 / answer workflow v2. Native/OCR observations and independent image transcriptions
remain available to answering as untrusted candidates, with candidate OCR snapshots archived.
Typed source/page/quote/subject verification requests are restricted to discovered pages; code
returns checked citations to the affected group without reopening the discovery tool loop.
At most two follow-up rounds fit within three group attempts, thirty group calls and existing
image/tool/time limits; twenty verification requests are permitted per run. Successful groups
and completed checks survive explicit recovery. Durable request markers distinguish interrupted,
unknown paid work, which is reported rather than silently repeated.

An explicit USD minimum supports deterministic `Decimal` comparison only after verifying the
firm/subject and an exact same-row amount/field/line association. Scans require OCR/image row
agreement and confidence checks on the relevant OCR words. One monetary condition does not
establish continuous operation, regulatory compliance, banking applicability or overall eligibility.
Checked monetary findings and verification failures are carried to the reviewer summary;
additional exact-criterion status notes remain model assessments, not trusted reviewer approvals.
The original source and ordinary independent gate/writer checks remain mandatory.

Offline validation: 1,174 passed, 19 skipped on Python 3.12 and 3.13; Ruff lint/format,
strict mypy (40 application files) and whitespace checks passed. The actual saved page-8
OCR/image data passes the same-row and minimum-comparison helpers read-only in memory; this
is not a regenerated application or a live coverage claim. Three added synthetic paid protocol/
grounding evaluation cases were not run; model-quality metrics remain not applicable.
README now contains a workflow and file-by-file artifact guide. Old v19/v1 archives remain
unchanged and cannot be upgraded in place; use a fresh, explicitly authorized demo for v20/v2.
Historical choice/control ambiguity (including Question 2) is not loosened by this increment.

**November 2 scanned current-evidence checks:** run `cf72c5512c834f7eb27e0777bcc00dce`
staged eleven answer groups; three failed because historical `current_checks` accepted only
native citations while exact-receipt restoration correctly recovered checked OCR citations.
Those checks now accept both citation types. Gate and writer independently verify scanned
source/render/artifact integrity, subject/transcription agreement and confidence. Inspected
but non-corroborating evidence does not become answer support or current confirmation.
Contradictions, absent/mismatched receipts and changed artifacts still withhold the answer;
completion recovery retains current-check-only scan receipts. Native historical contexts and
checked historical relationships remain separate from scanned current checks.
All three saved failing responses pass strict group validation offline. This verifies the
reported intake failure, not live model quality or packet completeness. No paid calls were
made and the failed run remains unchanged; explicit recovery retries its three unfinished
groups, reusing eleven staged groups. Verification: 1,144 passed, 16 skipped on both Python
3.12 and 3.13; Ruff lint/format, strict mypy (39 application files), four-call-site signature
compatibility and whitespace checks passed.

**November 2 evidence-led reading reconciliation:** agent v19 and gate/writer v14 remove the
automatic image-transcription preference. A disputed answer has no preferred candidate.
Discovery targets independent current identity/field evidence using existing bounded tools.
The typed `reading_resolution` contract permits either scalar reading only with a checked
historical Name relationship for the same role and a current contextual subject/field/value
citation. Native source text or subject-aware verified scan evidence is rechecked by both gate
and writer; raw OCR, majority voting, changed subjects/labels and guessed third values cannot
resolve a conflict. Original readings remain in the audit. Unresolved fields explicitly say
LEFT BLANK with a verification action; written resolved fields say FILLED AFTER RECONCILIATION.
No published packet or run archive is modified and no paid execution is implied. Five added
opt-in synthetic model cases test both winning directions and insufficient/wrong-context evidence;
offline tests alone do not measure reconciliation model quality.
Verification: 1,135 passed, 16 skipped on Python 3.12 and 3.13; Ruff lint/format,
strict mypy (39 application files), six-call-site signature compatibility and whitespace checks
passed. Synthetic gate/writer tests verify both winning readings, exact rendered identifiers,
unchanged pixels outside allowed regions, absent scan receipts and forged-review rejection.
The paid semantic cases were not run; real-document reconciliation remains unmeasured.

**November 2 answer-group citation correction:** run `dbb0792d63094680972fc2577500eaaf`
staged 13 of 14 groups; the remaining group represented a checked OCR quote as an invalid
native offset span. No packet was published. Group intake now resolves source/page/exact-quote
references to one unique checked receipt, preserving raw responses and recording resolution paths.
Ambiguity, unknown quotes, additional fields and changed OCR hashes are not repaired. Ordinary
source and relationship verification remains mandatory. The saved failing response passes the
strict group schema after offline resolution; this is not a new live run or a completeness claim.
Recovery still explicitly retries unfinished groups only, with unchanged paid-call limits.
Validation: 1,126 passed, 11 skipped on each of Python 3.12 and 3.13; Ruff lint/format,
strict mypy and whitespace checks passed. No new paid calls or run-artifact changes were made.

**November 2 dated cross-municipality prefill and supporting-purpose increment:**
agent v18, gate v13, scan v5 and source context v4 implement the approved draft policy.
Same-municipality history is not required: question correspondence records the target wording,
meaning, differences and uncertainty. Incompatible contexts still withhold. Tenure calculations
use a source-cited signing date in the same packet and a fixed run date, not filename dates or
unverified archive metadata. Python adds completed anniversaries, including a tested February 29
rule. Headcount remains unchanged with qualifiers and current-review concerns. Financial values
and reporting periods are never extrapolated; signatures and new personal acts stay human-only.
Scanned signing metadata must have its own rechecked question/answer receipt without extraction
disagreements, including a locally OCR-verified signing anchor. Ambiguous dates leave a review
exception rather than authorizing guessed arithmetic.

The approved supporting-data family allowlist now includes the specifically cataloged marketing,
agency-performance, Bloomberg, bio and business-policy materials. Arbitrary folders and restricted
financial sources remain inaccessible. Archived cover letters remain outside automatic inclusion.
Purpose metadata carries conditional inclusion class, topics, entity/period matching and limits.
The new bounded `plan_supporting_document` tool records requirement-linked selection rationale,
exclusions and gaps, persisted in `attachment-manifest.json` and the internal reviewer summary.
The writer allows up to 20 supporting attachments and 26 sources including historical references.
Historical packets themselves remain prohibited submission attachments.

Fresh runs may receive trusted `--requirement-assessments` input (including through the demo
script), using the existing form/hash-bound reconciliation contract. It is not a model tool or
automatic semantic approval; incompatible versions/wording fail explicitly, and assessments cannot
discard proposed answers or suppress human acts. This exposes previously replay-only approved
applicability/coverage decisions without hardcoding Broward applicability into the agent.

The observed email failures were case-only differences between checked candidate and source
transcription; text matching now tolerates capitalization, while identifiers remain case-sensitive.
Exact text parts from one packet and role can be combined with separately rechecked receipts and
a correspondence explanation; extra claims and mixed-role combinations still fail.
Five pages with at most one schema-repair request each give a conservative **90 model-call**
ceiling (60 orchestration/group attempts + 10 mapping + 20 independent image reads), not 85.
Tool/time limits remain 240/60 minutes; no configured total-dollar cap.

Validation uses offline synthetic contract and end-to-end cases. Six opt-in synthetic semantic
evaluation cases cover rephrased cross-municipality questions, changed quantities/conditions,
personal acts and period mismatches. No new paid run or model-quality result is implied by these
tests; the fresh run's previous 40-populated/19-unresolved result is not replaced by a new coverage
claim. Real signature-date extraction, document choice and semantic correspondence need a new
authorized run and reviewer inspection.

**Offline verification:** 1,115 passed, 11 skipped on each of Python 3.12 and 3.13;
Ruff lint/format, strict mypy (39 application files), shell syntax and whitespace checks passed.
Skipped paid/model cases are not a semantic-quality pass. No paid calls or deployment were made
for this increment.

**November 2 demo timeout correction:** the operator's first fresh run failed with
`scan_verification_failed` because the independent historical-page image request timed out.
The live demo had inherited the generic 60-second HTTP timeout. The demo now defaults to
180 seconds per request, explicitly configurable within 1-600 seconds; no automatic retries
or evidence-validation bypasses are introduced. Generic `agent-run` preserves its default.
Start/completion events and failure codes stream to the console and persist in a timestamped
content-free `progress.jsonl`, even when discovery fails before handoff. The request timeout
is recorded in the run's component metadata. These changes do not establish that a new paid
run will complete successfully; the corrected settings require live verification separately.

**November 2 page-mapping resilience correction:** the operator's second run failed with
`form_interpretation_failed` after mapping three pages: the model's page-4 reply contained a
zero-area `instruction_box`, rejected by strict schema validation. Live and resumed runs now
use the hash-keyed `outputs/page-map-cache/`, so validated page maps are reused only for an
identical blank, rendered page, prompt, schema, endpoint and deployment. A schema-invalid
page-map reply receives exactly one fresh request; timeout, connection, authentication and HTTP
failures still are not retried. The final progress line includes the content-free failure reason.
Live success after this correction remains unverified until a new paid run is performed.

**November 2 run-visibility/demo increment:** `bd-packet broward-demo` and
`scripts/run_broward_demo.sh` provide a repeatable, paid Broward execution using the checked-in
blank and one explicitly allowlisted 2026 Broward reference. A preflight lists only source
metadata and requires typing `RUN`; the existing `--allow-paid` guard remains mandatory.
Tool progress streams phase/name/count without arguments or document text. Run ID, final state
and readable output path are shown live and artifacts are exported on completion/failure.
Repeated executions are new runs, not silent retries.

The general `agent-run` CLI also streams content-free progress. Reviewed `draft` replays remain
separate and do not call the model. The live demo requires Azure CLI inference access and can
make up to 90 paid model calls after the mapping-repair allowance, 240 tool calls and 60 minutes;
a total-dollar cap is not configured.
Its default evidence root contains confidential business documents. This operator affordance
improves reproducibility and visibility, not model accuracy or application completeness.

**October 30 reviewed requirement/checklist reconciliation:** gate/writer v12 add generic
`RequirementAssessment` contracts to trusted local review input, separate from model proposals.
Assessments bind exact issuer wording and application hash, carry source-verified native/OCR
citations and separate per-criterion sufficiency from physical inclusion. Dependency evaluation
uses actual written/reconciled results, rejects cycles and cannot clear signing/personal acts.
Reviewed optional/not-applicable dispositions cannot discard proposed answers.

Attachment controls require an explicit reviewed control/label mapping; satisfied coverage without
one is reported as placement unavailable, not missing evidence. Default form discovery does not
automatically map attachment controls. Current criteria and applicability decisions are locally
reviewed, not autonomous semantic judgments or authenticated production approvals. `validate_answers`
can carry trusted typed assessments; the writer independently validates them before publication.

**Measured result:** 49 populated, 4 conditional/not applicable, 1 reviewed FIT not applicable,
1 optional Other not supplied, 1 evidence/checklist satisfied, 7 human-action and 5 unresolved
requirements out of 68. All 49 prior answer records are unchanged. The FINRA/state-registration
checklist is checked from explicit registration evidence. The historical electronic-access limitation
is cited internally, never substituted for initials or current named-user confirmation.
References are already inline; no separate attachment is required without explicit issuer wording.

Remaining review actions are eligibility sufficiency/operating continuity, latest FOCUS period,
disclosure baseline, actual questionnaire completion and reference qualification/recency. A printed
reporting-period/catalog discrepancy is explicit; execution/filing date is not reporting period.
The replay uses local OCR and cached evidence, no new paid model calls. It does not establish
autonomous completeness, automatic criteria discovery or held-out quality.

Validation: 1,045 passed and five skipped on each Python 3.12 and 3.13; Ruff lint/format, strict
mypy and diff checks passed. Only form page 5 changes in the 70-page packet, with zero outside-region
changed pixels. The marked page was visually inspected. All six supplement and 59 copied-evidence
content streams match the previous packet.

### Previous discrepancy-tolerant increment

**October 30 discrepancy-tolerant completion increment:** `packet-agent-v17`, scan v4,
historical context v5 and gate/writer v11 implement the approved candidate policy. Localized
OCR/image discrepancies retain the actual OCR quotation plus the image candidate and exact
review concern; conservative mode still withholds. Circular controls, labels before/after marks,
duplicate-label column mapping and same-row selected write-ins are covered without issuer- or
document-name-specific application logic. Source/version, role/geometry, contradiction,
reporting-period and new-personal-act restrictions remain enforced.

The writer reconciles narrowly explicit same-page If-yes explanation fields against their
immediately preceding, actually written Yes/No parent. Withheld parents do not establish
applicability. Historical No answers carry their historical limitation into the not-applicable
disposition. Populated, conditional/not-applicable, human-action and unresolved counts are
separate; stale parent-unanswered explanations are not emitted as the effective review result.

**Measured result:** a 70-page known-form draft now has **49 populated, 4 conditional/not
applicable, 7 human-action and 8 unresolved requirements out of 68**. This adds 10 populated
answers, preserves all 39 prior populated requirements (38 proposals unchanged) and completes
the existing instruments selection/write-in. Historical tenure/headcount are copied unchanged,
never rolled forward or represented as current measurements. The outstanding eight are two
platform fields, current eligibility proof and five attachment/checklist items. Included evidence
is distinguished from missing evidence and unvalidated checklist placement. All remaining
nonsigning requirements received an updated, specific review disposition.

The benchmark reused saved independent readings and OCR plus one targeted historical-page
reading, not an hour-long broad rerun. It uses explicit matching-form correspondences, not
automatic question-equivalence discovery or a held-out evaluation. Full autonomous completion,
generic conditional interpretation and current disclosure-event-baseline comparison remain open.

Validation: 1,018 passed and five skipped on both Python 3.12 and 3.13. Ruff lint/format,
strict mypy on both runtimes and diff checks passed. Five form pages and six supplement pages
were visually inspected; all six supplement text checks passed. Outside-region changed pixels
are zero. All 59 copied evidence page content streams match the approved originals.

### Previous increment results

**October 30 extraction-first / answer-first increment:** the sponsor approved historical
response extraction independently of reuse policy, a known-form reproduction benchmark,
and checked historical candidate prefills with reviewer concerns rather than continuity-only
abstention. Chat/UI infrastructure is not part of this increment.

`packet-agent-v16` / scan v3 / historical context v5 / gate and writer v10 now support
pixel-verified rectangular controls, explicit raw selected/unselected/ambiguous observations,
column-subheader context, durable extraction diagnostics and complete selected-group receipt
rechecking at publication. Existing v4 receipt identities are preserved across the new schema.
The trusted `answer_first_review` policy propagates through live intake, run manifests,
handoff and draft requests; legacy defaults remain conservative. The CLI enables the new
policy by default. Disclosure candidates get explicit historical/legal-baseline warnings,
without claiming current-event comparison is implemented. No new signatures, dates or
personal acts, conflicting values or financial-period roll-forward are permitted.

**Measured result, not full acceptance:** two approved historical pages produced 37 observed
controls and 20 verified associations, including 18 selected controls. Known-form benchmark
correspondences produced a 68-page **39/68 populated** candidate packet (33 retained unchanged,
six newly populated, one of those partial). The instruments Other/write-in, circular
eligibility extraction and net-capital question OCR still need repair. The two changed form
pages were visually inspected and outside-region changed pixels are zero. The earlier 40/68
target is not met; no autonomous full-run improvement or held-out model-quality claim is made.
All six reference packets remain reference inputs, not evaluation holdouts.
Known-form selected-control reproduction is 17/20 (excluding a personal acknowledgment),
with zero false selected marks on the inspected pages. All 59 copied evidence page streams
match their originals. Full offline validation: 996 passed, five skipped on both supported
Python versions; Ruff lint/format, strict mypy, syntax and diff checks passed.

**October 30 historical-first completion increment (acceptance pending):** source navigation
now supports source-specific, hash-bound native page previews across approved municipalities,
with image/textless warnings rather than unsupported absence claims. This is a navigational
index, not a verified semantic document summary. `packet-agent-v15` persists the index into
answering; `historical-page-context-v4` / `answer-gate-v9` permit explicit checked historical
answer labels to map exactly to target single-/multi-select options for eligible firm-wide
descriptions/capabilities. Graphical checkbox selection extraction remains unimplemented.
The sponsor authorized the two Carrollton, Princeton and New Mexico completed PDFs for
historical reference and the existing Foundry destination, in addition to the two Broward
references; none of those six PDFs is held out for evaluation.

Completion recovery now has a code-controlled entry point that revalidates the original
request/review and blank, preserves selected supported answers, reopens evidence discovery,
and assigns only remaining requirements to answering groups. It records baseline lineage
and replays retained proposals after restart. Tests cover exact-label mismatches, multi-select,
cross-issuer firm-wide reuse, sensitive exclusions, writer revalidation, bounded navigation
and baseline-recovery mismatches. Acceptance remains a measured real-document gain with no
loss of existing answers, not these deterministic tests alone. Automated question equivalence,
graphical checkbox extraction, disclosure-event baseline comparison and fully automatic
per-requirement evidence-recovery planning remain open.

**Measured acceptance failure:** recovery `98f224e87f3244fbb7a0a05312959ff0` used all six
approved historical references for navigation and inspected 17 pages, including 11 OCR pages
and seven independent image readings. The result is **33/68**, one added BOOM Discount Notes
choice, zero lost answers, and all 32 retained proposals unchanged. The proposed 40/68 target
was not met. Thirty-five remaining blanks comprise 27 missing-evidence dispositions, one
unsupported selection path, five signing/personal-act deferrals and two rejected attachment
proposals. Missing-evidence labels remain model dispositions, not proven absence of facts.
The handoff still lacks checked primary-title/account-opening associations despite indexed
leads; it does not support most graphical selections or establish disclosure-event continuity.
Two checklist proposals still fail quote/placement checks. Broader reference permission did
not fix these extraction/representation gaps. Do not launch an unchanged retry or present this
as broad-completion acceptance.

The 68-page local packet restores Public Funds collateral and includes historical page 96's
native 2025 league table; it does **not** restore page 104's terminal screenshot. The new choice
and both appended pages were visually inspected. All appended source content streams match
their originals, retained proposals are identical, and outside-region changed pixels are zero.
The packet remains incomplete, unsigned and local-only; the choice does not resolve its
upstream Bloomberg-execution question. Full deterministic checks: 949 passed, five skipped
on Python 3.12/3.13, Ruff lint/format, strict mypy and diff checks passed. Held-out model-quality
denominator is not applicable because all six historical packets were reference inputs.

**October 30 targeted-coverage clarification:** `packet-agent-v13` exposes a versioned `source-context-v1` map in source discovery and the durable answering handoff, covering document sections, firm/person scope, explicit disclosure summaries versus absence of search results, financial-period limits and historical supplemental-answer pointers. The source map is navigation/policy, never factual evidence. The sponsor's Broward rule resolves Qualified Representative to the designated Primary Representative for printed personalization only; other issuers and conflicting assignments do not gain that default. Checked explicit historical Yes/No firm-description/capability answers may be prefilled with historical warnings, but unchecked boxes, financial/disclosure/personal-act reuse and unverified relationships remain excluded. Long text fields can use readable, cross-referenced supplements instead of being silently stranded by a one-line region. Focused failing regressions preceded these changes.

Historical disclosure continuity needs prior/current event-baseline comparison, not a blanket copy of No or automatic reclassification of a disclosed event. The sponsor's interpretation is recorded in scope and source guidance; a machine-verified event-comparison contract is not yet implemented. Interactive reviewer fields/signing compatibility remain a separate usability increment; current output stays unsigned and personal acknowledgments remain blank.

**Targeted-coverage acceptance measured:** run `ed3767401ff445b58f83971efbda6f3c` collected 80 checked historical candidates. One malformed citation span required an explicit recovery that reused 12 saved groups and regenerated only the unfinished group; the Blob result published 31/68 written requirements. The final audit exposed an overly strict historical gate requiring every contextual quote to repeat the proposed value. After a failing regression and surgical correction, deterministic `answer-gate-v7` / `reviewed-draft-overlay-v7` revalidation of the exact saved proposals produced a local [66-page corrected draft](../outputs/broward-agent-20261030/attempt-17-revalidated/packet.pdf) and [field audit](../outputs/broward-agent-20261030/attempt-17-revalidated/field-audit.json) with **32/68 written**, up from 28/68, retaining every previously populated requirement. No additional inference was used for this correction; the immutable 31/68 cloud result is unchanged.

New draft content covers the backup title, historical references, Florida-office presence and printed primary/qualified-representative name. The title in the execution block is still incomplete and reference qualification remains unconfirmed; written-field counts must not be reported as complete requirement satisfaction. Remaining gaps include four unsupported historical-choice paths, unsuccessful current disclosure-evidence verification, primary-title/account-opening extraction and two withheld attachment answers. Disclosure-event comparison and digital review fields remain unimplemented. All nine form/supplement renders were inspected, outside-region changed pixels are zero, appended evidence page-content streams match the originals and historical/internal archives remain excluded. Final offline checks: **922 passed, five skipped** on both supported runtimes, Ruff lint/format, strict mypy and diff checks passed. Full-coverage acceptance remains open.

**October 30 completion-workflow correction:** the sponsor approved code-controlled requirement groups, durable proposal/validation diagnostics and targeted recovery. `packet-agent-v12` / `answer-groups-v1` now keep model-driven evidence discovery, then stop that tool loop at a saved evidence handoff. Code assigns at most five non-signing requirements per structured answer request, requires exact group coverage, and records immutable request/response checkpoints before advancing. Staged groups are not evidence approvals; the combined gate/writer still decides what can be written. Each execution attempts unfinished groups once; explicit local or Blob recovery rechecks inputs/configuration and reuses successful groups, with at most three attempts per group and a cumulative 30-call group ceiling. Discovery has a separate conservative 30-call allowance, preserving the existing 85-call total including mapping/images. Answer calls have a 180-second ceiling and at most 8,192 output tokens. Recovery does not repeat discovery or OCR/image model calls. Old failed runs without a saved handoff cannot be recovered retroactively. Real coverage, rendering and remaining-blank acceptance must still be measured independently.

**October 30 measured grouped result:** the second recovery of run `20a132a2955840049b10e11c098cce93` published a [75-page incomplete Broward packet](../outputs/broward-agent-20261030/attempt-16-r2/packet.pdf), separate [reviewer summary](../outputs/broward-agent-20261030/attempt-16-r2/reviewer-summary.txt) and private [field audit](../outputs/broward-agent-20261030/attempt-16-r2/field-audit.json). Coverage increased from **6/68 to 28/68 requirements**, comprising two current-evidence answers and 26 historical-continuity-unconfirmed prefills. All 13 groups completed; only three of 31 proposed answers were prevented from writing (two gate-withheld attachment answers and one readable-font fit failure). Most remaining blanks arise before writing: 31 model-reported evidence gaps, one unsupported historical-choice path, four signing deferrals and one unresolved signer. Do not interpret those evidence-gap labels as an independent absence check. Broad/near-complete questionnaire acceptance remains unmet.

The original grouped execution and first recovery were operator-stopped and archived as failed. Durable responses exposed a specific wire-contract defect: proposed answers had null confidence, allowed by the old JSON schema but rejected by local semantic validation. Outcome-specific response branches now require numeric confidence and citations for proposals; supplying the strict schema as a mapping preserves raw responses before SDK-side parsing can hide them. Three consecutive technical failures stop execution. The successful recovery repeated no evidence/mapping/image model calls. Initial Blob publication failed with `ServiceResponseError`; an immutable publication-only replay succeeded with no further inference, followed by hash-verified download. Form/supplement renders were inspected, outside-allowed-region changed pixels are zero, signing fields remain blank and historical originals/private diagnostics remain outside the packet.

Next completion work should target referenced historical supplements and missing checked title associations, evaluate eligible historical boolean/choice support, and correct the observed attachment/fit failures. Preserve current financial-period, disclosure and personal-act exclusions; avoid another unchanged full run or treating every abstention as missing business input. Deterministic validation is **909 passed, five skipped** on both Python 3.12 and 3.13, with Ruff lint/format, strict mypy and diff checks passing. These tests are regression evidence, not held-out answer-quality or zero-hallucination acceptance.

**October 29 priority clarification (supersedes hosted-first PoC sequencing below):** the immediate working PoC may execute locally using the authorized developer identity, with external Foundry inference and Azure Blob inputs/results. A deployed agent identity and Copilot publication are future deployment acceptance, not blockers to demonstrating the PoC. The ultimate workstation-independent Foundry/Copilot architecture remains the target. Prioritize a substantial real-document application-run attempt over additional tiny synthetic demonstrations; keep focused offline tests as regression safeguards.

**October 29 historical-evidence policy update:** the sponsor approved consulting explicitly permitted prior packets as historical business evidence during discovery, not just as wording references after answering. Eligible context-matched answers may be prefilled in incomplete drafts when continuity is unconfirmed, with prominent historical status/provenance and confirmation needs in the separate reviewer summary. Current contradictions leave the affected answer unresolved; financial periods, disclosure-scope review, personal-act/signing prohibitions and evaluation isolation remain mandatory. This supersedes wording-only sequencing below. **Bounded runtime historical prefill is now implemented** in agent v6/gate v5/writer v5; existing packets/runs do not gain historical support retroactively. Real coverage acceptance is recorded separately from offline contract tests below.

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
| [Completed packets](../bd_agreements/Completed/) | Explicit approved historical-business-evidence partition for draft proposals, with continuity status and provenance; separate held-out evaluation partition. Never automatic current confirmation or held-out answer input |

Use repository-relative paths for checked-in development data, resolved from an explicit repository/data root rather than the caller's working directory. Preserve source inputs unchanged. Local developer outputs belong in a separate configured, Git-ignored location. In the deployed application, use configured, access-controlled storage and allowed destinations; never assume the deployed agent can read a developer workstation or repository checkout. Maintain dataset partitions so completed holdout packets cannot leak into answering inputs.

Offline unit and synthetic integration tests remain required. Live model tests require explicit authorization, approved credentials, and appropriate data handling. The technical sponsor authorized staging designated real supporting documents and the selected Broward blank in Blob and sending relevant text/page images to the configured Foundry model on October 29. For the historical-evidence slice, the sponsor additionally approved both Broward 2025/2026 prior packets as historical inputs, including private Blob staging and relevant Foundry text/page images. Other completed packets, held-out answers/derivatives and restricted financial-reporting sources remain excluded. Both Broward packets are therefore answering inputs, not independent evaluation answers. Production private networking, business-source connectivity, durable storage, notifications, signing integration, hosted operation and Copilot publication remain separate future gates.

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
- Historical discrepancies are review flags, not ground truth. Eligible historical prefills require applicable issuer/question/period/role context and explicit continuity status; unknown/incompatible context remains unresolved. Identical answers are not an accuracy pass. Test evaluation text exclusion and duplicate-content leakage independently of model quality.

### Next local PoC slice - Historical business evidence

Implementation status: the existing partition manifest now gates the historical discovery family; immutable Blob/run inputs retain issuer and historical approval metadata. Typed historical context and current-source checks flow through the gate, writer, private archive and prominent reviewer-summary flags. Historical originals cannot be submission attachments. Eligible native text/identifier/narrative and machine-cross-checked scalar OCR reuse are supported. The new `read_historical_page` tool connects whole-page OCR and the blind image reader for mixed native/image completed forms, including verbatim scanned narratives. It validates question/role OCR, answer text and local geometry, retaining hash-bound receipts and per-field failures in private artifacts. Oversized image boxes cannot substitute for local text geometry. The live full-questionnaire profile now shares 20 OCR/image-page allowances between historical and current sources; expanded blind output is capped at 16,384 tokens without retries. Historical financial/disclosure/personal-act reuse and current-period reference qualification remain excluded. Exact provenance and risk guards are deterministic; semantic applicability/continuity are not proven by code or model category labels. Offline contracts include end-to-end rendering and independent writer rechecks, missing/forged receipts, artifact mutation, repeated roles/cross-section swaps, partial-word answers, OCR-only answers, budget exhaustion and existing historical business exclusions. Real-run coverage remains a separate acceptance item.

Real verification: the initial historical run (`505abdcfbcdf448da004b9b8129c6100`, request suffix `-8`) exposed repeated cached quote lookups exhausting the 25-page budget. Failing regressions preceded distinct-source/page accounting and role-navigation handling for repeated labels. The corrected run (`e06f8dc37f8d4b038c660ba2fa70eb21`, suffix `-9`) published a 64-page incomplete packet with **4/68 written requirements: two current-evidence answers and two historical-unconfirmed narratives**; a historical reference proposal was withheld for missing placement. There were no currently corroborated historical answers. Download hashes passed; form/supplement and cited-source spot inspection matched the historical wording; render checks reported zero changed pixels outside allowed regions. Offline validation: **855 passed, 5 skipped** on both Python 3.12 and 3.13, Ruff lint/format and strict mypy passed.

**Coverage acceptance remains unmet.** The corrected run is not a net field-count gain over the prior five-answer run. Among 59 missing-evidence outcomes, 25 explanations mention same-page historical question/role context and 16 mention scan/OCR limitations (overlapping, model-reported categories). Native filled values over scanned form backgrounds are not yet a reliable question/role evidence path. Address that mixed-representation context gap before concluding these are business-data gaps, loosening financial/disclosure safeguards or spending on another unchanged full run. Current results verify historical-prefill mechanics, not substantial questionnaire completion or independent model accuracy.

The subsequent mixed-page integration run (`c2fead356fe24d4989ea7aac0d42d205`, request suffix `-10`) returned 29 historical associations. An initial recheck accepted 19 and withheld 10. Rendered-source inspection traced those ten false abstentions to a left-hand section header legitimately covering right-column fields. Failing regressions preceded the whole-row section fix; **29/29 now pass local-geometry/provenance rechecks**, while competing-column and swapped-role tests reject wrong associations. These are associations, not necessarily eligible prefills; historical choices/disclosures remain excluded.

The run failed in the model step after evidence collection, before writing any packet (`model_call_failed` / `ChatClientException`). The 180.08-second interval matches its configured timeout, but the underlying cause was not retained and is not asserted. Safe exception-type/status diagnostics are now retained, without response/document payloads. A new controlled run uses the existing explicit timeout ceiling of 600 seconds. Offline regression validation is **875 passed, 5 skipped** on both Python 3.12 and 3.13, with Ruff lint/format and strict mypy green. Association counts are not useful-coverage acceptance or model accuracy.

The 600-second run (`a716f73b38ed4e8c8fc85f8c0766d031`, request suffix `-11`) published a hash-verified 64-page incomplete packet with **6/68 filled requirements**: two current-evidence answers and four historical-unconfirmed answers. Primary/backup representative names are newly supported by machine-checked question/role/answer associations; the two prior narratives remain flagged. Seven answers were proposed; only the reference narrative failed the final gate for missing placement. The remaining blanks are 57 missing-evidence outcomes, three signing deferrals and one unresolved signer. Form/supplement inspection and zero-outside-region pixel checks passed. All six accepted answers passed an independent final-code gate recheck unchanged.

The run issued 28 associations from five prior pages before the whole-row header fix. Replaying those exact retained blind readings against the unchanged source/OCR snapshots under the corrected rules yields **38 associations**. This replay used no manually supplied mappings or new model answers. It is not a new answering/publication run: the linked packet still contains six answers. The next coverage check should exercise answer generation with the additional associations and address the reference placement gap, not mistake available-but-unconsumed evidence for missing business input or relax financial/disclosure/signing restrictions. Coverage and held-out accuracy acceptance remain unmet.

**Completion-focused correction:** `packet-agent-v9` explicitly requires eligible checked historical prefills even when continuity is unconfirmed, and the evidence-completion handoff reoffers all checked candidates alongside every requirement for a second completion pass. The live/Blob and local CLI paths share an explicit profile of 60 orchestration + five mapping + 20 image readings (85 model calls), 240 agent tool calls, 3,600 seconds, 200 evidence calls, 80 distinct evidence pages, 20 OCR pages and 500,000 returned evidence characters. Effective limits/usage are retained privately. The 25-page/five-image defaults remain for direct developer tool instances. Native anchors now handle question numbers joined to the first word while retaining exact source quotations; small edge overlaps may be trimmed only within the proposed region while retaining at least 90% of its area and passing downstream native-ink checks. Unchanged cached Broward maps now yield 55 placements, versus 50; three placement exceptions remain. These changes do not establish useful output coverage until a new full run is inspected.

The subsequent v9 run (`539ee13ff05f467582a457bdd3433178`, suffix `-13`) retained a second confirmed 600-second `APITimeoutError`/`ReadTimeout`, this time after evidence collection and two accepted answer batches. No packet was produced. Reading used 13 distinct pages, seven OCR pages and five independent historical images, below the expanded limits. `packet-agent-v10` now uses SDK-supported deterministic phase compaction to keep the checked evidence handoff, current quote citations, source metadata, staged/remaining IDs and latest complete tool exchange without replaying all raw reads and prior batches. It does not add model calls or claim that context size is a proven timeout cause. `historical-page-context-v3` additionally handles joined question-number spacing in prior-form captions; direct comparison of the actual OCR/image text reproduced that reference-question failure. Exact numbers/words, answer confidence and gate/writer safeguards remain intact. Full offline validation is **892 passed, 5 skipped** on both Python 3.12 and 3.13, Ruff lint/format and strict mypy passed. Neither these checks nor failed runs establish useful packet completion.

Attempt `-14` (`61284870290c400d84e14930880c9cc9`) collected evidence but entered repeated answer-batch rejections interleaved with successful status calls. It was explicitly failed closed (`repeated_answer_batch_rejections`) without publishing a packet. The exact rejected payload was not retained. Investigation nevertheless reproduced three contract defects: a 500-item advertised schema versus a ten-item runtime limit, rejection feedback lost across status/compaction, and status queries resetting consecutive-error accounting. `packet-agent-v11` fixes those defects with a ten-item typed tool schema, retained validation feedback and non-progress-aware error accounting. A separate failing regression also prevents native anchoring from ignoring an explicitly wrong glued question number. Full deterministic validation is **895 passed, 5 skipped** on both Python 3.12 and 3.13, with Ruff lint/format and strict mypy green; useful-coverage acceptance still requires the real-run result.

Attempt `-15` (`9fd7f6deb9524b158909e6eabdf3e71d`) exercised v11 with context v3. It completed evidence collection, accepted one answer batch, rejected four with `invalid_arguments`, then failed with the retained `ChatClientException -> APITimeoutError -> ReadTimeout -> ReadTimeout` chain. No packet was published; in-memory staging is not recoverable. The downloaded private diagnostics passed hash verification and include 65 historical associations, not an answered-field count. The rejected field details were not archived, so their exact cause remains unresolved. **The latest published packet remains attempt `-11`, 6/68 written requirements; useful-coverage acceptance is still unmet.** Stop unchanged full reruns. The next completion correction should bound answering by small requirement groups and durably retain proposal/validation diagnostics, while preserving evidence, gate and signing rules. A complete remaining-blank audit cannot be claimed for an unpublished run.

Implement before another OCR-only optimization cycle:

1. Use the existing historical partition/access and hash-exclusion machinery to expose only explicitly approved historical inputs. Do not treat every file under Completed as approved, or reclassify holdouts implicitly. Historical documents used in a real run must be explicitly staged/authorized; previous support-only Blob bundles do not include them.
2. Discover relevant prior answers agentically, preserving issuer/question/role and temporal context, rather than building a fixed Broward answer map. Use them alongside current supporting evidence before reporting that business input is absent.
3. Add evidence status/provenance contracts that distinguish currently corroborated, historical-continuity-unconfirmed and unsupported/conflicting proposals. Keep historical records separate from current factual authority. Record inspected corroboration/contradictions and unknown dates explicitly.
4. Wire those statuses through tools, gate, writer, private run archive and reviewer summary. Permit eligible historical prefills without falsely setting current-confirmation flags. Keep historical source packets internal, not submission attachments, while retaining applicable current supporting attachments.
5. Add focused regressions for prior role assignments, different issuers/roles, stale contacts/references, current contradictions, period-sensitive financials, changing disclosure scope, non-reusable personal acknowledgments/signatures and evaluation leakage. Existing discrepancy-only history checks are not sufficient acceptance for prefill.
6. Exercise a substantial real questionnaire against approved historical and current sources. Report how many answers were newly supported by history, how many were currently corroborated, how many need continuity confirmation, and which remaining gaps genuinely need business input. Do not claim held-out accuracy using the historical input answers.

Acceptance is useful historically grounded draft coverage with explicit reviewer uncertainty, not a fully confirmed packet fabricated from precedent. The [scope's historical policy](../Broker-Dealer%20Packet%20Automation%20Phase%201%20Scoping%20Document.md#6-source-documents-and-version-selection) governs exclusions.

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

**Slice 6 status (implemented; live synthetic run succeeded).** [live.py](../src/bd_packet_builder/live.py) adds `FoundryPageMapper` (one visual-mapping call per blank page, reusing the existing mapping prompt and request limits; at most 5 pages for now), `build_live_client` (Agent Framework `OpenAIChatClient` over the Foundry endpoint with Azure CLI sign-in, 60 s timeout, no automatic retries), `prepare_live_run`/`run_live`, and the `bd-packet agent-run` command (requires `--allow-paid`; run store under `outputs/agent-runs/`). At that stage the cap was 35 agent turns plus at most five page-mapping calls, with `store=False` for model requests; the scanned-evidence increment below reserves five more calls by lowering orchestration to 30. Findings from live runs against `gpt-6.1-sol` with a fictional one-page form and one fictional evidence PDF (kept outside the repository):
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

**Next triage:** real native-text comparison identified model paraphrases/context additions as a major anchor failure. `visual-map-v4` preserves exact issuer labels and separates untrusted section/role guidance in `navigation_context`; native verification is not relaxed. All five real pages now produce 68 interpreted requirements and 50 accepted response placements, versus seven with v3. Three native-anchor failures remain, plus four printed-text overlaps, one missing writable region and one unsupported standalone boolean control. The writer supports grounded textual booleans only in sufficiently wide horizontal blank regions; square/small standalone attestation boxes remain withheld. `answer-gate-v2` and `packet-agent-v2` retain independently selected, hash-verified supporting PDFs even when no citing answer is writable, with an explicit internal warning that inclusion does not establish compliance or period sufficiency. Placement counts are not answered-field counts or grounding-quality results. See the [triage record](../README.md#mapping-triage-and-resumable-page-maps) for the corresponding real workflow result.

**Attempt 5 verification:** run `1a469e44591d4d85bf2ca63c14492875` retained all five selected PDFs (73 supporting pages) in a 78-page incomplete packet. Three answers were written, unchanged from attempt 4; 65 of 68 interpreted requirements remain blank. The model identified important firm facts as OCR-only and therefore uncitable under the existing native-only rule; role designations, acknowledgments and disclosures also remain unresolved. Prioritize a verified scanned-source evidence path, preserving missing-fact and personal-act safeguards, rather than expecting geometry improvements alone to increase answers. Initial Blob publication failed with `ServiceResponseError`; resuming only publication from the immutable local run succeeded with smaller chunks and a longer bounded transport timeout, without new model calls. Downloaded hashes and render-difference checks passed; pages 1, 4 and 5 were inspected. No exhaustive semantic-accuracy claim is made. Regression validation: 806 passed, 5 skipped on both Python 3.12 and 3.13; Ruff and strict mypy passed.

**Scanned-evidence increment (machine-cross-checked drafts explicitly approved):** [scan.py](../src/bd_packet_builder/scan.py) adds a bounded blind Foundry page-image reading, which receives no OCR text, candidate quote, proposed answer or expected subject. Code compares OCR word spans against the independently returned text/record subject, requires at least 90 OCR confidence for quote and subject words, retains source/page/render hashes, and checks requested/claimed periods. Runtime-issued check receipts can support text/identifier draft answers only; scanned narratives, choices, attestations, personal-act inference and signer-role answers remain blocked. The answer gate and writer revalidate the evidence without setting human visual-approval flags. A catalog/filename versus printed-period discrepancy is reported internally. This is transcription agreement, not semantic proof or a zero-hallucination guarantee; business review remains mandatory. The prior human-reviewed OCR path remains intact.

The original scan increment used **30 orchestration + up to five mapping + up to five independent scan readings = 40 model calls**, with no automatic retries. The later completion-focused correction above supersedes this profile with an explicit 85-call ceiling and a larger bounded evidence allowance. Repeated quotes on an already transcribed exact source/page/render reuse the in-memory reading, not a cross-run approval cache. The existing approved Foundry deployment/local Tesseract are reused; no dependencies, Azure resources or deployment changes are needed. Internal receipts, OCR snapshots and content-free tool traces are retained separately from the packet. Attempt 6 exposed a subject-capitalization lookup bug and uncitable-attachment omission (three answers, zero successful scan checks); both have targeted fixes and the failed result is retained. See [scanned-evidence usage/results](../README.md#machine-cross-checked-scanned-evidence).

**Attempt 7 real verification:** run `b68bf0214d3443038ba658888f7aacc7` published a 64-page incomplete packet with five written answers and 63 of 68 interpreted requirements blank. One written answer, firm CRD, uses independently cross-checked scanned evidence; instrument specialization is an additional native-evidence narrative. Of four scan-quote tool attempts, one passed, one failed OCR-confidence checks and two returned unreadable-page abstentions; these are tool outcomes, not held-out answer-accuracy metrics. Four relevant supporting PDFs are appended (58 evidence pages), including partial FOCUS/FINRA candidates with explicit adequacy/period exceptions, plus five form pages and one supplemental-answer page. Downloaded hashes and render-difference checks passed. Form pages 1, 2, 4 and 5, the supplement, and the accepted scanned source were inspected; the one promoted scanned value matched its source image (one case only). Signatures/dates/checklist marks were untouched. Do not equate this narrow success with satisfactory overall packet coverage, exhaustive narrative grounding or business approval. Remaining blockers include FOCUS scan readability/confidence and genuinely unestablished representative roles, acknowledgments and disclosures.

Scanned-evidence regression validation: **831 passed, 5 skipped** on Python 3.12 and 3.13; Ruff lint/format and strict mypy passed. Public call-site compatibility was checked with Pylance; the new scan module has no Pylance diagnostics. No dependency or cloud deployment changes were made.

**Slice 7 status (implemented; hosted acceptance blocked on agent permissions).** [blob_storage.py](../src/bd_packet_builder/blob_storage.py) stages approved originals with immutable hash/size manifests, verifies downloaded bytes, rejects duplicate request execution, and separates packet from internal-review publication. [hosted.py](../src/bd_packet_builder/hosted.py) implements strict build/status commands over Responses and managed-identity model/storage clients. The local HTTP/Blob synthetic run `synthetic-host-smoke-20261028-1` wrote legal name, leading-zero CRD and telephone, left EIN/signatures/date blank, and retained readable artifacts under `outputs/hosted-smoke/`. This proves local HTTP orchestration and Azure data access, not cloud-hosted completion.

The `bd-packet-builder` code deployment reached `active` in the existing project (final tested deployment: version 3). The hosted build fails reading the input manifest with HTTP 403; the instance identity (`9b23162c-2c31-4880-8562-2c5b94eae6bb`) has no assigned storage roles. The developer's new Storage Blob Data Contributor role successfully permits staging and downloading, but does not transfer to that identity. An administrator must grant the container-scoped input/output roles and model access listed in the [README](../README.md#blob-staging-and-foundry-hosting-slice-7). Do not close G6 or call slice 7 complete until an actual hosted packet run is verified.

Runtime safeguards found during integration: custom `SupportsAgentRun` hosting requires agent-owned history and outer `store:true`; inner model calls still use `store=False`. SDK-managed telemetry export must be disabled explicitly, since the beta server otherwise enables content capture despite `OTEL_SDK_DISABLED`. Unexpected execution failures are marked failed before publishing available diagnostics, without suppressing the original error. The current live budget reserves five mapping and five scan calls by allowing at most 30 orchestration turns, keeping the total at 40 rather than adding hidden calls to the cap. Crash resume, production retention and per-requester ACLs are not implemented. Automated evaluation generation was explicitly deferred; offline tests are not model-quality evaluation.

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
