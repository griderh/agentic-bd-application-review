# SharePoint intake poller spike

Status: offline prototype implemented and verified. No live SharePoint, queue, worker,
or scheduled job is implemented by this spike; live acceptance remains open.

Parent: [development plan](development-plan.md). The business scope remains
[Phase 1](../Broker-Dealer%20Packet%20Automation%20Phase%201%20Scoping%20Document.md).

## Agreed workflow

Users drag and drop blank PDFs into the future SharePoint intake library. The poller
observes the same item version in two separate checks before queueing it. This is a
safety heuristic, not proof editing is finished. At startup, existing eligible files
are included. A queue message means **Queued**, not Processed. The future worker
must process at most one packet at a time; files can wait together in the queue.
Edits after queueing are held for review, not automatically submitted again.

## Reviewer checklist

The checked items below apply **only to the synthetic local prototype**. Unchecked
items are not implemented or verified. The order is a proposed sequence, not a
promise that every design decision has already been made.

### 1. Offline prototype — complete

- [x] Define a poller with separate source, queue and state boundaries.
- [x] Enumerate an initial synthetic backlog and paged changes; track pending files
  across polls and require two observations of the same version.
- [x] Build a versioned message containing library ID, item ID, version and a stable
  idempotency key, without a filename or document content.
- [x] Track queued items and flag later changes or deletions for review.
- [x] Use local SQLite state and reject overlapping local polls; handle expired
  simulated cursors and preserve prior queued records.
- [x] Test restart, paging, queue-send uncertainty, duplicates, changed inputs,
  damaged state, limits and concurrent local polls.
- [x] Document and run a synthetic demonstration; run targeted tests and static checks.

### 2. Decisions and access details — needed before live integration

**SharePoint library**

- [ ] Identify the tenant, site and intake document library; obtain stable site and
  drive/library IDs and identify an owner for access and operational decisions.
- [ ] Decide whether the poller watches the entire library or specified folders,
  including whether nested folders count. Define how files moved into or out of
  the intake area are handled.
- [ ] Confirm accepted file types and limits, including whether each uploaded PDF
  represents one complete packet request. Decide how non-PDFs, empty, unreadable,
  encrypted or oversized files are reported without losing the request.
- [ ] Agree on the two-check settling interval and what happens if a file keeps
  changing, is deleted or moved, or is checked out. Two unchanged checks reduce
  premature processing but do not prove the user has finished.
- [ ] Confirm the first activation includes eligible existing files, as agreed;
  review that backlog and any previously processed items before enabling it.
- [ ] Decide retention and cleanup rules, who may remove files, and how users
  resubmit a corrected document after a queued or completed request.

**Queue, state and worker**

- [ ] Select the Azure Storage account, queue name, environment and region; identify
  the owning team and confirm the network path and access controls.
- [ ] Decide queue message retention, visibility timeout and renewal, retry limits,
  poison-message handling and operator recovery procedures. Verify choices against
  expected packet-building duration; don't rely on FIFO ordering.
- [ ] Select a durable shared state store for candidates, change cursor, queued
  versions, review exceptions and lease/ownership; define retention and access.
- [ ] Decide where the worker's durable idempotency and single-active-packet
  coordination live, including recovery if the worker dies or a lease expires.
- [ ] Agree what the worker does if the queued version is unavailable or changed
  before it can be snapshotted. It must not silently use a different version.

**Identity, status and operations**

- [ ] Identify the job's managed identity and obtain IT approval for the minimum
  Microsoft Graph and Azure Storage permissions, including explicit resource grants.
  Verify the chosen Graph endpoints work with those permissions.
- [ ] Decide which SharePoint status columns users see and who may update them.
  Distinguish at least waiting/queued, processing, completed and failed or review
  needed; agree the owner and meaning of each transition.
- [ ] Decide who receives operational alerts, who can retry or resolve exceptions,
  and what may appear in logs without exposing document contents or personal data.

### 3. Implement and verify the SharePoint source

- [ ] Add validated configuration for the approved tenant, site, library and
  optional folder scope; reject missing or inconsistent configuration explicitly.
- [ ] Implement authenticated Microsoft Graph discovery and map real item IDs,
  versions, files, folders and deletions into the poller's source contract.
- [ ] Follow paginated initial enumeration and delta changes; validate continuation
  URLs before use, protect cursor values, and persist the cursor only after work is
  safely recorded. Do not log filenames, tokens or document contents.
- [ ] Re-read pending item versions on later polls even when the delta feed does
  not repeat unchanged items. Handle 429/retry-after, transient failures, invalid
  responses and expired cursors with bounded recovery and explicit failure.
- [ ] Reconcile moves, deleted items, version changes and full resynchronization
  without silently omitting existing work or treating edited items as completed.
- [ ] Add offline mocked-boundary tests for configuration, authentication and
  pagination, throttling, expired cursors, scope changes and error cases.

### 4. Implement queue publication and durable coordination

- [ ] Add a real Azure Storage Queue sender using the approved identity and
  configuration. Preserve the minimal, versioned message contract; no document
  bytes, filenames, download URLs, credentials or sensitive metadata in messages.
- [ ] Replace local SQLite as production state with the selected durable shared
  store. Protect state and cursor updates against concurrent scheduled executions.
- [ ] Implement an atomic lease with expiry and fencing, or an equivalently verified
  ownership mechanism, so an old execution cannot overwrite a newer checkpoint.
- [ ] Handle queue-send failure and ambiguous success without advancing past
  unsent work. Test crash windows before and after sending and checkpointing.
- [ ] Document that queue delivery can duplicate messages; preserve stable keys
  across retries and require durable consumer-side deduplication.
- [ ] Test overlapping jobs, lease loss, restart, duplicate messages, state-store
  failures and bounded backlog handling. A local SQLite lock is not cloud proof.

### 5. Worker and user-visible status

- [ ] Implement or integrate a queue consumer that durably deduplicates messages
  and enforces **one packet in progress at a time**, including after crashes or
  overlapping worker instances.
- [ ] Fetch and verify the exact queued version; safely snapshot the original for
  the existing packet builder. Flag unavailable or changed versions for review.
- [ ] Define and implement queue acknowledgment only after the agreed durable
  handoff; handle long jobs, visibility renewal, retries and poison messages.
- [ ] Implement agreed SharePoint status updates with version/concurrency checks.
  Queue publication may mark Queued; only the worker may mark completion after
  successful processing. Make failed status writes observable and recoverable.
- [ ] Exercise the complete status lifecycle, duplicate delivery, worker crash,
  input changes and reviewer recovery with synthetic test documents.

### 6. Scheduled job, security and live acceptance

- [ ] Package the poller for a finite Container Apps job; configure the approved
  `* * * * *` one-minute schedule, timeout, retries and safe overlap behavior.
  Scheduling is approximate, not a one-minute completion guarantee.
- [ ] Configure the approved network, managed identity, least-privilege access,
  secure configuration and non-content operational logging. Do not include
  business documents, outputs or credentials in the container image.
- [ ] Configure alerts for failed or missed polls, stale cursor/lease, queue backlog,
  repeated failures and review-needed cases; document an operator runbook.
- [ ] Test with an approved synthetic SharePoint library and real queue: initial
  backlog, drag-and-drop, status, retries, restarts and single-worker processing.
- [ ] Review results with IT and the sponsor; explicitly authorize any real-document
  acceptance. Record code completion, offline verification and live acceptance
  separately, including failures, blockers and next action.

**Current blockers:** the library, queue, shared state, identity, status schema,
retention, worker and job are not yet established for this integration. The
offline prototype cannot be scheduled as a production poller without those pieces.

**Next action:** gather the SharePoint site/library and Azure Storage Queue details
with IT, then agree the status, retention and worker-handoff decisions in section 2.

## Verification

- `.venv/bin/python -m pytest -q tests/unit/test_intake_poller.py`: 15 passed;
  the same 15 passed with `.venv313/bin/python`.
- `.venv/bin/python -m bd_packet_builder.intake_poller` queued one synthetic item
  on the second poll without network access or persistent output.
- `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`, `.venv/bin/mypy`,
  `.venv313/bin/python -m mypy --python-version 3.13` and `git diff --check` passed.

These are offline behavior checks, not evidence that Microsoft Graph, Azure Storage
Queue, or the scheduled Azure job works in the target tenant.

## Operational boundaries

Queue delivery is at least once: a send that succeeds just before a crash can be
repeated. A future consumer must deduplicate with the message's stable identifier.
Local state is not a distributed lock or production state store. The future worker
must validate that it retrieves the exact queued version and report changes or
deletions; it must not silently process a replacement. No files are marked Processed
by the poller. SharePoint-visible status and retention are future work.

The future Graph adapter must validate continuation links against the approved Graph
origin and endpoint, handle throttling and expired cursors, and protect cursor values
from logs. Selected permissions require explicit resource grants; their support for
the exact chosen endpoints and identity must be validated with IT. Production needs
shared durable state, overlapping-job lease/fencing, alerting, queue retention and
poison handling, and a serial, idempotent consumer before live use. The worker must
read and snapshot the queued source version under approved permissions. A one-minute
job schedule is a target, not a delivery guarantee.

Microsoft references: [Graph delta](https://learn.microsoft.com/en-us/graph/api/driveitem-delta?view=graph-rest-1.0),
[Container Apps jobs](https://learn.microsoft.com/en-us/azure/container-apps/jobs),
[selected SharePoint permissions](https://learn.microsoft.com/en-us/graph/permissions-selected-overview),
and [Storage Queue](https://learn.microsoft.com/en-us/azure/storage/queues/storage-queues-introduction).
