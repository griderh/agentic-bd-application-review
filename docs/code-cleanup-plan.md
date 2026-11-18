# Behavior-preserving code cleanup

Status: Slices 1-5 complete and offline verified. Last updated: November 17, 2026.
This is a completed initiative, not an instruction to repeat the slices.

Parent and detailed historical evidence: [Phase 1 roadmap](development-plan.md).
Separate behavior change: [native-first extraction plan](native-first-extraction-plan.md).

## Reviewer dashboard

- [x] Baseline: establish observable contracts and protect pending work and confidential inputs.
- [x] Slice 1: separate pure reviewer-summary formatting from document mutation/publication.
- [x] Slice 2: separate evidence orchestration and repeated handoff/artifact construction.
- [x] Slice 3: decompose writer preparation, section building, supplemental rendering and merging.
- [x] Slice 4: consolidate identical CLI date parsing and command-error labels; improve documentation.
- [x] Slice 5: isolate final additional-form and supplemental-output verification.
- [x] Record offline verification and boundaries in the roadmap.

**Next action:** none for these five cleanup slices. Subsequent extraction fixes and
live-validation work belong to their own plans; do not reopen cleanup implicitly.

## Objective and preserved behavior

Make the bounded workflow easier to understand, change and test through coherent responsibilities
and removal of proven duplication. This was not a rewrite, a business-rule simplification, a
model-quality exercise or a promise to reduce total source lines.

Preserve answer/evidence decisions, exact source/hash checks, signatures/dates left to humans,
PDF placement, attachment order, page limits, failure behavior, atomic publication, saved-run
recovery and confidential reviewer-summary separation.

No speculative dead-code deletion: static references alone do not prove a helper is unused.
Dynamic tool/CLI registration and supported historical replay remain part of that judgment.

## Completed slices and evidence

### Slice 1: reviewer-summary formatting

- [x] Separate formatting from PDF mutation, source reading and publication.
- [x] Preserve wording, section order, warnings and separate internal-only output.

### Slice 2: evidence orchestration

- [x] Separate coverage validation, selection collection and artifact/handoff construction.
- [x] Preserve serialization, checkpoint timing, explicit errors and restart behavior.

### Slice 3: writer assembly

- [x] Extract four typed private helpers in the existing writer module.
- [x] Reduce the coordinator from 998 to 878 lines without changing business rules.
- [x] Preserve three synthetic packet/manifest fingerprints and pre-extraction writer AST
  equivalence after mechanically inlining helpers.
- [x] Full offline suites at completion: 1,811 passed, 67 skipped per Python target.

### Slice 4: bounded maintenance

- [x] Reuse identical strict-date parsing and command-error labeling; retain agent date semantics.
- [x] Preserve all 19 CLI help outputs and equivalent CLI AST.
- [x] Promote setup/validation and navigation in the README; correct the contributor overview.
- [x] Full offline suites at completion: 1,883 passed, 69 skipped per Python target.

No private helper was proven obsolete, so this slice did not delete one speculatively.

### Slice 5: final writer verification

- [x] Extract additional-form render checks and supplemental text/evidence verification.
- [x] Preserve staging/check order, source rechecks, cleanup, previews and atomic rename.
- [x] Reduce the publication callback from 97 to 38 lines.
- [x] Run 92 writer tests before and after, including five new characterization cases.
- [x] Preserve all 38 artifact fingerprints across five synthetic scenarios, excluding only
  manifest creation timestamps; inlined helpers reproduce the pre-extraction writer AST.
- [x] Full offline suites at completion: 1,888 passed, 69 skipped per Python target;
  Ruff lint/format, strict mypy and whitespace checks passed.

These are historical per-slice results, not fresh test runs for this documentation change.
Later behavior fixes intentionally change some artifacts and component versions; the old
equivalence claims describe their original cleanup baselines, not all subsequent development.

## Live-validation boundary

The user reported a successful fresh run after Slice 4. A subsequent post-Slice-5 run exposed
a schema-invalid scan transcription; that separate behavior fix and its reviewer reporting
are recorded in the roadmap. Native-first extraction addresses a separate completeness gap.
Do not label those failures cleanup acceptance successes or count approved historical inputs
as independent held-out model-quality evaluation.
