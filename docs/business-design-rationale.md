# Why the Document Builder Combines AI with Controlled Software

## Purpose

This document explains why the application uses AI to interpret documents while relying on controlled software to validate proposals and perform document operations. It describes the intended design, not a claim that every capability is already implemented.

**The central principle: use AI for understanding and drafting, but do not make AI the sole authority over facts, files, permissions, or completion status.**

## Why not simply give the AI all the documents and ask it to complete the application?

A modern AI model can read text, interpret page images, and draft convincing answers. A detailed prompt can explain the task and tell it not to invent information. This can be useful for an early demonstration.

However, a convincing result is not necessarily a correct, complete, or safe result. The model can misunderstand a question, overlook a condition, use an outdated figure, or place an answer incorrectly. It can make these mistakes even when the instructions are clear.

For a business process, we need more than a completed-looking document. We need to know what evidence was used, what remains unresolved, which checks were performed, and whether the output is ready for human review.

The software around the model provides that control and visibility.

## 1. Instructions guide the AI; controls enforce important boundaries

A prompt tells the model what it should do. A software control limits what the application will accept or allow.

| Business expectation | How the design supports it |
| --- | --- |
| Select only one answer when a question permits one choice | Reject proposed answers containing multiple selections |
| Explain an "Other" selection | Require its description and associate it with the correct selected option |
| Leave signatures and signature dates for human signing | Keep those actions outside automated document completion |
| Preserve the original source documents | Restrict writing to approved output locations |
| Do not deliver a packet to an issuer automatically | Do not give the model an unrestricted external delivery capability |

These controls are not substitutes for good instructions. They provide a separate layer of protection when the model makes a mistake.

## 2. Understanding a page and editing it accurately are different tasks

AI can help recognize questions, answer choices, checkboxes, and areas intended for written responses. But recognizing a control does not guarantee that the correct control will be marked or that text will be placed legibly.

The intended division is:

- **AI proposes the interpretation:** what the question means, which options belong together, and where an answer may belong.
- **Software checks and executes document operations:** whether the proposed locations are valid, whether text fits, and how pages are written and assembled.
- **Rendered-output verification checks the result:** whether the produced document actually looks correct, rather than assuming that valid instructions produced a valid page.

For narratives, the design prefers a complete, readable answer on the form. When it will not fit and the issuer permits supplementation, the application should place a clearly labeled supplemental answer elsewhere and reference it from the form. It should not silently cut off text or make it unreadably small.

A supplemental answer and its supporting evidence serve different purposes: one contains the response; the other substantiates it.

## 3. Answers must be traceable to evidence, not merely plausible

An answer may sound reasonable while relying on the wrong source, the wrong reporting period, or only part of a qualification.

For each proposed answer, the design calls for a record of:

- The supporting source and its specific version.
- The relevant page or section.
- The reporting period, where applicable.
- Any conflicting evidence or unmet condition.

Software can check that a cited passage exists in the recorded source and can enforce certain exact-value and reporting-period rules. But a quotation appearing in a document does not automatically mean it supports the proposed conclusion.

**Evidence references make an answer inspectable; they do not, by themselves, prove that it is true.** Interpretation and narrative support still need evaluation and human review. Previously completed applications may help with wording, but they are not authoritative evidence of current facts.

## 4. Repeatability means a controlled process, not identical AI wording

The model may phrase or interpret an answer differently on separate runs. We should not assume that running the same prompt guarantees the same result.

Instead, the application should preserve a record of:

- The input documents and versions used.
- The model, instructions, and validation rules used.
- The proposed answers and evidence references.
- The checks performed and exceptions identified.
- The generated output version.

Once answers and placements are accepted, rebuilding the document should use those recorded decisions rather than asking the model to reinvent them. A targeted correction should not unexpectedly alter unrelated answers.

This supports controlled revisions, investigation of errors, and an understandable review history.

## 5. Security and confidentiality cannot depend on a prompt alone

Source documents can contain confidential information. They can also contain instructions that belong to the document's business context, not instructions the AI is authorized to execute.

For example, a document might describe where a completed application should be sent. That does not authorize the model to send it there.

The intended safeguards include:

- Access only to authorized sources and destinations.
- Narrow document operations rather than unrestricted access to files, email, or other systems.
- Protection of credentials and confidential content from ordinary logs.
- Separation of the internal reviewer summary from the submission packet.
- Independent permission controls that document text cannot override.

Necessary confidential supporting documents remain in scope. The response is appropriate access and handling controls, not excluding required evidence simply because it is confidential.

## 6. Missing information and technical failures need different treatment

An unanswered business question is not the same as a system failure.

If evidence is missing, a reporting period does not match, or a signer cannot be identified, the intended behavior is to continue supported work, leave unsupported answers blank, and clearly explain the exception to the reviewer. The application must not imply that an unmet requirement has been satisfied.

If a document cannot be read or an output cannot be saved, that is a technical problem. The result must be marked appropriately rather than presented as a completed packet. An unreadable form should remain unchanged.

The surrounding software also supports safe recovery: keeping runs separate, preserving prior outputs, and preventing retries from duplicating actions or silently overwriting work.

## 7. Human review and signing remain explicit responsibilities

The application is intended to attempt all answerable fields, including attestations and disclosures, using approved evidence. It must not invent a missing fact, infer a negative disclosure from silence, or assume that a person performed an act.

Human reviewers remain responsible for reviewing the answers, resolving exceptions, and approving the packet. Signatures and mandatory signature dates belong to the human electronic-signing process, not automated generation. Submission to an issuer remains a separate human action.

The reviewer should receive a clear summary of issues and evidence used, not just a document that appears finished.

## 8. The goal is reusable controls, not a custom program for every form

The architecture should let AI handle differences in wording and layout while software enforces rules that remain consistent across applications.

| AI-assisted interpretation | Controlled software responsibilities |
| --- | --- |
| Understand unfamiliar questions and conditions | Check required information and permitted answer structures |
| Identify likely options and answer areas | Validate proposed locations and perform bounded document edits |
| Propose answers from supplied evidence | Verify source references and enforce exact rules where possible |
| Draft supported narrative responses | Measure available space, preserve overflow, and assemble pages |
| Identify possible ambiguity | Record explicit exceptions and route them for review |

Form-specific examples can help test whether these methods work. They should not become an assumption that business users must maintain a separate technical template for every new application.

## What this approach does not guarantee

Neither a detailed prompt nor a well-tested codebase guarantees zero errors or zero hallucinations.

- A correctly structured answer can still be factually wrong.
- A valid citation can still fail to support a conclusion.
- A valid page location can still produce an unsatisfactory visual result.
- Strong results on a small test set do not establish accuracy across all future forms.

Confidence must come from separate evaluation of interpretation and grounding, testing of document operations, verification of rendered outputs, and human review. These checks should report what was actually tested and what remains uncertain.

## Bottom line

**AI provides flexible interpretation and drafting. Controlled software provides enforceable boundaries, traceability, reliable document operations, and explicit status. Human reviewers provide approval and signing.**

Combining these responsibilities makes the application more dependable and easier to review than asking a model to both complete the work and judge its own correctness. The purpose is not to replace AI with complex code; it is to give AI a useful, bounded role in a business process that must remain accountable.
