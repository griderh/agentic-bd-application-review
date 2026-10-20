# agentic-bd-application-review
This agentic AI application reviews broker-dealer application requirements and constructs the application using supporting documentation such that it can be reviewed and submitted by signatories

## Project documentation

- [Phase 1 scoping document](Broker-Dealer%20Packet%20Automation%20Phase%201%20Scoping%20Document.md): business requirements, boundaries, and evaluation criteria.
- [Development plan](docs/development-plan.md): milestones, dependencies, acceptance criteria, and open implementation decisions.
- [Copilot coding instructions](.github/copilot-instructions.md): repository-wide Python, test-driven development (TDD), grounding, and data-handling standards.

## Development status

The repository currently contains planning documents and business document samples; the Python application and build/test tooling have not been implemented. The first development milestone establishes the environment and exact validation commands. No dependency installation or Azure deployment is required to review these documents.

The initial deliverable is a locally executed Python PoC using [blank forms](bd_agreements/Blank/) and [supporting documents](bd_agreements/supporting_data/) already in this repository. It calls a remote model through an approved Foundry endpoint, validates the results, and generates outputs locally; the model does not directly access the local folders. [Completed packets](bd_agreements/Completed/) support validated evaluation and wording precedent, not current factual authority. Network-drive mapping, cloud application hosting, Azure Blob document storage, and production integrations are deferred until the working PoC has been reviewed.

Treat business samples and generated outputs as potentially confidential. Do not publish them, copy them into ordinary test fixtures, or upload them to model/OCR services without approved access. Use synthetic or sanitized fixtures for offline development and CI.
