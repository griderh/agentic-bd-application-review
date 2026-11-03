# agentic-bd-application-review
This agentic AI application reviews broker-dealer application requirements and constructs the application using supporting documentation such that it can be reviewed and submitted by signatories

## Project documentation

- [Phase 1 scoping document](Broker-Dealer%20Packet%20Automation%20Phase%201%20Scoping%20Document.md): business requirements, boundaries, and evaluation criteria.
- [Development plan](docs/development-plan.md): milestones, dependencies, acceptance criteria, and open implementation decisions.
- [Copilot coding instructions](.github/copilot-instructions.md): repository-wide Python, test-driven development (TDD), grounding, and data-handling standards.

## Development status

### Saved-run coverage repair (agent v25)

The v24 paid run exposed extraction/reference failures that the earlier prompt-policy tests
did not establish were fixed. Control localization now tolerates padded model hints while
requiring actual bounded outlines or a connected two-arm checkmark; ambiguous neighboring
controls still fail. Check-arm proportions use the observed mark, not surrounding whitespace.
Digit-only historical readings can reconcile an image misread only when exact native text
in the same answer region agrees with local OCR at confidence 90 or higher. Original readings
remain in the internal summary; low-confidence OCR and native/OCR disagreement remain unresolved.
A copied OCR render hash resolves only to one complete checked handoff receipt with every other
field, artifact identity and word span unchanged. Arbitrary hashes/text are not repaired.

A separate saved-evidence reconstruction passes the production gate and independent writer:
**45 populated of 69 requirements**, versus 40 in the v24 run. It restores eligibility,
all ten instrument selections and the linked Other write-in, discount-window selections,
employee discipline and primary representative CRD. No populated answer from either the
40-answer v24 or 42-answer v21 run is lost. Rendered affected pages were inspected;
zero pixels change outside allowed regions. **14 unresolved, 7 human-action and 3 conditional
not-applicable requirements remain.** Historical continuity and eligibility-proof gaps still
require reviewer attention. Original runs and source documents remain unchanged.

This is **local reconstruction from saved model readings**, not a new autonomous model run or
proof that live coverage is fixed. No paid calls were made. Full offline validation:
**1,278 passed, 33 skipped on each of Python 3.12 and 3.13**; Ruff lint/format, strict mypy for
both targets and whitespace checks passed. Provenance is agent v25, historical context v7,
answer groups v3 and checked-citation resolution v2; domain knowledge remains v2. Any separately
authorized paid test must start a fresh v25 run after restarting long-running processes,
not resume the old run.

### Applied institutional knowledge (agent v24)

**Historical-confirmation conflict cleanup:** domain knowledge v2 separates verification of
what a prior source said from confirmation that it remains true. Current reading is attempted
within budget to find corroboration/contradictions, but is not a prerequisite for an otherwise
eligible checked historical draft under `answer_first_review`. `current_checks=[]` is valid;
unread current pages, missing corroboration and technical current-verification failures are
review gaps, not contradictory evidence. The stale blanket exclusion of historical eligibility
and disclosure booleans has been removed. Conservative-mode restrictions, actual contradictions,
substantive historical-reading disputes, financial periods and personal-act safeguards remain.
Grouped condition assessments and native proposal instructions use the same distinction.

Validation after this cleanup: **1,264 passed, 33 skipped on each of Python 3.12 and 3.13**;
Ruff lint/format and strict mypy for both targets passed. Behavioral tests cover eligibility
with no current inspection, noncorroborating checks and contradictions, and historical booleans
under both reuse policies. Four further opt-in reasoning cases cover unread/failed current
checks, an explicit prior negative disclosure and a substantive historical-reading conflict;
**0/4 executed**, no paid calls. The subsequent v24 live run exposed the failures described above.

The shared runtime reference is
[`domain_knowledge.json`](src/bd_packet_builder/domain_knowledge.json), not the Copilot coding
instructions. Nine bounded entries consolidate document-reading guidance, historical reuse,
eligibility, financial periods, tenure/headcount, supporting materials and scoped sponsor rules.
Each has a stable ID, authority, applicability, guidance and limitations. Discovery, grouped
answering and native proposals receive the same reference; the source catalog remains navigation
metadata. Overlapping business-rule prompt blocks have been removed.

Checked applicable historical eligibility supports a flagged `answer_first_review` draft without
fresh certification of every condition. Current contradictions still block. BrokerCheck guidance
separates status dates from continuous operations: a single Approved entry is **not** treated as
proof of uninterrupted registration or operation.

Answers report `knowledge_applied` entry IDs, reasons and the reference hash alongside their
ordinary citations. Unknown IDs, duplicates and stale hashes are rejected. The internal audit
and summary label this **model-reported application**, not verified reasoning or source evidence.
These notes do not enter the packet. Legacy proposals with no annotations say none reported.
The run records version/hash and a reference snapshot at evidence handoff; recovery rejects a
different reference even if its version label was not changed. Changed agent/reference versions
require a fresh run rather than resuming an incompatible old run.

To maintain this reference, edit the existing entry or add a narrowly scoped entry with authority,
applicability and explicit limits; bump its version for interpretation changes. Never add
confidential source facts, unverified internet assertions as approved facts, or automatically
promote chat/model output into knowledge. Add focused behavioral tests and relevant synthetic
reasoning evaluations before changing an interpretation.

Validation: **1,255 passed, 29 skipped on each of Python 3.12 and 3.13**; Ruff lint/format and
strict mypy for both targets passed. The built wheel independently loads all nine packaged
entries. Gate/writer tests retain the supported historical eligibility selection, reject actual
contradictions, and preserve the original evidence checks. Four new opt-in synthetic knowledge
reasoning cases were added; **0/4 executed** (paid calls not authorized). This is not a new
autonomous form run or proof of improved live-model coverage.

**October 30 requirement/checklist reconciliation:** gate/writer v12 support reviewed,
version-bound applicability and criterion-level coverage. These are trusted local review inputs
(`DraftReview.requirement_assessments`), not model-granted exemptions or authenticated approval.
Criteria quote the issuer form; native/OCR citations are rechecked against approved source versions.
Included evidence, satisfied criteria, period discrepancies, missing coverage, human actions and
unavailable checklist placement are distinct. A checklist is marked only when all reviewed criteria,
actual packet inclusion and required-item dependencies pass, with a validated label/control mapping.
Default discovery still leaves attachment placement unmapped; criteria are not autonomously inferred.

**Earlier reviewed known-form result:** **49 populated, 4 conditional/not applicable, 1 reviewed
not applicable (FIT), 1 optional/not supplied (Other), 1 evidence/checklist satisfied,
7 human-action and 5 unresolved requirements out of 68**. All 49 prior answers are unchanged.
FIT and Other are sponsor-reviewed applicability corrections, not additional filled answers.
The FINRA/Florida-registration checklist is now checked against the attached registration pages.
The historical electronic-access write-in remains an internal operational limitation, never initials
or current named-user confirmation. References already appear inline; no duplicate attachment is
required absent issuer wording, but current qualification/recency remains a review concern.

The five unresolved items now have specific actions: establish all eligibility conditions,
confirm the latest FOCUS reporting period, reconcile disclosure coverage/legal baseline,
complete the remaining required questionnaire items and confirm reference eligibility.
The reviewer summary records a printed financial-period/catalog discrepancy rather than treating
an execution date as the reporting period. Signatures and other personal acts remain human actions.

Validation: **1,045 passed, five skipped on each of Python 3.12 and 3.13**; Ruff lint/format,
strict mypy and diff checks passed. The 70-page packet changes only the checklist on form page 5;
all 49 previous answer records, six supplement content streams and 59 evidence content streams
are unchanged. Outside-region changed pixels are zero; the marked checklist was visually inspected.
This is a reviewed known-form replay using local OCR and cached evidence, with no new paid model
calls, services or dependencies. It is not a new autonomous full-run or held-out accuracy result.

### Previous discrepancy-tolerant increment

**Bounded historical-eligibility repair (agent v22):** local control inspection also recognizes
a connected, two-arm checkmark when a printed outline cannot be resolved. Slashes, crosses,
dots and empty regions do not qualify. OCR/image control-label reconciliation retains all
option words and permits only localized single-character mark/bullet-margin artifacts; changed
wording, numbers or substantive conditions remain disputed. Original readings remain auditable.
Under `answer_first_review`, an applicable checked historical eligibility selection is sufficient
for a conspicuously flagged draft; missing current confirmation of individual conditions goes
to the reviewer, not an automatic blank. Contradictions and incompatible conditions still block.

Supporting pages with sparse native text and extensive vector outlines now use the existing
bounded local OCR path, instead of treating footer-only text as a successful body read.
OCR candidates remain unverified until the ordinary independent evidence checks pass.
No new knowledge subsystem or dependency was added.

**October 30 discrepancy-tolerant completion increment:** `packet-agent-v17`,
`scan-cross-check-v4`, historical context v5 and gate/writer v11 allow localized historical
candidates under `answer_first_review` despite OCR confidence/transcription or local mark
inspection disagreements. Real OCR quotes remain unchanged; image readings, discrepancies
and selection rationale appear in the internal summary and per-answer audit. Conservative
policy still rejects those candidates. Invalid source/role/relationship geometry, contradictions,
explicit period mismatches and personal acts remain protected.

Control extraction supports circular outlines and labels on either side of a mark, including
historical Yes/No underlines. Duplicate option labels use the governing question and source/target
column positions; a write-in must belong to its selected control on the same row/source/page.
Publication independently rechecks source artifacts and the full selected group.

**Historical choice/write-in repair (agent v21, scan/context v6):** each control now carries
its printed label separately from its entered write-in, with linked, checked citations in the
answer handoff. Adjacent native PDF text can recover a missing write-in; a merged OCR
label/write-in token is separated only when its exact label prefix and native-text
geometry agree. Original OCR/image readings remain auditable. This is layout-based, not
specific to an issuer, instrument or entered value. Explicit extracted write-ins also support
other option wording, columns and wrapped text. Unresolved readings are not guessed.
The entire question remains blank if any known selection or mandatory write-in fails
verification; partial checkbox groups are never published. Gate and writer both recheck.
Previous run artifacts are unchanged; use a fresh, explicitly authorized run for v21.
The separate Q1 missing-page discovery limitation is not addressed by this repair.

**Follow-up correction:** the first v21 live run supplied the complete Q2 answer, but also
listed the write-in receipt in `historical_basis.additional_contexts`. This exposed a contract
mismatch: that field previously only supported composed text, so the gate rejected the valid
choice answer. Choice answers now permit additional contexts only when they identify the
same write-in receipts independently validated by the complete-choice verifier. Unrelated or
unsupported contexts still withhold the entire question. Regression tests exercise both forms
through the gate and PDF writer. An offline replay of the exact saved live proposal confirms
Q2 is written; this does not repair Q1's unresolved control reading or certify live-model quality.

Explicit same-page "If yes, please explain" follow-ups are reconciled against the immediately
preceding Yes/No answer **actually written**, not an unaccepted proposal or stale explanation.
A historical No makes its explanation not applicable only on that historical-candidate basis.
This intentionally narrow rule does not infer arbitrary conditional dependencies.

**Measured known-form result:** the 70-page local draft has **49/68 populated** requirements
(10 new), **4 conditional/not applicable**, **7 requiring human action**, and **8 unresolved**.
All 39 previous populated requirements remain: 38 proposals are unchanged, and the instruments
answer now includes its selected Other write-in. New answers include historical tenure/headcount
(unchanged, explicitly not current measurements), primary title, primary/backup trading choices,
eligibility, net-capital response and account-opening requirements.

Remaining unresolved items are FIT choices, the empty Other-platform line, current eligibility
proof and five attachment/checklist requirements. The summary distinguishes included evidence,
unvalidated checklist placement and unmet current coverage; those are not all missing facts.
Personal acknowledgments, signatures/dates and the signed-authorization requirement remain human
actions. The four not-applicable items are not newly populated answers. This used cached evidence
plus one targeted historical-page reading, with explicit known-form correspondences; it is **not**
an autonomous full-run or held-out accuracy result. No new services or dependencies were added.

Validation: **1,018 passed, five skipped on each of Python 3.12 and 3.13**; Ruff lint/format,
strict mypy on both runtimes and diff checks passed. All five form pages and six supplemental
pages were visually inspected; all six supplements also passed text checks. Outside-region
changed pixels are zero, and all 59 copied evidence page content streams match their originals.

The following paragraphs record the preceding increment and its measured limitations.

**Previous checkbox/answer-first increment:** `packet-agent-v16`, `scan-cross-check-v3`,
`historical-page-context-v5` and gate/writer v10 separate historical extraction from reuse.
Historical page reading now observes selected, unselected and ambiguous graphical controls;
rectangular selections require local outline/interior-pixel verification, independent image
transcription and checked question/option-label geometry. Empty boxes never imply No.
Unresolved circular outlines and OCR disagreements remain explicit extraction issues.
Multi-select publication rechecks every cited selection and the known selected group; an
uncited or omitted known selection cannot be silently accepted. Option subheadings no longer
masquerade as personal role assignments. Legacy receipt hashes remain compatible.

`agent-run` now defaults to `--historical-policy answer_first_review`; pass
`--historical-policy conservative` for the older restriction set. Programmatic
`LiveRunRequest`, persisted `RunRequest` and standalone `DraftRequest` default to conservative
for backward compatibility; set `historical_policy="answer_first_review"` explicitly to opt in.
The trusted run policy survives intake, evidence handoff, grouped answering and publication;
it cannot be selected by an answer proposal. Checked historical disclosure candidates can
be written with prominent current-event/legal-baseline review concerns. Current contradictions,
requested periods, signer authority, new personal acts and signing prohibitions still apply.
Raw control observations and extraction issues remain distinct from verified answer receipts.
Discovery keeps all candidates; review records retain only needed receipts and control groups.

**Measured known-form benchmark:** two approved historical pages yielded 37 observed controls
and 20 verified associations (18 selected-control associations and two text answers).
The local candidate packet is now **39/68 populated**, up from 33/68, retaining every prior
proposal unchanged. New fields cover instruments (partial), discount-window access, Bloomberg
trading and three disclosure responses. The instruments Other/write-in is unresolved.
Eligibility and net-capital selections still fail specific outline/OCR checks, not a proven
lack of evidence. The two changed form pages were visually inspected; outside-region changed
pixels are zero. This is a bounded reference reproduction with explicit known-form
correspondences, not a new autonomous full run or held-out accuracy evaluation. Full coverage
and the earlier 40/68 target remain unmet. The 68-page draft stays local, incomplete and unsigned.
Known-form selected-control reproduction is **17/20** nonsigning, non-personal selections,
with zero false selected marks on the two inspected pages; this is not a held-out quality score.
All 59 copied evidence pages have content streams identical to their originals.
Final offline checks: **996 passed, five skipped on each of Python 3.12 and 3.13**;
Ruff lint/format, strict mypy on both versions, syntax and diff checks passed.

The following paragraphs record the preceding increment and its measured limitations.

**October 30 cross-municipality completion increment:** `packet-agent-v15` adds bounded
`index_source` page previews for each approved document, including source hashes, historical
issuer metadata and explicit warnings for absent native text or page images. Indexes are
untrusted navigation, not document summaries establishing facts or proof of missing evidence;
full-page inspection and exact citations remain required. Collected indexes survive in
`answer_handoff.json`. Historical firm-wide descriptions/capabilities may transfer across
municipalities; issuer-specific assignments, financial periods, disclosures and personal
acts retain their restrictions.

Checked historical **written answer labels** can now map to single-/multi-select options
when the entire answer exactly matches the selected labels. This does not read graphical
checkbox marks, infer selections from unchecked lists, or approve semantic equivalence.
`seed_completion_recovery` rechecks a saved request/review against the same blank and a new
source snapshot, retains explicitly selected verified proposals, and reopens discovery for
unanswered requirements. Grouped answering preserves/replays those proposals rather than
regenerating them. This is separate from resuming failed answer groups on frozen evidence.
Real coverage improvement must be measured independently; the baseline remains 32/68 until
a newly rendered packet demonstrates otherwise.

**Measured result:** local recovery `98f224e87f3244fbb7a0a05312959ff0` produced **33/68**,
retaining all 32 prior proposals unchanged and adding the BOOM Discount Notes choice.
This **fails the proposed 40/68 acceptance target** and is not meaningful broad completion.
The 68-page draft includes Public Funds collateral and a native historical 2025 league table,
not the requested Bloomberg terminal screenshot. Primary-title/account-answer extraction,
graphical choices, disclosure baseline comparison and checklist placement remain unresolved.
Full offline validation: 949 passed, five skipped on Python 3.12 and 3.13; Ruff and strict
mypy passed. These tests are not model accuracy or full-coverage acceptance.

**October 29 priority:** the immediate PoC runs locally with Foundry inference and Blob storage under the developer's authorized credentials. Cloud hosting and Copilot remain the ultimate target, not prerequisites for this demonstration. Real-document quality is now the next acceptance gate; synthetic tests remain regression safeguards, not the main deliverable.

M3 slices 1-6 connect the run store, form interpretation, evidence tools, deterministic answer gate and PDF writer under Microsoft Agent Framework. The application—not an external coding assistant—has completed synthetic workstation runs against Foundry. Slice 7 adds private Blob staging/publication and a Foundry Responses server, deployed as `bd-packet-builder` version 3 (`active`). A local HTTP build using staged Azure Blob inputs produced three supported answers, withheld the unsupported EIN and signature/date, and uploaded a packet plus separate internal summary. The hosted build fails reading Blob inputs with **HTTP 403**; the hosted identity has no assigned storage roles. **Cloud end-to-end completion is not yet verified.** Copilot publication remains slice 8. See the [hosting decision](docs/decisions/0002-agent-hosting-and-copilot-front-door.md) and [M3 backlog](docs/development-plan.md#m3-implementation-backlog-october-28-2026).

Local development means code and tests run on a developer workstation; those processes may call remote Foundry APIs. A locally running application is not the target hosted application. The M3 PoC must run in Foundry without a developer workstation, select a staged blank through the intended Copilot/Teams experience, access only approved evidence, and return a packet plus separate reviewer summary. Direct file/image upload is not supported on the selected Copilot custom-engine path; staged IDs replace that intake assumption. [Blank forms](bd_agreements/Blank/) and [supporting documents](bd_agreements/supporting_data/) are development samples. [Completed packets](bd_agreements/Completed/) remain reference/evaluation material, not current factual authority.

The offline foundation also includes strict requirement/proposal contracts, a manual-input review harness, and a fact-sheet **draft** validator. No fact-sheet approval or authorized production release reader is implemented. Model-generated answers remain unapproved proposals; the new draft writer requires a separate, exact-snapshot local review record.

**Latest agreed direction:** answers will come from supporting-document evidence, with conversational reviewer corrections and exception-only human involvement. A lightweight catalog describes likely document contents and conservative version rules; it is not a human-maintained fact sheet or a whole-drive index. Excel is optional inspection/export. Existing workbook commands remain earlier prototype tools, not the final user workflow. Targeted native-text proposals now exist; approved fact release and chat revisions do not. See the [evidence/revision/archive workflow](docs/evidence-review-workflow.md).

This increment adds explicit historical **reference versus evaluation** partitions and offline, manually supplied discrepancy checks. Historical packets can flag differences or inform wording, never establish current facts. Held-out packets are excluded from the reference reader; copies with identical hashes cannot cross partitions. No real archive was automatically assigned to a split.

Treat business samples and generated outputs as potentially confidential. Do not publish them, copy them into ordinary test fixtures, or upload them to model/OCR services without approved access. Use synthetic or sanitized fixtures for offline development and CI.

## Local setup

The supported Python range is 3.12-3.13; both versions pass the offline suite. Use Python 3.12 for the existing local setup. The hosted Foundry code runtime uses Python 3.13. From the repository root on macOS or Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-build-isolation --no-deps -e .
python -m pip check
```

On Windows, create the environment with `py -3.12 -m venv .venv` and activate it with `.venv\Scripts\Activate.ps1`, then use the same `python -m pip` commands. Windows execution has not yet been validated.

Dependencies, including transitive packages, are pinned in [runtime requirements](requirements.txt) and [development requirements](requirements-dev.txt). Package metadata and tool settings live in [pyproject.toml](pyproject.toml). No uv, Azure credentials, or model access is needed for the offline commands or tests.

## Blob staging and Foundry hosting (slice 7)

The [Blob adapter](src/bd_packet_builder/blob_storage.py) uses original bytes, hashes and immutable bundle manifests, not a vector index. The [hosted entry](src/bd_packet_builder/hosted.py) accepts strict JSON commands containing IDs, never arbitrary paths. It calls the same model-driven workflow as workstation runs. Cloud clients use managed identity through `DefaultAzureCredential`; staging/download commands use your Azure CLI sign-in.

The PoC account is `https://bdpoc3ff06060.blob.core.windows.net`. Containers require Entra data roles; anonymous access and shared keys are disabled. The network endpoint is public, not a private endpoint. On October 29 the sponsor authorized uploading the selected Broward blank and designated supporting documents, and sending relevant text/page images to the configured Foundry model. That approval excludes Completed packets, held-out answers/derivatives, restricted financial-reporting sources and unrelated files; it is not blanket authorization for other destinations.

After local setup and `az login`, stage an approved input root:

```bash
python -m bd_packet_builder.blob_storage \
  --account-url https://bdpoc3ff06060.blob.core.windows.net stage \
  --root /path/to/approved-input-root \
  --blank "bd_agreements/Blank/Synthetic Issuer Questionnaire.pdf" \
  --blank-id synthetic-issuer-v1 --evidence-set-id synthetic-firm-v1
```

The command includes all files from designated supporting-document families under that root, not just the blank. Use a purpose-built synthetic root for development. Completed packets and undesignated families are excluded. Inputs are bounded to 64 MiB per file, 100 evidence files and 512 MiB total. Reuse an ID pair only for identical bytes; changed documents require new IDs.

Run the host locally:

```bash
export BD_BLOB_ACCOUNT_URL=https://bdpoc3ff06060.blob.core.windows.net
export BD_MODEL_ENDPOINT=https://bd-application-builder-resource.openai.azure.com/openai/v1
export AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-6.1-sol
export BD_ALLOW_PAID=1
export OTEL_SDK_DISABLED=true
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false
PYTHONPATH=src python main.py
```

Paid calls are disabled unless `BD_ALLOW_PAID=1`. The full-questionnaire profile permits at most 60 orchestration turns, five blank-page mapping calls and 20 independent evidence-image readings (**85 model calls total**), 240 agent tool calls and 3,600 seconds. Model calls have no automatic retries. Evidence reading is capped at 200 calls, 80 distinct source/pages, 20 OCR pages and 500,000 returned characters. Historical and current evidence share those limits; successful exact-page image readings are cached within the run. `reading_budget.json` records effective limits and usage in private reviewer results. SDK-managed telemetry export is disabled explicitly in the server constructor, not merely through environment variables. Development run files remain under `~/.bd-packet-runs/` or an explicit non-symlink `BD_WORK_ROOT`. Press **F5** for the [VS Code debug configuration](.vscode/launch.json); it defaults to paid calls disabled. Agent Inspector can connect to the running Responses endpoint.

The local server listens on port 8088. `GET /readiness` checks readiness. `POST /responses` accepts an OpenAI Responses envelope with `model: "bd-packet-builder"`, `store: true`, and a JSON command as its `input` string:

```json
{"operation":"build","request_id":"unique-request-1","blank_id":"synthetic-issuer-v1","evidence_set_id":"synthetic-firm-v1","as_of":"2026-09-30"}
```

Use `{"operation":"status","request_id":"unique-request-1"}` to retrieve a published result without calling a model. Outer Responses history contains IDs/result metadata; all inner model calls use `store=False`. The custom-agent hosting adapter currently rejects outer `store:false`. Returned Blob locations are **not download links**. Invalid commands and technical/storage failures are errors, never completed packets.

Deployment uses [azure.yaml](azure.yaml), the existing Foundry project and Python 3.13 remote build. [.agentignore](.agentignore) excludes business documents, generated outputs, credentials, tests and development tooling from the uploaded source archive. Inspect the packaged ZIP before each deployment:

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd package bd-packet-builder \
  --no-prompt --output-path /tmp/bd-packet-hosted-package.zip
unzip -l /tmp/bd-packet-hosted-package.zip
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd deploy bd-packet-builder --no-prompt
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd ai agent show bd-packet-builder --output json
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd ai agent invoke bd-packet-builder \
  '{"operation":"build","request_id":"unique-cloud-request-1","blank_id":"synthetic-issuer-v1","evidence_set_id":"synthetic-firm-v1","as_of":"2026-09-30"}'
```

**Administrator prerequisite:** assign the deployed agent's instance identity, not the developer or blueprint identity:

- Principal/object ID: `9b23162c-2c31-4880-8562-2c5b94eae6bb` (recheck after identity replacement).
- Storage Blob Data Reader on `bdpoc3ff06060/blobServices/default/containers/packet-inputs`.
- Storage Blob Data Contributor on each of `packet-results` and `reviewer-results`.
- Cognitive Services OpenAI User on `bd-application-builder-resource` for the direct Azure OpenAI model endpoint, unless equivalent inference permission is already provided. Model access has not yet been reached in the hosted smoke test.

These are role assignments an administrator can make without granting the developer RG-wide RBAC Administrator. Developer Blob Data Contributor does not transfer to the hosted agent.

For an administrator using Azure CLI, the exact scopes are:

```bash
principal=9b23162c-2c31-4880-8562-2c5b94eae6bb
rg_scope=/subscriptions/3ff06060-623c-40d7-aa0c-df5d9f124e94/resourceGroups/rg-bd-application-builder-dev
storage_scope="$rg_scope/providers/Microsoft.Storage/storageAccounts/bdpoc3ff06060/blobServices/default/containers"
az role assignment create --assignee-object-id "$principal" \
  --assignee-principal-type ServicePrincipal --role "Storage Blob Data Reader" \
  --scope "$storage_scope/packet-inputs"
az role assignment create --assignee-object-id "$principal" \
  --assignee-principal-type ServicePrincipal --role "Storage Blob Data Contributor" \
  --scope "$storage_scope/packet-results"
az role assignment create --assignee-object-id "$principal" \
  --assignee-principal-type ServicePrincipal --role "Storage Blob Data Contributor" \
  --scope "$storage_scope/reviewer-results"
az role assignment create --assignee-object-id "$principal" \
  --assignee-principal-type ServicePrincipal --role "Cognitive Services OpenAI User" \
  --scope "$rg_scope/providers/Microsoft.CognitiveServices/accounts/bd-application-builder-resource"
```

These commands have **not** been executed by the application/developer. Cloud invocation and safe session diagnostics are retained in [cloud-invoke.txt](outputs/hosted-smoke/cloud-invoke.txt) and [cloud-session-log.txt](outputs/hosted-smoke/cloud-session-log.txt). The final smoke test failed before any hosted model calls. Allow role propagation, then retry with a new request ID.

Download a completed or failed run's available artifacts to a new directory:

```bash
python -m bd_packet_builder.blob_storage \
  --account-url https://bdpoc3ff06060.blob.core.windows.net download \
  --request-id unique-request-1 --output outputs/blob-runs/unique-request-1
```

The persisted local-HTTP/Blob test is in [outputs/hosted-smoke/synthetic-host-smoke-20261028-1/](outputs/hosted-smoke/synthetic-host-smoke-20261028-1/), including [packet.pdf](outputs/hosted-smoke/synthetic-host-smoke-20261028-1/packet.pdf), [reviewer-summary.txt](outputs/hosted-smoke/synthetic-host-smoke-20261028-1/reviewer-summary.txt) and [manifest.json](outputs/hosted-smoke/synthetic-host-smoke-20261028-1/manifest.json). It is synthetic and `published/incomplete`, not a cloud-hosted success or a submission-ready packet.

### Authorized real Broward attempt (October 29)

The full five-page `BrokerDealerQuestionnaire.pdf` was staged as `broward-questionnaire-20261029`, with all 11 PDFs from the six designated supporting families as `approved-support-20261029` (about 30.8 MB). This includes multiple financial-report versions and documents not necessarily relevant to the form. No manually authored field map, answer map or historical completed packet was supplied. The separate two-page authorization form was not included in this first case.

The local application backend downloaded and hash-verified those Blob inputs and invoked `gpt-6.1-sol`. Three attempts ended in technical failure before form interpretation completed:

| Request suffix | Mapping request timeout | Mapping output-token cap | Observed failure |
| --- | --- | --- | --- |
| `-1` | 60 s | 4,096 | Model request timed out |
| `-2` | 180 s | 4,096 | Structured response rejected with `json_invalid` |
| `-3` | 180 s | 16,384 | Structured response rejected with `value_error` |

Request prefix: `broward-full-questionnaire-20261029`. Manifests and result records are retained in [outputs/broward-agent-20261029/](outputs/broward-agent-20261029/) and the private reviewer container. **None produced a packet or reached evidence selection/answering.** This is a real-world failure finding, not a successful coverage or grounding evaluation. The second failure does not by itself prove output truncation; the third confirms that a larger output allowance alone does not solve schema validity.

`FoundryConfig.timeout_seconds` now accepts an explicit 1-600 s timeout (default unchanged at 60 s), used consistently by mapping and orchestration clients. Real attempts 2-3 used 180 s. Page mapping explicitly opts into a bounded 16,384-token response allowance; other structured callers retain the 4,096-token guard unless they explicitly opt in. Automatic retries remain disabled and each run retains the existing 40-call total cap. Further diagnostics identify the failed page and validation field paths without echoing model/document values. These changes have **not** been redeployed to Foundry; the immediate path remains local.

Next priority is reliable complete-form interpretation with retained page-level diagnostics, followed by actual evidence/attachment selection and rendered packet inspection. Do not substitute hand-authored Broward mappings or weaken validation to manufacture a successful result.

### Mapping triage and resumable page maps

The next diagnostic run isolated the schema failure on **page 5, items 0-5**: each attachment checklist item incorrectly contained a checkbox option. `VisualItem` permits options only for answer-choice kinds; its validator correctly rejected them. The service returned `completed`, with 1,894 output tokens, so that reproduction was not output-token exhaustion. Prompt `visual-map-v3` explicitly distinguishes attachment-presence checkboxes from answer choices (`kind=attachment`, `region=null`, `options=[]`); the schema and validator were not weakened.

The revised prompt passed the actual failing page and then all five real pages: **69 discovered items**. Deterministic conversion retained 69 interpreted requirements but accepted only **7 placed responses**, with 50 native-anchor placement exceptions and two unsupported standalone boolean controls. Attachments/signatures are not ordinary placed answers, so 7/69 is not an answer-accuracy metric. This is progress past the schema blocker, **not broad form-filling acceptance**. The protected [mapping assessment](outputs/broward-agent-20261029/mapping-triage/mapping-assessment.json) records the remaining exceptions.

Reproduce a selected page, or omit `--page` to resume all pages:

```bash
OTEL_SDK_DISABLED=true python -m bd_packet_builder.mapping_triage \
  --root . --blank bd_agreements/Blank/Broward_County/BrokerDealerQuestionnaire.pdf \
  --output outputs/broward-agent-20261029/mapping-triage \
  --endpoint https://bd-application-builder-resource.openai.azure.com/openai/v1 \
  --deployment gpt-6.1-sol --timeout-seconds 180 --page 5 --allow-paid
```

Diagnostics are opt-in, confidential local artifacts (files created with mode `0600`), never ordinary logs or packet attachments. They retain the raw model response **before** SDK schema parsing, service completion/incomplete details, usage, elapsed time, validation field paths and constraint messages without submitted values. No HTTP authorization headers or credentials are recorded. They may contain issuer text in model outputs; keep them under ignored, access-controlled outputs and apply the same retention/access rules as source documents.

Only schema-valid maps are cached, keyed by blank hash, rendered image, page input, exact prompt/version, schema, endpoint/deployment and output-token allowance. Failures are retained but never cached as successes. A retry reuses successful exact-input pages and calls the model only for uncached pages. Prompt/schema/model/input changes invalidate reuse. Cache validity does not prove correct geometry or grounded answers; native anchoring and placement checks still run. The same cache can be passed explicitly as `BlobPacketBackend(..., mapping_diagnostics_dir=...)` for a local complete-workflow attempt. Default runs do not silently enable raw diagnostics.

**Resumed real run:** `broward-full-questionnaire-20261029-4` / run `d97bb56e8e3d4d2dbed08cc80ff74964` reached `published/incomplete` using those cached maps and the 11-file Blob evidence set. The actual [seven-page packet](outputs/broward-agent-20261029/attempt-4/packet.pdf) and separate [reviewer summary](outputs/broward-agent-20261029/attempt-4/reviewer-summary.txt) are retained locally and in their respective Blob containers. Three requirements were written (firm name, broker/DTC number and question 11's narrative); 66 remained blank. Two one-page attachments were included (public-funds material and delivery instructions); selected FOCUS and FINRA attachments were omitted by the existing attachment gate. This is **not** satisfactory packet coverage or attachment completeness.

Artifact hashes were verified after download. The writer recorded zero changed pixels outside allowed regions; rendered form pages 1, 4 and 5 were inspected locally, including the narrative and untouched signature/date/checklist areas. No synthetic company values were found in the real reviewer summary. These checks do not establish exhaustive evidence grounding, full-field placement quality or business approval. Next work is fixing the native-anchor/placement mismatch and diagnosing required-attachment omissions; do not report all blank answers as genuinely missing source facts.

**Next placement/attachment triage:** actual native text showed that paraphrased labels (for example, adding a section's role to a short printed label) failed the exact-anchor check. Prompt `visual-map-v4` requires issuer wording verbatim and keeps section/role guidance separately in `navigation_context`, which is untrusted model-proposed navigation, not source evidence. It also asks for the blank writing space above an answer line rather than the thin rule itself. On the same five real pages, 68 interpreted requirements now yield **50 accepted response placements**, compared with seven previously; native-anchor exceptions fell from 50 to three. Four regions overlap printed text, one has no writable region, and one standalone boolean control remains unsupported. These are placement counts, not answer-quality metrics or a held-out evaluation.

`answer-gate-v2` retains explicitly selected supporting PDFs even if no answer citing them is writable. Selected IDs must belong to the hash-verified input selection; readable-PDF and publication checks still apply. The internal report explicitly warns that inclusion alone does not establish reporting-period, registration or attestation sufficiency. Other callers retain citation-driven attachment behavior unless they explicitly supply selected IDs. `packet-agent-v2` passes that selection to the gate and exposes navigation context separately from exact requirement quotes.

Standalone boolean answers can be rendered as `Yes`/`No` only in native-anchored, blank text regions with adequate height, width of at least 30 PDF points and a horizontal aspect ratio of at least 2:1. Square/small standalone attestation controls remain unsupported rather than being marked as if they were text lines. Existing yes/no choice groups use their verified choice controls. Evidence, signature and render-difference gates remain unchanged; a missing fact is never converted to `No`.

**Real verification of these changes:** request `broward-full-questionnaire-20261029-5`, run `1a469e44591d4d85bf2ca63c14492875`, produced a [78-page incomplete packet](outputs/broward-agent-20261029/attempt-5/packet.pdf) and separate [reviewer summary](outputs/broward-agent-20261029/attempt-5/reviewer-summary.txt). All five selected supporting PDFs are now retained: FOCUS, FINRA, audited financials, public-funds material and delivery instructions (73 supporting pages plus five form pages). The answer count remains **three**; 65 of the 68 interpreted requirements remain blank. Better placement has not yet improved answer coverage. The model reported scanned/OCR-only evidence for important firm facts; the current native-only citation rule blocks those facts, while representative designations, personal acknowledgments and several disclosures remain genuinely unestablished. Do not equate every blank with absent documentation, or accept OCR text without a verified evidence path.

The initial Blob upload failed with `ServiceResponseError` after the local run completed. Publication alone was resumed from the immutable local artifacts, using smaller upload chunks and a longer bounded read timeout; no model calls were repeated. The resumed result was downloaded and hash-verified. Render checks recorded zero changes outside permitted form regions; pages 1, 4 and 5 were inspected locally, including unmarked signature/date/checklist areas. These are not exhaustive semantic-grounding or business-approval results. Regression validation: **806 passed, 5 skipped** on both Python 3.12 and 3.13; Ruff and strict mypy passed. Next substantial improvement is a verified scanned-source evidence path, not another placement-only run or cloud deployment.

Local PDFium extraction confirmed zero native-text characters across all 32 pages of the selected FOCUS PDF. The 24-page FINRA candidate has 2,513 native-text characters in total; that count does not establish that the specific requested facts are natively citable. Keep those observations separate from the model's OCR-only explanations.

Packet PDFs are stored only in `packet-results`; summaries, original blank, manifests and other internal artifacts go only to `reviewer-results`. A result record is written last; a partial upload has no completed record. Reusing a claimed request ID fails explicitly instead of running or paying twice. Missing records require operator inspection; there is no automatic crash resume, orphan cleanup or cross-requester ACL yet. Downloads may leave partial files on failure; treat them as unusable until the command succeeds and validates hashes. The shared PoC must not be published broadly before slice 8 authorization/result delivery is implemented.

### Historical business evidence and flagged prefills

The October 29 scope update permits explicitly approved prior packets as historical business evidence during discovery. Eligible context-matched answers may be prefilled in incomplete drafts with **historical - continuity unconfirmed** status and prominent provenance/confirmation needs in the separate internal reviewer summary. History does not override current contradictions, applicable financial periods, disclosure-scope checks or prohibitions on carrying forward signatures, signature dates and personal acknowledgments. Historical packets are internal evidence, not automatically submission attachments; evaluation holdouts remain excluded.

`packet-agent-v6`, `answer-gate-v5` and `reviewed-draft-overlay-v5` implement this policy for bounded draft reuse. The source boundary reuses [ArchiveManifest](src/bd_packet_builder/history.py): only explicit `reference` entries are exposed to discovery. Evaluation entries are excluded, their bytes are not staged or read by the runtime, and declared archive/evaluation hashes cannot be copied into current supporting evidence. This does not discover undeclared answer-bearing derivatives automatically.

The agent can search/read the `historical_reference` family alongside current sources without an issuer-specific answer map. Catalog metadata includes the prior issuer and known completion date; unknown dates stay unknown. Historical proposals carry an exact prior-question citation, category/role/applicability context, cited current-source checks and explicit reviewer confirmation needs. The gate and writer independently re-resolve provenance and enforce reuse restrictions. They distinguish `current_evidence`, `currently_corroborated`, `historical_continuity_unconfirmed` and `unsupported`; a missing contradiction is not promoted to corroboration.

Eligible historical text/identifiers/narratives must retain the literal proposed value in the prior answer quote (whitespace differences only are tolerated). Historical scalar OCR retains the existing blind image/transcription receipt path. The historical page-association tool below additionally supports verbatim scanned narratives with checked question/answer/role regions. Historical financial roll-forward, signing/personal-act and disclosure reuse are not enabled. Explicit requested periods require current evidence. Same-issuer/same-role constraints apply to historical representative assignments. Context interpretation and semantic relevance still require human review: exact quotes, category labels and keyword guards are not proof of semantic equivalence, currentness or reference qualification.

For completed forms with image-only labels and native or scanned filled answers, `read_historical_page(source_id, page)` forces whole-page Tesseract OCR and reuses the independent image reader. The blind reader receives only the page image and generic instructions, never candidate values or OCR text. It proposes up to 60 question/answer/role regions; code cross-checks each locally. Label/role text must match OCR with every selected word at least 90 confidence. Native answers require whole-word text and PDF character geometry; scanned answers require exact OCR/image text agreement. Code checks proximity, intervening questions and role sections using local geometry as well as the image-proposed boxes, so an oversized box cannot hide a cross-role answer swap. Uncertain fields are returned as explicit per-field issues without discarding other supported associations.

The tool returns an `answer_citation` and receipt-bound `context_citation`. The agent uses the former for the answer and the latter for `historical_basis.prior_question`; it does not manufacture citations for image-only labels. Gate and writer independently recheck source/artifact/render hashes, quoted text and geometry. Receipts and attempted page readings (including per-field failures and their OCR snapshots) remain in private reviewer artifacts, not the submission packet. Current and historical reading share the full-questionnaire profile's 20 OCR-page and 20 independent-image-call allowances; repeated page reads reuse cached results. The expanded blind response is capped at 16,384 output tokens, with no automatic retries. This validates transcription/association, not current continuity or semantic applicability.

The internal summary prominently labels historical uncertainty and lists prior source/hash/page, issuer, known or unknown date, question/role context, current checks and what the reviewer must confirm. Historical originals are **never selectable as submission attachments**. A historically prefilled application remains incomplete, including when literal current corroboration was found, until the separate human review.

To stage a newly approved historical partition, use a **new immutable evidence-set ID** and the existing staging command:

```bash
python -m bd_packet_builder.blob_storage --account-url https://ACCOUNT.blob.core.windows.net \
  stage --root . --blank bd_agreements/Blank/ISSUER/form.pdf \
  --blank-id APPROVED_BLANK --evidence-set-id NEW_APPROVED_SET \
  --issuer "Issuer name" --historical-manifest outputs/approved-history.json
```

The historical manifest uses the existing `ArchiveManifest` schema (`path`, `sha256`, `partition`, `issuer`, optional `completed_on` and `reporting_period`). Approval must precede access/upload/model use; do not generate approval implicitly from a directory listing. The Blob bundle binds the issuer, partition manifest and exact historical inputs, and the run manifest retains those values for gate/writer rechecks. Existing support-only bundles remain valid and do not gain historical access.

The local `bd-packet agent-run` command also accepts `--historical-manifest` and `--issuer`, with the same partition rules and explicit `--allow-paid` requirement. Neither entry point takes a manually prepared question/answer map. Navigation context distinguishes repeated field labels for role matching; it remains model-proposed guidance, not evidence that someone has the role.

The live profile's 80-page evidence limit counts **distinct source/page pairs**, shared by reading and native quote lookup. Reusing an already read page still spends tool-call/returned-character budgets and rechecks source freshness, but no longer consumes another page slot. OCR and independent image calls retain their separate limits. Direct developer tool instances keep their smaller defaults unless explicitly configured.

**Targeted coverage (`packet-agent-v13`):** source discovery and the saved evidence handoff now include `source-context-v1`, defined in [retrieval.py](src/bd_packet_builder/retrieval.py). This map describes expected sections, source subject/coverage, limitations and historical supplemental-answer navigation; it contains no manually supplied business answers and confers no source approval. BrokerCheck routing explicitly distinguishes report-summary evidence from a missing search result and public reporting scope from confidential matters.

The sponsor-approved Broward-only printed-role rule maps Qualified Representative to Primary Representative. The historical gate still requires the source's actual Primary Representative context, issuer match and current-source checks; unrelated issuers/roles and signing acts remain excluded. Explicit filled historical Yes/No firm-description/capability answers can now pass the existing checked-association path, with historical continuity warnings. The entire answer quotation must be Yes or No; unchecked labels are not evidence. Sensitive disclosures, financial eligibility, personal confirmations and requested-period facts remain excluded from automatic historical reuse. The sponsor's investigation interpretation is recorded for evidence discovery, but validated prior/current event-baseline comparison is still outstanding; no blanket historical-negative override was added.

Long text answers that cannot fit their mapped region at the existing minimum readable font can use a bounded supplemental page, with a short page reference in the original field. Text is never truncated or shrunk below the existing minimum; the final renderer checks the reference region and full supplemental text. Interactive reviewer fields and electronic-signing compatibility are not implemented by this increment; signatures, dates and unevidenced personal acknowledgments remain blank.

**Measured targeted result:** source-guided run `ed3767401ff445b58f83971efbda6f3c` collected 80 checked historical candidates across 19 distinct source pages. Its first execution saved 12 successful groups and failed on one malformed citation span; explicit request `broward-source-guided-20261030-17-r1` reused them and retried **only that one group**, with no repeated discovery/OCR/image calls. The immutable Blob result published **31/68 written requirements** and was downloaded/hash-verified.

The output audit identified a false withholding: a supporting state quotation did not repeat the city value, although the checked city quotation did. A failing regression preceded the correction; the gate now requires the value in at least one approved prior quotation while retaining source/page/relationship checks on all citations. Deterministic gate/writer revalidation of the **unchanged saved proposals**, with zero additional model calls, produced the local [66-page corrected draft](outputs/broward-agent-20261030/attempt-17-revalidated/packet.pdf), [reviewer summary](outputs/broward-agent-20261030/attempt-17-revalidated/reviewer-summary.txt) and [field audit](outputs/broward-agent-20261030/attempt-17-revalidated/field-audit.json): **32/68 written requirements**, versus 28/68 before this increment. The [revalidation record](outputs/broward-agent-20261030/attempt-17-revalidated/revalidation.json) distinguishes this local correction from the unchanged 31/68 Blob result; it is not a new inference run or cloud publication.

The four new populated requirements are the backup title (readable supplement), historical public-sector reference candidates (supplement), explicit Florida-office Yes and Qualified Representative printed name. All 28 previously populated requirements remain populated. The printed signer title is still missing, and reference qualification/currentness remains unconfirmed; **written is not synonymous with completely satisfied**. Of 34 proposed answers, 32 write and two attachment answers remain withheld. The other blanks are 26 model-reported evidence gaps, four unsupported historical-choice paths and four signing/personal-act deferrals. Current BrokerCheck contents were not successfully captured as checked disclosure-answer evidence; that is an extraction/verification gap, not proof the reports lack disclosures. Primary-title/account-opening extraction and historical event-baseline comparison also remain outstanding.

All five form pages and four supplements were visually inspected. Render checks report zero changed pixels outside allowed regions; signing fields remain blank. All three appended evidence sections retain unchanged page-content streams, and neither historical originals nor internal reviewer/checkpoint artifacts are appended. Final deterministic validation: **922 passed, five skipped** on Python 3.12 and 3.13; Ruff lint/format, strict mypy on both runtimes and diff checks passed. Broad coverage and independent held-out accuracy acceptance remain unmet.

`packet-agent-v12` makes the approved historical-prefill policy explicit: unknown continuity alone is not a reason to omit an otherwise eligible checked historical answer. `finish_evidence` reoffers every checked historical association, the complete requirement list and reading usage for a second completion pass before proposal submission. Contradictions, period-sensitive facts, disclosures and personal/signing acts retain their exclusions. This handoff is not evidence that the model used every eligible answer; real output coverage must be measured independently.

**Code-controlled answering (`packet-agent-v12`, `answer-groups-v1`):** the local and Blob workflows retain agentic evidence discovery but stop that tool loop immediately after `finish_evidence`. Application code divides the interpreted non-signing requirements into stable groups of at most five, in form order; this is not a hardcoded issuer answer map. Each independent structured answering call must return exactly its assigned requirements, with supported proposals or explicit unresolved outcomes. It has no tools, uses low reasoning effort, at most 8,192 output tokens and a 180-second ceiling. Evidence discovery retains its 16,384-token response bound. The 60-call orchestration allowance is split conservatively into 30 discovery calls (including the SDK's final no-tools turn) and 30 cumulative group attempts; mapping/image allowances keep the total model-call ceiling at 85.

The private run archive now saves `answer_handoff.json`, a hash/version-bound `answer-plan.json`, a request marker before each group call, and the actual response plus field-path validation diagnostics afterward. A successful group is labeled `staged_unvalidated`, not evidence-approved. Application code performs final combined gate validation, rendering and publication only after every group has a schema-valid disposition. Missing business evidence remains an explicit review exception; malformed responses or technical group failures leave a failed run with no fictional completed packet. The underlying ten-item staging contract remains for existing callers, but live models no longer manage staging, submission or publication themselves.

The SDK receives a strict JSON-schema mapping, rather than a Pydantic response class, so application code can archive the raw response before local semantic validation. Proposed answers have a separate wire-schema branch requiring a non-null value, at least one citation and numeric confidence; unresolved outcomes require an explanation. This fixes an observed producer/consumer mismatch, not an evidence-standard relaxation. Three consecutive technical group failures stop the execution; private diagnostics retain bounded exception classifications and validation paths without logging response contents.

Before group validation, code resolves a plain native-shaped citation to the saved checked
receipt only when source ID, page and exact quote identify one unique receipt. This also handles
a model incorrectly expressing checked OCR evidence as text offsets. No fuzzy quote matching or
new evidence is introduced; ambiguous references, extra fields and altered OCR hashes are not
repaired. Raw responses remain unchanged in the archive, with resolution paths recorded separately.
Restored citations still pass the ordinary source, OCR and question/answer relationship checks;
resolution is not evidence approval. Successful groups replay the same resolution on recovery.

Historical `current_checks` accept native citations or exact checked OCR receipts. Both the gate
and writer recheck scanned source/render/artifact hashes, subject agreement and OCR confidence.
A scan inspected without corroborating the historical answer remains `not_corroborated`; it
does not become answer support or current confirmation. Contradictions and missing or changed
scan receipts still withhold the answer. Current-check-only OCR artifacts are archived and their
receipts retained during completion recovery.

**Explicit recovery, not automatic retries:** each execution attempts each unfinished group once. Recovery rechecks the blank, every source snapshot, saved artifact hashes, workflow/model configuration and OCR receipts, then reloads successful groups and calls the model only for unfinished ones with their prior errors. There are at most three attempts per group, also bounded by the cumulative 30-call group budget. No evidence discovery, mapping or blind-image model calls are repeated on recovery. Old v11 failures did not save this handoff/progress and cannot be retroactively resumed.

If recovery reports `Run input rejected: Evidence changed after the run snapshot`, the named
source no longer matches the original bytes; this is not a PDF-readability diagnosis.
Recovery stops before model calls. Restore that exact original version only if the source change
was unintended, or start a new run using the revised source. Never edit the saved manifest/hash
or mix staged answers with a different evidence version.

For a local run (use the original evidence root and run-store folder):

```bash
bd-packet agent-resume --root /APPROVED/DATA/ROOT --runs-dir /PRIVATE/RUNS \
  --run-id RUN_ID --endpoint https://ACCOUNT.openai.azure.com/openai/v1 \
  --deployment ORIGINAL_DEPLOYMENT --allow-paid
```

The hosted Responses boundary also accepts `{"operation":"resume","request_id":"NEW_REQUEST_ID","resume_request_id":"FAILED_REQUEST_ID"}`. This re-stages the original approved Blob inputs and restores the hash-verified failed answer run into isolated storage. Results use the new request ID, leaving the failed request's archive unchanged. Do not supply replacement blank/evidence IDs or business answers. Publication is internal only; signing and issuer submission remain prohibited. The legacy all-tools runner remains available to developer callers, not the live entry points.

**Grouped Broward result, October 30:** run `20a132a2955840049b10e11c098cce93`, request `broward-grouped-questionnaire-20261030-16-r2`, produced a hash-verified [75-page incomplete packet](outputs/broward-agent-20261030/attempt-16-r2/packet.pdf), separate [reviewer summary](outputs/broward-agent-20261030/attempt-16-r2/reviewer-summary.txt) and private [field-by-field audit](outputs/broward-agent-20261030/attempt-16-r2/field-audit.json). It writes **28/68 requirements (41.2%)**, up from 6/68 in attempt 11: two current-evidence answers and 26 historical-continuity-unconfirmed prefills. All 13 groups reached schema-valid staging, followed by code-controlled validation and assembly. Of 31 proposed answers, two attachment answers were gate-withheld and one title did not fit at the configured readable font size. The other 37 blanks comprise 31 model-reported missing-evidence outcomes, one unsupported historical-choice path, four signing deferrals and one unresolved signer. A model's missing-evidence disposition is **not proof** that the approved original sources contain no answer.

The initial grouped run and first recovery were operator-stopped and archived as failed; neither produced a packet. The first recovery's saved responses identified proposed answers with `confidence: null`, which the old nullable wire schema permitted but the proposal validator rejected. The outcome-specific schema above corrected that contract. The second recovery reused the original evidence handoff without repeating discovery, mapping or OCR/image model calls. Assembly completed, but the first Blob publication encountered `ServiceResponseError`; replaying only immutable publication from the saved local run succeeded, without further inference, and the downloaded artifacts passed hash verification.

All five form pages and two supplements were rendered and visually inspected. Render checks report **zero pixels changed outside allowed form regions**; signatures, dates and initials remain blank. Historical originals and private reviewer/checkpoint artifacts are not appended. Remaining coverage work includes discovering referenced historical supplements, obtaining checked title associations, handling eligible historical choices/booleans, and fixing the specific attachment/fit failures without weakening financial, disclosure or personal-act safeguards. This is meaningful coverage improvement, **not near-complete questionnaire acceptance**. Offline validation: **909 passed, five skipped** on both Python 3.12 and 3.13; Ruff lint/format, strict mypy on both runtimes and diff checks passed. Held-out accuracy is not applicable because the prior Broward packets were answering inputs.

`historical-page-context-v3` resolves repeated native values using their actual PDF character geometry instead of requiring a value to occur only once on the entire page. Repeated state/city/address values need not fall back to less reliable OCR solely because they recur. A unique occurrence inside the independently proposed field region is still required; oversized/ambiguous regions and wrong-role associations remain rejected. Question captions also tolerate whitespace immediately after the same printed question number (`10.For` versus `10. For`), retaining the actual OCR quotation. Numbers, other words, answer formatting and the 90-confidence threshold are not relaxed. Existing v1/v2 receipts remain eligible only after the same source, quotation, render and geometry rechecks.

Native placement now retains the exact PDF quotation when a question number is glued to its first word (for example `10.For`); an explicitly different question number is still rejected. Small edge collisions can be trimmed inside the model-proposed writing area only if at least 90% of that area remains; the resulting region is still checked for native ink and independently revalidated by the writer. Larger overlaps remain withheld. The unchanged cached Broward visual maps now produce 55 placements rather than 50, with three outstanding placement exceptions; this is not an answered-field count.

**Completion attempt `-12` failed before answer submission:** run `5d35d6202da7462a991736d9e32df3d8` used the expanded reading profile and repaired placements, but no packet was produced. The retained failure chain is `ChatClientException -> APITimeoutError -> ReadTimeout -> ReadTimeout`, confirming an orchestration timeout at the explicit 600-second ceiling. Unlike earlier ambiguous failures, this cause is recorded. v9 adds the generation bounds/batching above and content-free per-tool progress logging; it does not automatically retry failed calls or label the failed run complete.

**Attempt `-13` also failed**, run `539ee13ff05f467582a457bdd3433178`, with the same retained timeout chain after evidence collection and two accepted answer batches. No packet was published; in-memory batches are not recoverable run artifacts. It read 13 distinct pages, seven OCR pages and five independent historical images, so the expanded reading allowance was not exhausted. v10 uses the SDK's deterministic compaction hook after evidence collection: each answering call receives the complete checked handoff (requirements, navigation, source metadata, native/scan quotes and historical associations), staged/remaining IDs and the latest complete tool exchange, rather than replaying all raw page reads and earlier answer batches. No summarization model or new model calls are added. This reduces context growth; it is not proof that context size caused either timeout. A fresh approved run is still required to establish actual output coverage.

**Attempt `-14` failed**, run `61284870290c400d84e14930880c9cc9`: after collecting evidence, it repeatedly alternated rejected answer batches and successful status queries. It was explicitly failed closed with `repeated_answer_batch_rejections`; no packet was published. Investigation found that the tool advertised 500 proposals while runtime accepted ten, compaction could drop the preceding rejection, and status queries reset consecutive-error accounting. v11 corrects all three contracts and logs safe error codes. The rejected arguments were not archived, so the exact rejection cause is not asserted.

**Attempt `-15` also failed**, run `9fd7f6deb9524b158909e6eabdf3e71d`, using v11 and historical context v3. Evidence collection completed; one answer batch was accepted and four were rejected with `invalid_arguments`, followed by another retained `ChatClientException -> APITimeoutError -> ReadTimeout -> ReadTimeout`. No packet was published, and the in-memory batch was not recoverable. Downloaded evidence diagnostics passed artifact hash checks. The archived evidence contains 65 historical associations, not 65 filled answers; it does not establish eligible-answer coverage or explain the rejected argument fields. The latest published packet remains attempt `-11` with **6/68 written requirements**. Useful completion remains unmet; do not launch another unchanged full run or describe the remaining blanks as proven business-data gaps. The answer phase needs smaller bounded work units with durable proposal/validation diagnostics before another completion attempt. Offline validation after these corrections: **895 passed, 5 skipped** on both Python 3.12 and 3.13, with Ruff lint/format and strict mypy green.

The sponsor explicitly authorized the **two Broward 2025/2026 packets** for private Blob staging and relevant Foundry input on October 29. Other completed packets remain excluded from this run. Because both Broward answers are answering inputs, this test cannot claim held-out Broward accuracy. See the [scope policy](Broker-Dealer%20Packet%20Automation%20Phase%201%20Scoping%20Document.md#6-source-documents-and-version-selection) and [implementation sequence](docs/development-plan.md#next-local-poc-slice---historical-business-evidence).

**Initial historical run, retained as a failure finding:** request suffix `-8`, run `505abdcfbcdf448da004b9b8129c6100`, published a 62-page incomplete packet with three current-evidence answers and no historical prefills. Five answers were proposed: one historical reference answer had no accepted placement, and one historical background answer overstated partial current corroboration. The final gate withheld both. Quote lookups also exhausted the old page budget because repeated access to cached pages was counted again. A failing regression reproduced that accounting bug; distinct-page accounting and explicit exact-versus-partial corroboration instructions were added before the corrected run. Zero pixels changed outside allowed form regions. These results are not useful-coverage acceptance or model accuracy.

**Corrected real historical run:** request suffix `-9`, run `e06f8dc37f8d4b038c660ba2fa70eb21`, published a [64-page incomplete packet](outputs/broward-agent-20261029/attempt-9/packet.pdf) and separate [reviewer summary](outputs/broward-agent-20261029/attempt-9/reviewer-summary.txt). It writes **4 of 68 interpreted requirements**: two current-evidence answers and two historical-continuity-unconfirmed narratives (instrument specialization and fixed-income background). No historical answer was promoted to currently corroborated. A third historically supported reference proposal remains blank because placement was unavailable. The 64 blanks comprise 59 `missing_evidence` outcomes, three signing deferrals, one unresolved signer and that placement exception. The historical originals are not appended; the packet contains five form pages, two answer supplements and 57 current-support pages.

This verifies the historical prefill/provenance path, **not useful overall coverage acceptance**. It is not a net coverage gain over the earlier five-answer attempt. Of the 59 missing-evidence explanations, **25 mention unavailable same-page historical question/role context** and **16 mention scan/OCR limitations**; these categories overlap and are model explanations, not independently established absence of business data. Many prior answers are native text over scanned issuer forms, while their question/role labels are not natively citable. Reading that mixed representation reliably remains a material upstream blocker. Do not describe those blanks as requiring new business input without resolving the reading/context gap.

**Historical page-association verification:** request suffix `-10`, run `c2fead356fe24d4989ea7aac0d42d205`, exercised the new tool against the same approved private Blob bundle. It returned 29 associations across prior form pages 2/4. An initial local-geometry recheck accepted 19 and withheld 10. Actual rendered-source inspection found a false-abstention bug: a left-hand section header legitimately governs right-column fields, but the first rule required horizontal text overlap. A failing regression preceded the fix; all **29/29 now pass provenance/local-geometry rechecks**, with separate competing-column and swapped-role tests still rejecting wrong associations. This is association/transcription validation, **not business eligibility, answer accuracy or questionnaire completion**; some associations concern historical choices/disclosures that the reuse gate still excludes.

That run failed after evidence collection with `model_call_failed` / `ChatClientException`, before answer validation or packet publication. Its [retained artifacts](outputs/broward-agent-20261029/attempt-10/) were downloaded and hash-verified; there is **no packet** from this attempt. The failure occurred 180.08 seconds after evidence collection, matching the configured timeout, but the original wrapper did not preserve the underlying cause, so a timeout diagnosis is not asserted as proven. Failure metadata now retains bounded exception-type chains and HTTP status codes, never error payloads/document text. The next controlled run uses an explicit 600-second model timeout within the existing limit; automatic retries and call/page budgets remain unchanged.

**Published association run:** request suffix `-11`, run `a716f73b38ed4e8c8fc85f8c0766d031`, produced a hash-verified [64-page incomplete packet](outputs/broward-agent-20261029/attempt-11/packet.pdf) and separate [reviewer summary](outputs/broward-agent-20261029/attempt-11/reviewer-summary.txt). It writes **6/68 requirements**, versus 4/68 in attempt 9: two current-evidence answers and four historical-continuity-unconfirmed answers. The new historical prefills are the primary and backup representative names, with independently checked source question/role associations and issuer-specific assignment context. The two historical narratives remain flagged. No historical answer is currently corroborated or human-approved. Of seven proposed answers, only the reference narrative was withheld for missing placement; the remaining blanks are 57 missing-evidence outcomes, three signing deferrals and one unresolved signer. Zero pixels changed outside allowed form regions. Actual form/supplement renders were inspected; all six accepted answers passed a fresh final-code gate recheck with no decision changes.

That full run issued 28 associations from five prior pages. The whole-row header fix was completed while it was running: replaying its **exact recorded blind image readings** against unchanged sources/OCR under the final rules yields **38 associations**, not 38 filled or eligible answers. No new model-generated text or manually authored mappings were supplied for that replay. Those extra associations have **not** been run through a new answer-generation/publication cycle; the linked packet remains at six filled requirements. Historical choice/disclosure/financial/signing exclusions still apply. Offline validation: **875 passed, 5 skipped** on both Python 3.12 and 3.13, Ruff lint/format and strict mypy passed. Broad questionnaire coverage and held-out model-quality acceptance remain unmet.

Downloaded artifacts passed hash verification. Actual form pages 2/4, answer supplements 6/7 and both cited historical source pages were inspected locally; the promoted historical wording matches the cited sources, retains historical qualifiers and is prominently flagged internally with unknown completion dates and reviewer confirmation needs. Render checks recorded **zero pixels changed outside allowed form regions**. This spot check is not an exhaustive semantic evaluation. Final offline validation: **855 passed, 5 skipped** on Python 3.12 and 3.13; Ruff lint/format, strict mypy and diff checks passed. Held-out accuracy is not applicable because the prior Broward answers were inputs.

### Machine-cross-checked scanned evidence

The authorized local PoC can now use scanned evidence for **text/identifier draft answers** through [scan.py](src/bd_packet_builder/scan.py), prompt `scan-cross-check-v1`, `packet-agent-v4`, `answer-gate-v3` and writer `reviewed-draft-overlay-v3`. This is machine transcription agreement, **not human visual approval, semantic proof or a zero-hallucination guarantee**. The existing human-reviewed OCR path remains available and unchanged.

1. The agent calls `read_page` on a snapshot-approved source. Local Tesseract produces the existing unverified OCR artifact with word confidence/geometry, source hash, page and 300-DPI render hash. OCR text alone remains uncitable.
2. The new `verify_scan_quote` tool accepts only source ID, page, an exact contextual OCR quote and the explicitly printed source subject. It accepts no paths, recipients or commands.
3. A separate bounded Foundry request reads the original page image **without the OCR text, candidate quote, proposed answer or expected subject**. It independently returns visible text, the record's subject and an explicit reporting period when available.
4. Code requires agreement on the quote (case/whitespace normalization only), subject, OCR token span and word confidence of at least 90 for the quote and subject. Digits, leading zeros, signs and punctuation are not repaired. Disagreement, unknown subjects and unreadability are explicit abstentions.
5. The tool returns a full `OcrCitation` plus independently read subject/period. The gate accepts only runtime-issued check receipts, validates artifact/source/render hashes and exact scalar values again, and checks requested/claimed periods. The writer rechecks those receipts and evidence; it does not set human approval flags. Scanned narratives, choices, booleans/attestations and signer-role answers are not enabled by this slice.

The agent must still establish that a contextual quote answers the issuer's question; agreement between two readers does not establish semantic support, currentness, representative designation, eligibility or a personal act. Unknown facts stay blank. A catalog/filename period that differs from the image-read reporting period is explicitly noted internally, not silently treated as matching.

Independent image readings are limited to 20 per live run, including failed attempts (direct tool instances default to five). A successful page transcription is reused in memory for other quotes from the same source/page/render; no cross-run scan approval is assumed. The full-questionnaire live cap is 85 model calls including orchestration and blank mapping. Repeated OCR page reads reuse exact-page results while checking source freshness. The path uses the existing Foundry deployment and local OCR engine; no new dependencies or cloud resources were added.

`scan_checks.json`, hash-addressed OCR JSON artifacts, and the answer review retain the check provenance and transcript in the private reviewer results. `evidence_tool_trace.json` retains content-free tool outcomes/error codes, not document text or model payloads. These internal artifacts are never merged into the submission PDF or ordinary logs. The OCR/transcript artifacts may contain confidential text and require the same access/retention controls as the sources. The reviewer summary labels machine cross-checks separately from human visual confirmation. Offline tests cover agreement/disagreement, leading zeros, source/subject, confidence, period and kind restrictions, receipt replay/mutation, budgets, blind image inputs and complete agent-to-writer artifact staging. Those tests are not model-quality evaluation.

The first real cross-check attempt, request suffix `-6` / run `aabc43af9caa4d1ab606b4a2c6bfd97d`, published an incomplete seven-page packet with three answers and **zero successful scan checks**. Real OCR metadata exposed a case-sensitive subject-token lookup: the firm name appeared with different capitalization in OCR, even though its tokens had sufficient confidence. A failing regression reproduced that problem; subject lookup now permits case differences only, without repairing punctuation, digits or names. The attempt also demonstrated that the model omitted uncitable scanned attachment candidates; v4 explicitly separates attachment selection from citation usability. Attempt 6 is retained as a failure finding, not a scanned-evidence success.

**Corrected real run:** request `broward-full-questionnaire-20261029-7`, run `b68bf0214d3443038ba658888f7aacc7`, published a [64-page incomplete packet](outputs/broward-agent-20261029/attempt-7/packet.pdf) and separate [reviewer summary](outputs/broward-agent-20261029/attempt-7/reviewer-summary.txt). Five answers were written, versus three previously: firm name, firm CRD, broker/DTC number, instrument-specialization narrative and background narrative. **One answer (firm CRD) now uses the machine-cross-checked scan path**; the other new answer uses native evidence. Of four `verify_scan_quote` tool attempts, one passed, one was rejected for low OCR confidence and two returned unreadable-page abstentions. This is a tool-outcome denominator, not answer accuracy; repeated attempts may refer to the same page.

Four relevant supporting PDFs are included (FOCUS, firm FINRA BrokerCheck, public-funds material and delivery instructions): 58 evidence pages plus five form pages and one supplemental-answer page. The FOCUS and FINRA candidates are explicitly described as partial/unconfirmed evidence where their adequacy is unresolved; their inclusion does not satisfy every checklist item. Sixty-three of 68 interpreted requirements remain blank, including signatures/dates, unresolved roles, unsupported disclosures and address/office facts whose scanned evidence failed verification. Low confidence or an unreadable independent reading was not overridden to increase coverage.

Downloaded artifact hashes passed. Form pages 1, 2, 4 and 5, the supplemental answer, and the accepted scanned source page were inspected locally. The one promoted scanned value matched the visible source value (one inspected case, not a held-out evaluation). Render checks recorded zero changed pixels outside permitted regions; signature/date/checklist areas remained untouched. These checks do not establish exhaustive narrative grounding, currentness, attachment sufficiency or business approval. FOCUS scan readability/confidence and genuine evidence/designation gaps remain the next substantive blockers.

Regression validation for this increment: **831 passed, 5 skipped** on Python 3.12 and 3.13; Ruff lint/format and strict mypy passed. No dependencies or cloud deployments were changed.

## Controlled draft completion

The [draft writer](src/bd_packet_builder/draft.py) now produces a real PDF **incomplete draft**, not just answer/location JSON. It reuses the existing requirements/proposals, native citation checks, hash-bound response mappings, text wrapping and packet pagination contracts. It does not modify the retrieval/review checkers to pretend their unapproved proposals are writable.

### Try a real public blank with fictional evidence

```bash
python -m examples.draft_completion_demo --root .
python -m examples.draft_completion_demo --root . --overflow
```

The [example](examples/draft_completion_demo.py) copies only the designated public blank into a unique ignored fictional root, generates fictional supporting evidence, and supplies an explicitly fictional review fixture. It never reads real supporting documents or Completed packets, calls a model, or claims a business reviewer approved the answers. The first variant writes a short narrative inline; the second writes a cross-reference to an actual multi-page supplemental-answer section. Both exercise firm name, leading-zero CRD, one radio selection, several checkbox selections, Other write-in, an unresolved DTC number, and untouched signature/date areas. These are developer-mapped subsets of one exact blank version, **not automatic whole-form completion or a model quality evaluation**.

Each successful run publishes a unique `outputs/draft-.../` **inside the fictional root**, containing:

- `draft-packet.pdf`: original form pages with flattened answer overlays, any full supplemental answers, then reviewed supporting PDFs in explicit order. A 24-point draft banner is added **above** each original form page rather than obscuring or scaling issuer content. Supplemental pages are labeled as drafts; original attachment pages are preserved, not stamped or rewritten with answers.
- `draft.json`: exact input/review/application/output hashes, declared requirements and mappings, per-answer values/citations/review reasons/exceptions, actual final pagination, attachment records and render-check results.
- `reviewer-summary.txt`: separate internal answer/value/evidence/exception report, including form/source/packet page locations. It is never appended to the packet.
- `page-N-before.png` / `page-N-after.png`: rendered original/form output comparisons for every form page.
- `supplement-page-N.png`: actual renders of each generated supplemental page; full answer text is checked within its body region before publication.

Generated form and supplemental pages are labeled **INCOMPLETE DRAFT - NOT FOR SUBMISSION**; the example additionally labels form pages **FICTIONAL DATA**. Attachments retain their original pages. The entire application is not declared complete: unattempted fields outside the selected subset remain unresolved. The source blank and supporting PDFs remain unchanged.

### Explicit reviewed handoff

The general local command is:

```bash
bd-packet draft --root . --request outputs/draft-request.json \
  --review outputs/draft-review.json
```

Use actual prepared input filenames. This is currently a technical/development interface, not a business-maintained JSON workflow. The typed `DraftRequest` contains the blank `source`, `mode` (`fictional` or `reviewed_evidence`), existing `ApplicationRequirements`, `ResponseLayout`, `AnswerProposals`, exact supporting paths/hashes, ordered attachment source IDs, and protected regions. Existing retrieval proposals and reviewed mappings can be supplied in those same contracts; **there is no automatic discovery/retrieval-to-reviewed-draft promotion**.

`DraftReview.request_sha256` binds the review to the exact request-file bytes, including values, citations, mappings, source versions and attachment order. Each `draft_verified` decision must explicitly confirm evidence support, source approval and placement, and include a reason; attachments need their own reviewed source IDs. Omitted/withheld decisions leave answers blank. A model's confidence, catalog description or exact quote cannot create this review. For real evidence, a person must check support/conditions/periods and placements before recording the decision.

Optional `reviewer_notes` are copied into the internal reviewer summary and JSON manifest only; they are never written onto or appended to the packet.

**The review JSON is a trusted local development input, not authentication, a digital signature, or a production approval boundary.** Do not let the model write it or treat a generated fictional review fixture as business authorization. Restrict access operationally. No human-maintained fact sheet is introduced, and this temporary checkpoint is not the target permanent per-field business process.

The writer rechecks native citations and exact identifier strings, requires requested/claimed periods to agree, and includes cited evidence in the packet before writing a value. It rejects request/review/source changes, wrong application hashes, unknown identities, overlapping/protected regions and writable text regions covering existing issuer text. Unsupported/malformed answers and unfit write-ins are withheld individually while supported work continues. Signing requirements cannot receive writable mappings or approved write decisions.

OCR can now be used as a **separately reviewed citation type**, not as automatic evidence promotion. An OCR citation binds the selected source hash, page, exact OCR JSON artifact hash, deterministically re-rendered page hash, and a contiguous range of OCR words that must reconstruct the quotation and pixel bounds. The writer validates the artifact and source again. A `draft_verified` OCR answer additionally requires explicit reviewer confirmation of the report subject, visual OCR text, evidence support, source approval, and field placement. The OCR page stays in the attached evidence packet. OCR confidence alone never approves a value, and `check_proposal` continues to mark OCR citations as requiring local review.

The local `DraftReview` JSON remains trusted development input, **not authenticated business approval**. In the current controlled Broward trial, two distinct user-selected FINRA BrokerCheck reports were locally inspected on their covers and relevant registration sections. The writer supports separately reviewed OCR citations, attached issuer forms, and up to 100 declared requirements and 100 total packet pages. These limits were raised to accommodate this bounded packet, not to claim general-purpose scaling.

### Full local Broward packet attempt

The final local artifact is an **incomplete draft, not for submission**. It contains 75 pages: five Broker-Dealer Questionnaire pages, two Authorization-to-Trade pages, then the 32-page FOCUS report, 24-page firm BrokerCheck, 11-page representative BrokerCheck and one-page public-funds overview. It declares 61 requirements and writes 13 reviewed values. The checklist marks only the FOCUS and FINRA registration items because those reports are attached. Question 2 remains blank because the overview lists product categories but does not establish that the firm offers them regularly. Eligibility, Questions 7 and 8, Question 12, other unsupported fields and unresolved checklist items remain blank or unchecked. Signatures and dates remain blank.

The firm and representative reports were appended separately. The internal reviewer summary is separate from the issuer PDF. The output was locally rendered and inspected; form render checks reported zero changed pixels outside reviewed writable regions. Inputs and review decisions were prepared manually; no model call, external upload, signing or submission occurred. The output is stored in the ignored `outputs/draft-.../` area with its request, review record and manifest. This demonstrates bounded deterministic assembly for one attempt, not full-form accuracy, automatic evidence approval, or completion of M2/M3 acceptance criteria. The firm report's regulatory-event details were not assessed.

### Writer limits and verification

- This slice writes scalar text/identifiers, single/multiple selections with write-ins, and narratives. Money, ordinary dates, boolean-specific layouts, tables and arbitrary fonts are not released by this writer; they remain explicit exceptions. Existing proposal contracts support more kinds than this writer.
- Blank forms must have native instruction/label text, zero rotation, standard point units, origin `(0,0)` and no differing crop box. Prefilled native fields are rejected. Scanned/rotated **blank mapping** is not wired into this writer; rotated supporting attachments are a separate case and are preserved.
- Limits: 100 declared requirements, 26 selected sources and 20 supporting attachments, 30 inventoried files in designated source families, 100 total packet pages, 2 MiB per JSON input, existing 64 MiB per PDF input, and 12 million pixels per rendered form page. OCR page citation verification is limited to 20 million rendered pixels. Helvetica is fixed at the reviewed readable size (minimum 10 points); unsupported characters or unbreakable/oversized text are flagged, never silently substituted, shrunk or truncated.
- Long narratives retain their complete answer in one or more question-labeled supplemental pages, with final evidence references and a form-page backlink. The form marker points to the actual supplement start; attachment page references use actual form/supplement/attachment page counts.
- Before atomic publication, native text is checked in the written regions and actual form renders are compared at scale 2. After removing the added banner, there must be zero changed pixels above luminance difference 16 outside actual written regions plus a fixed two-pixel edge allowance. Selected controls must visibly change. These checks protect placement/preservation, not semantic support or whether a reviewer chose the right mapping. Human visual inspection remains necessary.
- The packet, internal summary, report and PNGs publish together only after checks and input freshness rechecks. Failures leave no successful/partial published run. Repeated successful invocations create new isolated run directories; they never overwrite earlier outputs. The report hashes identify repeat inputs, not a production idempotency/notification service.
- Signatures, signature dates, unresolved fields, undeclared fields and unapproved attachments are never supplied by inference. No signer-specific duplication, archive comparison, chat revision, notification, signing or submission is implemented here. Sources, drafts, reports and PNGs remain potentially confidential and must stay in controlled local output locations.

ReportLab was already pinned for fictional PDFs; its same verified `5.0.1` pin is now a runtime dependency because the application itself draws PDF overlays/supplements. No new PDF framework or version was introduced. Strict mypy checks application boundaries; as with PDFium, the untyped ReportLab dependency is explicitly configured.

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
- Sparse native text or a dominant page image triggers an explicit OCR-needed condition. `--allow-ocr` permits the existing **local** Tesseract experiment on those selected pages, including displayed landscape/90-degree rotation. Detection is heuristic, not universal scan classification. OCR remains unverified by default, is not automatically sent to answer generation, and is never promoted to native citations. A separately prepared OCR citation can enter the controlled draft writer only after the explicit visual/source-subject/support/placement review above.
- `--cache outputs/retrieval-RUN_ID/retrieval.json` optionally reuses **unapproved native proposals** only when the requirements/application hash, catalog, route plan, source hashes, extracted page text, eligible requirements, prompt/schema and model configuration match. Substitute the actual prior report path. Sources/pages and quotations are rechecked; cached source/answer/input mutations cannot silently become approved facts. Invalid context is explicitly invalidated; malformed cache input is rejected, and failed citation checks are labeled rejected.
- Cache reuse requires the same model configuration/opt-in. It suppresses the answer call, not source/page rechecking, OCR work or automatic routing; supplying the existing plan also avoids another routing call. It is not a trusted universal answer sheet, signed fact register or cross-application approval mechanism.
- Internal reports/cache/OCR artifacts contain potentially confidential text and source metadata. Keep them out of submission packets, ordinary logs, source control and public artifacts. No approval, signatures, notification, PDF assembly or submission is introduced.

## Opt-in live agent runs

`bd-packet agent-run` lets the Foundry model drive the repository's tools end to end on one blank form: interpret the form, retrieve evidence, submit answers, assemble the packet and publish results. It is paid and sends page images and evidence text to the model. Use fictional data unless you have explicit authorization to process the selected documents at the configured endpoint. Place the blank under `<root>/bd_agreements/Blank/` and evidence under a designated family such as `<root>/bd_agreements/supporting_data/FINRA_Certification/`.

### One-command Broward workstation demo

After local setup and an Azure CLI sign-in with model inference permission (`az login` if needed),
start a fresh model-driven run from the repository root:

```bash
./scripts/run_broward_demo.sh
```

The script selects the checked-in Broward blank questionnaire and the single explicitly
allowlisted 2026 Broward historical application as a `reference` input. It does not include
the other completed applications. `bd-packet broward-demo` prints the blank hash, historical
source/hash and the available supporting-document inventory before asking you to type `RUN`.
Review the listed input paths, model endpoint/deployment and inventory, then decline or close
the prompt if any input is unexpected. The script can be run from any current directory; it
anchors paths to this repository. Override the defaults only when needed with
`BD_FOUNDRY_ENDPOINT` and `BD_FOUNDRY_DEPLOYMENT`.

The demo's HTTP request timeout is **180 seconds**, configurable from 1 to 600 seconds
with `BD_REQUEST_TIMEOUT_SECONDS` or the CLI's `--request-timeout-seconds`. The generic
`agent-run` retains its 60-second default unless explicitly overridden. Dense independent
historical-page transcriptions can exceed 60 seconds. No automatic retry is enabled for
timeouts, connection, authentication or HTTP errors; an expired request is an explicit
technical failure, not a missing-evidence decision. Blank-form page mapping is the one bounded
exception: a model reply that fails the strict page-map schema (for example a zero-area box)
gets exactly one fresh request; a second invalid reply fails the run. Successful page maps are
cached in the Git-ignored `outputs/page-map-cache/` with raw mapping diagnostics, keyed by the
blank-form hash, rendered page, prompt, schema, endpoint and deployment. A rerun of the same
blank reuses only identical maps and pays only for unmapped or changed pages. Delete that folder
to force fresh mapping.

This is a **fresh paid model execution**, not a rebuild of saved request/review JSON. After
confirmation it streams run ID and content-free tool progress (start/completion, phase, tool name,
count and error/failure code;
no document text, tool arguments or answers). The source snapshot, manifest, model/tool trace,
reviewer summary and packet are written to the ignored `outputs/agent-runs/<run-id>/` folder;
the console reports the readable output directory at completion or failure. Inspect `readable/`
for the packet, reviewer summary, manifest and detailed internal artifacts. A failed/incomplete
run is not a successful application. No signatures, approval, delivery or submission occur.
The timestamped, content-free progress stream is also saved as `progress.jsonl` directly under
the run directory, including on evidence-phase failures before an evidence handoff exists.
The final `Run ended` line includes the failure code and its content-free reason; the same
`failure` entry is in `readable/manifest.json`.

The demo has limits of up to 90 paid model calls, 240 tool calls and 60 minutes; **there is no
configured total dollar spending cap**. Local source metadata is listed during preflight. Selected
document excerpts and images may be sent to the configured Foundry endpoint. Run locally only
when authorized to process these documents there. A repeated run creates a new run ID and may
make new paid calls; do not use `agent-resume` unless intentionally recovering the named run.
By comparison, `bd-packet draft --root ... --request ... --review ...` replays already prepared
review inputs without new model reasoning. It is useful for deterministic rendering tests, not
evidence that the orchestrator independently made those decisions.

### Complete evidence handoff and bounded follow-up

Agent v20 / `answer-groups-v2` preserve discovery's native/OCR page readings and cached
independent image transcriptions in `answer_handoff.json` as `candidate_readings`. They retain
source/page/version, extraction issues and OCR artifact references. These observations are
untrusted task data, not approved answers or checked citations; OCR and image readings remain
separate, including when they disagree. Candidate OCR artifacts are archived even when no
quotation was successfully verified.

Answering can return typed `verification_requests` for an already discovered source/page,
exact quotation and subject. Application code verifies those requests with the existing native
or scanned-source checks and passes `verification_results` back to the affected group.
No arbitrary paths, external actions or additional agents are exposed. At most two follow-up
rounds fit within the existing three attempts per group, 30 cumulative group calls and shared
image/tool/time limits; there are at most 20 verification requests per run. Technical model
failures still require explicit recovery rather than automatic retries.

For an explicit USD minimum, a request can include `minimum_amount`: exact issuer
`criterion_quote`, `field_label` and `line_label`, with the amount alone as its quote.
Code verifies the amount, field and line association in one source row. Scans require the
same association in OCR and independent image text, with high-confidence OCR field/line/amount
tokens, checked source subject and source/render/artifact provenance. Code compares `Decimal`
values, including equality at the threshold. Wrapped, absent, duplicate, negative or disagreeing
rows remain explicit verification exceptions. The result establishes one monetary condition,
not operating continuity, regulatory compliance, banking applicability or an entire eligibility
selection. Checked monetary results and verification failures are added to the separate reviewer
summary even if the overall question remains unresolved. Ordinary gate and writer checks still
govern every proposed answer.

Compound questions can carry `condition_assessments`, explicitly labeled model assessments in
the reviewer summary, not trusted reviewer input. Exact issuer criteria are identified as
supported, contradicted, evidence-backed not applicable or unresolved, with reasons such as
`not_searched`, `verification_failed` and `source_lacks_fact`. These labels do not override
evidence verification, approve a packet or establish that every criterion was correctly identified.

Issuer-criterion matching ignores whitespace and PDF line wrapping only; spelling, case and
punctuation must still match. This avoids rejecting an unchanged quotation split across lines.
Malformed or unfinished model JSON is never completed by guessing; it remains an explicit
group failure for recovery. Successful groups and completed verification remain reusable.

Each follow-up saves an immutable request marker before execution and a private result afterward.
Recovery reuses completed verification results and cached image readings, retaining successful
groups. An interrupted verification with unknown paid work is reported, not silently repeated.
The original handoff remains unchanged; per-group verification checkpoints supplement it.
Older v19/v1 runs are not upgraded in place; start a fresh run for this workflow.

Synthetic paid protocol/grounding cases are opt-in with `BD_RUN_EVIDENCE_FOLLOWUP_EVAL=1`
and the existing `BD_FOUNDRY_ENDPOINT` / `BD_FOUNDRY_DEPLOYMENT` variables. Run
`python -m pytest -q tests/integration/test_evidence_followup_eval.py` only when paid calls are
authorized. Offline fixtures establish contracts and rendering behavior, not model-quality metrics.

### Navigating the readable run artifacts

`readable/` is a named export of the immutable run archive, not an input folder or editable
answer sheet. A question appearing in an answer group means it was considered, not accepted.
For ordinary review, start with **packet → reviewer summary → final draft audit**.
For a missing answer, trace **group response → gate decision → final draft audit**.

| Artifact | Purpose |
|---|---|
| `packet.pdf` | Generated application and submission-side supporting attachments; still an unsigned draft. |
| `reviewer-summary.txt` | Human-facing evidence, blanks, uncertainty and review actions; never merged into the packet. |
| `draft.json` | Writer audit: actual written/withheld fields, source/output hashes, attachments and render checks. |
| `manifest.json` | Overall status/outcome, source snapshot, versions, limits, steps and failures. |
| `blank.pdf` | Preserved original application. |
| `form_interpretation.json` | Questions, answer types, choices, layout and protected signing regions. |
| `answer_handoff.json` | Discovery observations and checked evidence supplied to answering; not answer approval. |
| `answer-plan.json` | Stable groups of up to five questions, handoff hash, versions and call/follow-up limits. |
| `answer-group-NNN-attempt-N-request.json` | Durable marker for a model answering attempt. |
| `answer-group-NNN-attempt-N.json` | Original response and intake diagnostics. `staged_unvalidated` is structural acceptance only. |
| `answer-group-NNN-attempt-N-verification-request.json` | Requested follow-up operations recorded before execution. |
| `answer-group-NNN-attempt-N-verification.json` | Verification results, deterministic minimum comparisons and cached reading/budget state. |
| `draft_request.json` | Combined proposals, requirements, layout and sources sent to gate/writer. |
| `answer_review.json` | Code-generated gate acceptance/withholding reasons and receipts, not human approval. |
| `evidence_selection.json`, `attachment-manifest.json` | Supporting-document selections and attachment planning. |
| `historical_page_readings.json`, `historical_context_checks.json` | Historical extractions and checked question/answer/role relationships. |
| `ocr-HASH.json`, `scan_checks.json` | OCR words/confidence/coordinates and independently checked scan quotations. |
| `evidence_tool_trace.json`, `reading_budget.json` | Discovery operations and resource use; not a complete reasoning transcript. |

All these files can contain confidential evidence. Keep them out of Git, public logs and external
delivery. Do not edit readable copies to authorize answers or bypass immutable source hashes.
`progress.jsonl`, immediately above `readable/`, records content-free live progress.

### Dated historical prefills and supporting-document planning

**Reading conflicts (agent v19, gate/writer v14):** neither OCR nor the image model is the
preferred transcription. When localized answer readings differ, `candidate_answer` is null;
both original readings and the original citation remain in the private evidence handoff.
Discovery instructions require targeted inspection of identity-linked current evidence before
finishing evidence collection, within existing tool/model/time limits. Unchecked OCR or a
two-to-one vote is not verification.

A text/identifier proposal can resolve a disputed reading through
`historical_basis.reading_resolution`: `subject`, a checked historical Name `subject_context`
for the same packet/role, `field_label`, and a current corroborating `citation`. Include both
the original historical answer citation and current citation in the proposal. Gate and writer
independently require the exact historical name and explicit field/value linkage in an
independent current source. Native quotes are resolved against the PDF; scanned current quotes
need an existing successful subject-aware OCR/image `verify_scan_quote` receipt, with source,
render, artifact and confidence rechecks. Either original reading can win, but not a guessed
third value. Unknown names/aliases, conflicting corroboration and unverified current OCR remain
unresolved; this bounded path does not resolve narrative/control disputes or authorize personal
acts, signing or financial extrapolation.

The summary distinguishes **FILLED AFTER RECONCILIATION** from **LEFT BLANK**, retains both
readings, identifies the corroborating citation and provides an explicit verification action
for unresolved fields. A model's candidate explanation is not presented as the final disposition.
These changes apply to new runs; already published packets and their summaries are unchanged.
Paid semantic evaluation cases are opt-in, not part of offline correctness results.

Approved historical applications from **other municipalities** are valid reference inputs.
Use `agent-run --historical-manifest ... --issuer ...` to supply a hash-bound reference archive;
the Broward convenience script still deliberately selects its one approved Broward packet.
Question matching uses meaning, entity, conditions, role and period, not identical wording.
The model's correspondence and uncertainty are recorded for review, not treated as independently
verified semantic equivalence. Incompatible contexts, contradictions and new personal acts block
reuse. Exact text parts may be combined only from checked receipts in the same packet/role.

Under `answer_first_review`, firm years established and representative years with firm may
increase by completed calendar anniversaries from an explicitly evidenced signing date in that
same packet. Python performs the arithmetic using the fixed `--as-of` date or run-creation UTC
date, not a model's calculation or filename. February 29 uses February 28 in non-leap years.
Missing, ambiguous, conflicting or future dates prohibit an increment; an unchanged historical
candidate may still be offered for review. The summary records baseline, signing evidence,
calculation date and operating/employment-continuity concern. Old signing dates are metadata,
never permission to fill current signature dates. Headcount is copied unchanged, with original
approximation qualifiers and a current-review flag. Financial amounts and reporting periods are
never extrapolated.

The source catalog now exposes the specifically approved supporting families for bios, agency
performance, Bloomberg tables, sustainability and other business evidence, as well as the earlier
financial/registration sources. It does not expose arbitrary folders or the restricted financial
tier. Archived cover letters remain outside automatic inclusion; an unsigned/new letter is a
human/generated-component gap. `plan_supporting_document` records inclusion/exclusion/gap reasons,
linked questions and period/entity limitations. The private `attachment-manifest.json` and reviewer
summary retain these decisions; unselected documents without a supplied rationale are explicitly
reported as such, not described as deliberately irrelevant. They are never merged into the packet.
Physical inclusion does not establish financial eligibility or satisfy every checklist criterion.

Existing trusted reviewer assessments can be passed to a fresh run:

```bash
./scripts/run_broward_demo.sh --requirement-assessments outputs/reviewed-assessments.json
```

The same flag is available on `agent-run`. Input shape is `{"assessments": [...]}`, containing
`RequirementAssessment` records with exact application hash, requirement ID/wording, reviewer,
reason, applicability and, where needed, evidence-backed criteria/dependencies. This is explicit
local review input, not a model-generated approval channel. Invalid form versions/wording fail
explicitly. Do not copy assessments from a differently mapped form or mark unchecked historical
options not applicable without an actual review decision. Inspect supplied inputs before authorizing
the paid run; canceling preflight still makes no model calls.

Offline tests exercise the actual grouped gate/writer/publication path with synthetic data.
They do **not** establish model grounding or a new real-document completeness count. Six synthetic
semantic cases can be run separately with explicit paid opt-in:

```bash
BD_RUN_HISTORICAL_EVAL=1 .venv/bin/python -m pytest -q \
  tests/integration/test_historical_equivalence_eval.py
```

Set the authorized `BD_FOUNDRY_ENDPOINT` and `BD_FOUNDRY_DEPLOYMENT` first. The default offline
suite skips these cases; skipped cases are not a model-quality pass.

```bash
bd-packet agent-run --root /path/to/synthetic-root \
  --blank "bd_agreements/Blank/Form.pdf" \
  --endpoint https://bd-application-builder-resource.openai.azure.com/openai/v1 \
  --deployment gpt-6.1-sol --as-of 2026-09-30 --allow-paid
```

The run uses the same full-questionnaire profile as the Blob-backed runtime: 60 agent turns plus at most five page-mapping calls and 20 independent scanned-page readings (85 model calls total), with explicit evidence/tool/time bounds described above. Output is an incomplete draft under `<root>/outputs/agent-runs/<run-id>/`, never for submission.

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

The [demo](examples/proposal_demo.py) creates four deterministic, fictional PDFs using the existing pinned ReportLab dependency: a blank questionnaire, company identity, conflicting contact record, and July financial report. You do not supply or maintain any test documents. It creates them beneath a unique Git-ignored `outputs/proposal-demo-.../synthetic-root/`, **never reads your real document folders**, and does not create Excel workbooks.

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

`PacketPagination` resolves 1-based page references from ordered form/supplement/evidence sections. It rejects missing/out-of-range/wrong-role references and does not accept reviewer-summary sections. Internal source/version/page citations remain unchanged. **This earlier example uses hypothetical pagination** to demonstrate the rule; the newer [controlled draft writer](#controlled-draft-completion) now supplies actual assembled ordering and supplemental/evidence references. The helper alone does not verify PDF contents, source hashes or evidence support.

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

Broader forms, cross-page interpretation and automatic semantic/source approval remain unfinished. The later [scanned-evidence increment](#machine-cross-checked-scanned-evidence) supports narrow scalar drafts through independent OCR/image agreement, not general scanned-document approval. The [controlled draft writer](#controlled-draft-completion) implements bounded deterministic assembly, not automatic promotion of visual form-mapping output. A passing geometry evaluation does not approve facts, eligibility or a generated packet.

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
- `AnswerProposal`: a requirement ID, explicit outcome, typed value, source/page/quote citations, optional claimed reporting period, and model confidence. Citations may be native-text spans or an OCR citation bound to the exact source/render/artifact and OCR word range. A proposed answer requires citations and confidence. Missing/conflicting evidence, unreadable forms, unsupported requirements, unresolved signers, and signing deferrals require an explanation and no answer value.
- Typed values: text, string identifiers preserving leading zeros, boolean, ISO date, explicit-unit money, or attachment source identity. Money uses a plain decimal string at the JSON boundary and exposes `Decimal` internally; floats, comma formatting, exponents, and non-finite values are rejected. Attachment proposals do not accept arbitrary file paths or destinations.
- `check_proposal`: checks requirement identity, value kind/units, attachment citation identity, and exact native-text source/page/quote resolution through the existing read-only inventory. OCR citations remain explicitly review-required and are released only by the separately validated draft writer and human OCR confirmations. Unknown native citations or altered native quotes reject the proposal; source mutation and I/O failures remain technical exceptions. A requested period is compared to the proposal's claim, but neither a claim nor filename proves the actual reporting period.

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
