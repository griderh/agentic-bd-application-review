# Broker-Dealer Packet Automation: Phase 1 Scoping Document

Oct 16, 2026 · @Hansen Grider

## 1. Purpose and executive summary

Phase 1 delivers an agent that takes a blank broker-dealer approval packet, completes it from current InspereX records, appends the required support documents, and returns one finished PDF to the signatories for review.

- **Problem:** InspereX completes a few of these packets each week. One employee does the work today and will not be here in January.
- **Solution:** An agent on Microsoft Foundry fills the issuer's own PDF forms, selects the latest support documents from designated network folders, and merges everything into a single submission-ready packet.
- **Human control:** The agent never signs and never sends to the issuer. Every signatory named on the forms, including the chief compliance officer where named, reviews the packet before it goes out.
- **Reviewer aid:** A separate internal summary lists each answer, its source, what changed from the prior packet, and anything the agent could not resolve.
- **Phase 1 target:** Field-level accuracy against held-out completed packets, with zero fabricated values (Section 13).
- **Timeline:** A bare-bones proof of concept on local copies of the documents in 2 to 3 weeks, so the business can see the agent logic before access decisions are final. Production readiness is needed before January 2027.

## 2. Background and business problem

InspereX is repeatedly asked by public-fund issuers and counterparties to certify the same facts about the firm in different wording, and the manual work is about to lose its only owner.

- **Volume and ownership:** A few packets per week, handled by one employee who leaves in January. The business owner does not want to take the work on.
- **Content:** Every packet asks about the firm: trading volume, inventory and dealer status, capital, clearing, banking, regulatory disclosures, and representative credentials. Wording and rubrics differ by issuer. Answers change little from year to year, apart from figures such as notional volume.
- **Existing record:** InspereX keeps completed packets from prior years on a shared drive. The business owner considers these the best source for how each question has been answered, because Power BI holds much of the underlying data but is hard to extract from.
- **Financial support:** The latest FOCUS report is uploaded monthly (a new report appears on the 17th). Audited financials are annual. Most support material lives on shared drives, but not in one place.
- **Recurring exception:** About one request in six or seven asks for financial reporting beyond the FOCUS report. Sharing that is a business decision, so the agent will have no access to that tier.
- **Request types:** For Phase 1, RFIs and RFQs are treated the same as broker-dealer approval applications.

## 3. Scope

Phase 1 covers the full path from a blank issuer packet to a reviewed-ready PDF, and stops at the reviewer's desk.

| Area | In scope for Phase 1 | Out of scope (later phase or never) |
| --- | --- | --- |
| Intake | Blank issuer documents, most likely PDF, fed to the agent manually | Email monitoring, browsing issuer sites to pull documents (Phase 3, if an MCP approach proves feasible) |
| Completion | Every question and field on the issuer's forms, including boilerplate attestations, filled from approved sources | Applying signatures. Entering anything the agent cannot source |
| Support documents | Selecting the latest version of each required document from designated folders and appending it | Regenerating web printouts such as the SIPC member list (Phase 3) |
| Output | One merged, submission-ready PDF packet plus a separate internal reviewer summary | Sending the packet to the issuer |
| Review | Notifying the signatories that a packet is ready | Approval workflow tooling, e-signature |
| Data | Designated network folders, read-only. Prior packets for wording reference | Power BI extraction. Access to financial reporting beyond FOCUS and audited financials |
| Document types | Broker-dealer approvals, RFIs, RFQs about the firm | NDAs, contracts, or other legal documents |

**Boundary rule:** If a request asks for information outside the approved source set, the agent flags it for the reviewer and does not answer.

## 4. Stakeholders and roles

The business owner has final sign-off, and the signatories on each form are the review gate.

| Role | Who | Responsibility |
| --- | --- | --- |
| Business owner, sponsor | John Tolar | Final sign-off on scope, POC, and go-live. Signatory on many packets |
| Technical sponsor | Hansen Grider | Design, build, evaluation |
| Technical sponsor | Daria Bidnyk (IT) | Platform, access, and security alignment |
| Reviewers | Each signatory named on the form, including the chief compliance officer or designee | Review the full packet and sign. Not involved in building |
| Folder owners | To be named (Finance, Compliance, Sales, Operations) | Keep designated folders current and correctly named |

## 5. Analysis of the example packets

Both issuer packets mix firm-written answers, attestations, and pass-through attachments, and only part of each needs the agent's judgment. Page counts and contents below come from the files supplied.

**Packet anatomy**

| Packet | Pages | Issuer-supplied forms | Support attachments |
| --- | --- | --- | --- |
| City of Carrollton, TX (completed and signed) | 72 | Cover letter, submission checklist, 4-page questionnaire (8 sections), certification, Texas PFIA acknowledgment, evaluation criteria (City scoring, no input needed) | Audited statement of financial condition (p10 to 25), about 32 pages with no extractable text (p26 to 57, likely the attached FOCUS report, to confirm), SIPC member list printout dated 9/4/26, three representative bios, standing settlement instructions, public-fund collateral, agency market snapshot |
| Carrollton forms only (unsigned) | 8 | Checklist, questionnaire, certification, PFIA acknowledgment, evaluation criteria | None. This is the filled form set before signing |
| New Mexico State Treasurer's Office (NMSTO) | 41 | Cover letter, 3-page application, campaign contribution disclosure (3 copies), acknowledgment and certification (3 copies, one per signer) | Representative bio, agency snapshot, public-fund collateral, audited financials (p30 to 41), about 6 pages with no extractable text |

**What the agent must handle, by field type**

| Field type | Examples seen | Source for the answer | Risk |
| --- | --- | --- | --- |
| Static firm identity | Legal name, address, FINRA CRD number, SEC number, year established, parent | Governed fact sheet | Low |
| Representative roster | Names, titles, CRD numbers, phones, emails, years in fixed income | Fact sheet plus bios | Medium. Rosters change by issuer |
| Regulatory disclosures | 10-year FINRA disclosure yes/no for firm and each representative | Latest compliance-approved records | High. Reviewer must confirm |
| Time-varying numbers | Firm-wide Treasury and Agency volume, excess net capital, line of credit | FOCUS report, fact sheet, prior packet | High. Wrong period is the main failure |
| Short narrative | Market sectors served, banking relationships | Prior packets as wording reference | Medium |
| Checkboxes | Fully disclosed clearing, inventory dealer, primary dealer, SIPC | Fact sheet | Medium. Flattened PDFs make detection harder |
| Attestations | Read and understood policy, PFIA acknowledgment, campaign contribution disclosure | Prior wording, standard answers | Medium. Signatory reviews |
| Third-party contacts | Three public-sector references | Prior packet | Medium. Stale contacts |
| Attachment selection | Checklist of required documents | Support folders | Medium. Version selection |

**Findings that shape the design**

1. **Inconsistent facts across packets.** The main phone is 561-361-1100 in the Carrollton questionnaire and the NMSTO letterhead, and 561-361-1000 on the NMSTO application. A title for the business owner appears as "Head of Institutional Sales and Trading" in one packet and "Head of Fixed Income and Institutional Sales" in another. A governed fact sheet and a consistency check remove this class of error.
2. **Period selection is an active risk.** The Carrollton questionnaire cites the July 2026 FOCUS report and its excess net capital figure, with signatures dated 10/9/2026. "Latest" must be defined in code (Section 6), not left to the model.
3. **Attachments carry their own dates.** The SIPC printout is a dated web page capture. A stale capture is a visible defect, so each attachment needs an as-of date in the reviewer summary.
4. **Forms are flattened.** Extracted text shows checkbox glyphs but no form-field structure, so the agent needs layout and vision handling to find fields and verify what it marked.
5. **Signer-specific copies.** NMSTO repeats forms once per signer. The agent must read the signer list and duplicate pages accordingly.
6. **The supplied files are completed packets, not blanks.** Phase 1 evaluation needs the matching blank originals from each issuer.

## 6. Source documents and version selection

The agent reads only from designated, named folders, and picks the current version of each document with deterministic code, not model judgment.

| Source | Used for | Cadence | Folder owner | Location |
| --- | --- | --- | --- | --- |
| Governed fact sheet (new) | Firm identity, rep roster, CRD numbers, standard answers, annual volume figure | Reviewed on any change and at least annually | To be named | To be created in Phase 1 |
| FOCUS report | Excess net capital, financial condition evidence | Monthly (new report on the 17th) | Finance | To be confirmed |
| Audited financial statements | Required attachment, capital and financing answers | Annual | Finance | To be confirmed |
| FINRA and regulatory documents | Disclosure answers, attached disclosure documents | On change | Compliance | To be confirmed |
| SIPC evidence | Required attachment | Per submission | Compliance | To be confirmed |
| Representative bios and resumes | Required attachment | On change | Sales | To be confirmed |
| Standing settlement instructions | Required attachment | On change | Operations | To be confirmed |
| Firm collateral and market snapshot | Optional attachments | Periodic | Marketing | To be confirmed |
| Prior completed packets | Wording and precedent only | Per submission | Sales | Shared drive, to be located |

**Proposed version rule (for John's approval)**

1. Each designated folder uses a naming convention that carries the period or effective date, for example `FOCUS_2026-09.pdf`. The agent parses the date from the name and falls back to file metadata only to flag a mismatch.
2. The agent selects the single document with the latest period. Ties or unparseable names stop the run for that item and produce a flag.
3. Two reporting periods in one folder are expected, so the selection is by period date, never by modified time or folder order.
4. A document older than one cycle is attached with a staleness flag, not blocked. The business owner stated that a one-month lag on the FOCUS report is acceptable. Proposed flag thresholds: FOCUS older than 2 monthly cycles, audited financials not for the most recent fiscal year-end.
5. The agent records the file name, period, and path of every document used.

Financial reporting beyond the FOCUS report and audited financials sits outside the agent's folders. When a request asks for it, the agent flags the request and the business owner decides.

## 7. Functional requirements and agent workflow

The agent runs one packet per run, in a fixed sequence, and ends with a file for the reviewer rather than an action in the world.

&#91;embedded content: agent workflow · 10 steps, 1 branch\]

A field without a current source is left blank and flagged. The agent's last step is saving the packet and notifying the signatories.

| ID | Requirement | Phase 1 |
| --- | --- | --- |
| FR1 | Accept one or more blank issuer PDFs from an input folder or upload | Must |
| FR2 | Classify each page: form to complete, attestation, checklist, instructions, or issuer-only content | Must |
| FR3 | Detect fields, checkboxes, and tables on flattened PDFs using layout and vision, and fall back to native form fields when present | Must |
| FR4 | Answer each field from the fact sheet and current source documents first, then prior-packet precedent for wording. Record source and confidence per answer | Must |
| FR5 | Write answers onto the issuer's original PDF, preserving its layout | Must |
| FR6 | Leave signature fields for the signatories. The agent never applies a signature | Must |
| FR7 | Read the issuer checklist, select the latest version of each required document, and append it in the checklist order | Must |
| FR8 | Produce one merged packet PDF with a page index and bookmarks | Must |
| FR9 | Produce a separate internal reviewer summary (Section 9) | Must |
| FR10 | Flag and leave blank any field with no source, conflicting sources, or no precedent. Never estimate | Must |
| FR11 | Run a consistency check across the packet: names, titles, phones, CRD numbers, dates, and figures | Must |
| FR12 | Duplicate signer-specific pages for each signer listed on the form | Should |
| FR13 | Notify the signatories that the packet is ready (Section 10) | Must |
| FR14 | Archive inputs, outputs, summary, and the source versions used under issuer and date | Must |
| FR15 | Log every run with inputs, sources, model version, and flags | Must |
| FR16 | Detect requests beyond the approved source set and flag them for the business owner | Must |

## 8. Human review, controls, and guardrails

The agent can read approved folders and write drafts. Only a signatory can approve and only a person can send.

| Control | Rule |
| --- | --- |
| Review gate | Every packet is reviewed in full by each signatory named on the forms, including the chief compliance officer or designee where named. Nothing is submitted without that review |
| No external send | The agent has no ability to email or upload to an issuer |
| No signing | Signature fields stay blank. Dates beside signatures stay blank unless the business owner decides otherwise (open item) |
| Read-only sources | Folder access is read-only and limited to designated paths. The agent writes only to the output and archive locations |
| Flag, do not guess | A value with no source, a conflict between sources, or a new question with no precedent is left blank and flagged |
| Sourced values only | Numbers, dates, names, and identifiers are copied from a retrieved source and cited in the summary. The model does not generate them |
| Prior packets are wording only | Facts always come from current documents. A prior packet can suggest phrasing but not a value that has a current source |
| Restricted tier | Financial reporting beyond FOCUS and audited financials is not placed in agent-accessible locations |
| Untrusted input | Text inside issuer PDFs is treated as data. Instructions found in a form are ignored and flagged |
| Traceability | Each run stores inputs, outputs, source versions, model version, and reviewer notification for audit |

## 9. Output specification

Each run produces two files: the packet, which is the deliverable, and a reviewer summary, which I recommend as a minimum companion.

**File 1: Submission packet (PDF)**

- The issuer's own forms, completed, in the issuer's order
- Support documents appended in the order of the issuer's checklist, each latest-version
- Signature fields left blank, with no other open fields except those flagged
- A page index and bookmarks per section
- Name pattern: `Issuer_PacketType_YYYY-MM-DD_RunID.pdf`

**File 2: Reviewer summary (PDF, 1 to 3 pages, internal only)**

The summary exists so a signatory can review in minutes instead of reading 70 pages cold. It is never sent to the issuer.

| Block | Content |
| --- | --- |
| Needs your attention | Flags first: blank fields, conflicts, stale attachments, requests beyond the source set |
| Signature locator | Each page and field where a signature or date is needed, by signer |
| Changed from last packet | Fields whose answers differ from the most recent prior packet for the same issuer, or the nearest equivalent |
| Answer register | Each filled field, its value, and source file with period |
| Attachments | Each document appended, its period or as-of date, and any staleness flag |
| Consistency check | Results across names, titles, phones, CRD numbers, and figures |

Both files are saved to a pending-review folder and the inputs, outputs, run log, and source versions used are copied to the archive folder at the end of the run.

## 10. Reviewer notification and delivery

I recommend saving outputs to a pending-review location and pushing a short notification with the link to each signatory, because a file on a drive alone does not tell anyone it exists.

| Option | How it works | Fit |
| --- | --- | --- |
| A. Teams message | Agent calls a workflow that posts a message with the link and the top flags to each named signatory | Recommended. Immediate, linkable, no mailbox side effects |
| B. Outlook notification | Agent drafts or sends an internal email to the signatories with the link. It never addresses the issuer | Acceptable alternative. Confirm that internal sending is allowed |
| C. Pull only | The reviewer opens the agent in M365 Copilot and asks for pending packets | Useful as a complement, not as the alert |

**Who is notified:** the signatories named in the forms, resolved against a maintained list of names and addresses in the fact sheet, plus the requester. If a signatory cannot be matched, the run flags it and notifies the business owner.

**Boundary:** The notification path is internal only. The person who submits to the issuer does so manually after review, which preserves the requirement that nothing is sent automatically.

## 11. Architecture and platform recommendation

I recommend Foundry Agent Service for the agent, model, evaluation, and publishing, with a small set of dedicated Azure compute tools for the deterministic PDF and file work, published to Teams and Microsoft 365 Copilot as the front door.

&#91;embedded content: target architecture · 6 components\]

The agent reads folders through the tool layer and writes only to the output folders. Reviewers get a notice and pick up the packet there.

**Hosting options**

| Option | Description | Assessment |
| --- | --- | --- |
| A. Everything inside Foundry | Agent, model, and all file logic as agent tools or prompts | Fastest to start. Weak for PDF manipulation and version selection, which should be tested code, not model behavior |
| B. Foundry agent plus dedicated Azure tools | Agent and model in Foundry. PDF, file-selection, and consistency tools as Azure Functions or Container Apps in your virtual network | **Recommended.** Keeps reasoning in the agent and anything that must be exact in code. Evaluation, tracing, and publishing stay in Foundry |
| C. Fully custom on Azure | Own orchestration on App Service or AKS with a model endpoint | More to build and operate. Gives up Foundry's evaluation and publishing for no Phase 1 gain |

The tool split matters here because the failure modes are exact ones: the wrong FOCUS period, a mis-placed overlay, a missed checkbox. Those belong in code with unit tests.

**Network and data location.** Azure uses the term virtual network, not VPC. Foundry Agent Service supports a [standard setup with private networking](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks) that injects the agent runtime into a subnet you own, uses customer-owned storage, and puts the endpoint behind a private endpoint. The model itself is an Azure service reached over that private path, not a server inside your network, so describe it to IT as private connectivity to a Microsoft-hosted model. IT should confirm the region and the exact setup. Because the packet contents are public, Phase 1 does not need the strictest tier, but the standard setup costs little extra at design time and is hard to retrofit (for hosted agents, virtual network injection must be set when the Foundry account is created).

**Network drive access.** Do not assume a Foundry agent can read a file share directly. Two workable patterns: reach the share through your virtual network over VPN or ExpressRoute from the tool layer ([networking options](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/networking-options) lists on-premises access this way), or sync the designated folders to a SharePoint library or Azure Blob container that the tools read. The sync pattern is simpler to secure and to audit. This is the main infrastructure dependency and needs IT input.

**Front door.** Publishing to Microsoft 365 Copilot and Teams [reached general availability on June 10, 2026](https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-june-2026/), and a tenant admin approves the published agent in the Microsoft 365 admin center ([publishing steps](https://learn.microsoft.com/en-my/Azure/foundry/agents/how-to/publish-copilot)). Copilot is a good place for requesters and reviewers to start a run, check status, and open outputs. A 70-page packet takes longer than a chat turn, so the run should be asynchronous, with the Teams notification in Section 10 as the completion signal.

**Model choice.** Foundry offers several model families. Benchmark two or three on the held-out packets in Phase 1, especially for field detection on flattened pages, and pick on measured accuracy and cost.

## 12. Data governance, security, and retention

The business owner's position is that packet content is public, so sharing it with a model inside the Azure tenant is acceptable. Two checks and one retention question remain.

| Topic | Position for Phase 1 |
| --- | --- |
| Data classification | Packet content is treated as public. Compliance should confirm two exceptions that appear in the examples: standing settlement instructions (account-level detail) and representative direct phone numbers and emails |
| Model data handling | Use a Foundry model deployment in the InspereX Azure tenant. IT confirms the data-handling terms for the chosen model, region, and abuse-monitoring settings |
| Identity and access | Managed identity for the agent, read-only on designated folders, write only to the pending-review and archive locations. Separate identities for read and write are preferred |
| Restricted tier | Reporting beyond FOCUS and audited financials is not reachable by the agent identity |
| Audit | Each run logs input hash, source files and versions, model and prompt version, output hash, flags, and notification recipients |
| Retention | Anything sent to an issuer is retained, as stated by the business owner. Whether drafts, reviewer summaries, and run logs fall under books-and-records rules is an open item for Compliance |
| Fact sheet control | Named owner, change log, and review at least annually. A change to a disclosure answer requires Compliance approval before it enters the fact sheet |

## 13. Evaluation plan and Phase 1 success metrics

Phase 1 passes if the agent fills a high share of fields correctly on packets it has not seen, and fabricates nothing. Thresholds below are proposals for the business owner to confirm.

**Method.** Use completed packets as ground truth. For each test packet, blank its answers, run the agent, and score every fillable field against the completed answer. The agent's prior-packet library excludes the test packet itself, so the test is held out.

**Scoring labels per field**

| Label | Meaning | Counts as |
| --- | --- | --- |
| Correct | Value matches ground truth, correctly placed | Hit |
| Correct abstention | Field left blank and flagged because no current source exists, and ground truth agrees it needs human input | Hit for accuracy, miss for coverage |
| Incorrect | Value differs from ground truth, or placed in the wrong field | Miss |
| Fabricated | Value has no traceable source in the answer register | Fail. One occurrence fails the phase |

**Phase 1 metrics**

| Metric | Definition | Proposed target |
| --- | --- | --- |
| Fabricated values | Filled values without a source citation | 0 |
| Field accuracy | (Correct + correct abstentions) / all fillable fields | 95% or higher |
| Coverage | Fields auto-filled / all fillable fields | 85% or higher |
| Attachment correctness | Required documents present, latest version, correct order | 100% |
| Period selection | Correct version chosen in adversarial folder tests | 100% |
| Reviewer time | Minutes for a signatory to review a packet with the summary | Baseline to be measured, then target a reduction |
| Run time and cost | Wall-clock minutes and model cost per packet | Reported, no target in Phase 1 |

**Test set.** Two completed packets (Carrollton, NMSTO) are not enough to support accuracy claims. Add 8 to 10 prior-year packets from the shared drive, covering as many issuers as possible, and include these adversarial cases: two reporting periods in one folder, a missing required document, a conflicting phone number, a question with no precedent, and instruction text planted in a form.

## 14. Phase plan and timeline

The plan works backward from January, when the current owner leaves, and leaves two weeks for a parallel run against the human process. Dates are proposals that start from today, October 16, 2026.

&#91;embedded content: phase timeline · 4 phases, 3 milestones\]

- **Phase 0, prerequisites (Oct 19 to 30, in parallel with the POC):** Obtain blank issuer originals, 8 to 10 prior packets, folder locations and owners, and the written process from a few years ago. Request IT and Foundry setup.
- **Phase 1a, proof of concept (Oct 19 to Nov 6):** Run on local copies in a folder path set as a variable. Show the agent logic end to end to the business owner on his return: field detection, sourcing, attachment selection, merged packet, reviewer summary. Score against the held-out packets.
- **Phase 1b, hardening (Nov 9 to Dec 11):** Fact sheet, version rule in code, designated folder integration, Foundry deployment on private networking, Teams notification, archive, Copilot publishing with admin approval.
- **Phase 1c, parallel run (Dec 14 to departure in January):** Run every incoming packet through the agent alongside the current process. Compare and tune. Business owner decides go-live.
- **Phase 2:** Broader issuer coverage and rules learned from reviewer edits.
- **Phase 3:** Automated intake and web-sourced attachments, for example an MCP browsing tool for the SIPC member list or issuer portals, if feasibility and governance allow.

## 15. Risks and mitigations

The largest risks are a wrong-period document, delayed access to folders, and reviewers trusting a draft too much.

| Risk | Effect | Mitigation |
| --- | --- | --- |
| Wrong version or period attached or cited | Inaccurate certification to a public entity | Period parsed from file names, selection in tested code, staleness flags, adversarial tests |
| Folder locations and access delayed | POC and hardening slip | POC on local copies, access requests in parallel, sync pattern as fallback |
| Flattened PDFs resist field detection | Misplaced or missed answers | Vision plus layout approach, overlay tests across 3 or more issuers, summary-only fallback for unreadable forms |
| Reviewers approve without reading | An error is signed | Summary leads with flags and changes from last packet, spot audits, signatories remain accountable |
| Stale boilerplate repeated | Outdated disclosures certified | Fact sheet with named owner and annual review, Compliance approval for disclosure changes |
| Tacit knowledge leaves with the current owner | Unknown exceptions surface after January | Obtain the older written process, log each exception found into a rules library, parallel run |
| Unfamiliar issuer questions | Wrong or invented answers | Flag, do not guess. Track the share of unknown fields as a metric |
| Sensitive content in packets | Disclosure of non-public data | Compliance classification check on settlement instructions and direct contacts |
| Copilot publishing needs admin approval | Lead time delays rollout | Request approval early in Phase 1b |
| Two sample packets overstate accuracy | False confidence | Expand the test set to 8 to 10 or more packets before any go-live decision |

## 16. Assumptions, open items, and dependencies

Thirteen items need an answer or an owner, and the first four block the evaluation.

**Assumptions in this document**

1. Inputs are blank issuer documents, most likely PDF, fed manually in Phase 1.
2. The output is a finished PDF packet built from the issuer's own files with support documents appended.
3. Signatories, including the chief compliance officer or designee, review every packet. The agent never signs or sends to an issuer.
4. Packet content is public, subject to the two classification checks in Section 12.
5. Prior packets inform wording only. Facts come from current documents.
6. RFIs and RFQs follow the same pattern as broker-dealer approvals.
7. The process has not changed materially since the older written procedure was produced.

**Open items**

| # | Item | Suggested owner |
| --- | --- | --- |
| 1 | Blank originals of the Carrollton and NMSTO forms, and of other issuers' forms | Business owner, Hansen |
| 2 | 8 to 10 additional prior completed packets and the location of the shared drive | Business owner |
| 3 | The older written process, if it can be found | Business owner |
| 4 | Folder locations, owners, and naming convention for each source in Section 6 | Business owner, folder owners, IT |
| 5 | Approval of the version rule and staleness thresholds in Section 6 | Business owner |
| 6 | Whether dates beside signature lines stay blank or are filled | Business owner |
| 7 | How signatories on a form map to notification addresses, and who the chief compliance officer designee is | Business owner, Compliance |
| 8 | Internal notification channel: Teams message or Outlook email | Business owner, IT |
| 9 | Retention requirements for drafts, summaries, and logs | Compliance |
| 10 | Classification of standing settlement instructions and representative direct contacts | Compliance |
| 11 | Foundry subscription, region, private networking setup, and Microsoft 365 admin approval for publishing | IT |
| 12 | Network drive access pattern: VPN or ExpressRoute from tools, or sync to SharePoint or Blob | IT |
| 13 | Approval of Phase 1 metric thresholds in Section 13 | Business owner |
