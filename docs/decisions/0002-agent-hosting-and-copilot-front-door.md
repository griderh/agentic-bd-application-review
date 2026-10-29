# 0002 - Agent hosting and Copilot front door

Status: **Accepted for the PoC**. Foundry hosting, the beta Python adapter, staged-ID intake and private Blob storage were approved by the technical sponsor. Researched October 28, 2026; re-verify service and channel capabilities before production.

**October 29 clarification:** Foundry hosting remains the ultimate deployment thesis, but the immediate PoC runs locally with Foundry model calls and Blob storage using the developer's authorized credentials. Hosted identity grants and Copilot publishing do not block that PoC. Do not spend further effort deploying versions merely to demonstrate local document quality.

## Context

Slices 7 and 8 must run the agent with the developer workstation off and let a user select a staged blank PDF from M365 Copilot or Teams. Direct file/image attachments are not currently supported for this custom-engine Copilot publishing path. The model is a Foundry model deployment in every option. The agent code (`agent.py`, tools, gate, writer) is hosting-independent; hosting changes the web wrapper around `run_packet_agent` and the storage adapter.

## Options

### A. Foundry hosted agent (leading option)
- Selected deployment: `azd` code deploy with remote build on Python 3.13; no developer-managed Docker image or ACR required. Agent Service provides the endpoint, an agent identity, isolated sandboxes and session state.
- Accepts any framework (Agent Framework, LangGraph, Semantic Kernel, custom code) over the Responses, Invocations, and Activity protocols.
- Publishing to Teams/Microsoft 365: Microsoft documents that the platform bridges Responses to the Activity protocol automatically; publishing is done from the Foundry portal and creates an Azure Bot Service resource. Prerequisites: Azure Bot Service Contributor (or Contributor/Owner) on the resource group, Foundry User on the project, `Microsoft.BotService` provider registered.
- The hosted session Files API does not establish Copilot attachment support. Use staged blank/evidence IDs instead; original PDF bytes remain available to deterministic tools.
- Python adapter: `agent-framework-foundry-hosting==1.0.0b261022` is beta, with some beta server dependencies. The technical sponsor reports that the hosted-agent service is GA and explicitly accepts the beta adapter for the PoC. Service GA and adapter maturity are separate; the earlier research did not independently verify the GA claim.
- Caution from Microsoft: data published to M365/Teams is subject to M365 data-handling and residency terms; evaluate against the confidentiality rules in this repo.

### B. Azure Container Apps (or App Service) with our own HTTP wrapper
- Our container, managed identity, scale-to-zero, no pre-release hosting package required. Longer runs are fine (unlike Functions timeouts).
- We own endpoint authentication, session/run state (the run store is already file-based and would move to Blob Storage), and observability.
- Copilot/Teams front door needs the Microsoft 365 Agents SDK or Azure Bot Service. The Microsoft 365 Agents SDK documents Python **3.9 to 3.11**, which does not cover this repository's Python 3.12 and 3.13. A separate front-door service on a supported runtime (or a C#/Node front door calling our HTTP API) would be needed, or the repository's Python floor would change. Treat this as a significant cost of option B.

### C. AKS
- Works but adds operational overhead with no PoC benefit unless IT already standardizes on it.

## Selected direction
Use A for slices 7-8, with B as the fallback if deployment or operational requirements cannot be met. Unsupported Copilot uploads are addressed by staged-ID intake, not by changing hosting. Do not change the Python floor or add a second runtime without agreement.

- Use the existing `bd-application-builder` Foundry project and `gpt-6.1-sol` deployment.
- Use `bdpoc3ff06060`: authenticated `packet-inputs`, `packet-results`, and `reviewer-results` containers. HTTPS/TLS 1.2 is enforced; anonymous Blob access and shared-key authentication are disabled. The public network endpoint remains enabled: these are private containers, **not private-endpoint networking**.
- Stage approved original PDFs plus an immutable hash/size manifest. File Search can assist text grounding later; it does not replace original document intake, hashes, rendering or attachments.
- The preview SharePoint grounding tool uses delegated user access and is not supported for Teams publication. A future SharePoint/Graph original-file adapter can feed the same bundle contract; no whole-drive indexing or SharePoint dependency is introduced in the PoC.
- The sponsor's Blob Data Contributor role permits workstation staging and testing. It does not grant the hosted agent data access or allow the sponsor to assign its roles.
- An administrator must grant the hosted identity Blob Data Reader on `packet-inputs`, Blob Data Contributor on `packet-results` and `reviewer-results`, and model inference access at the appropriate Foundry scope. No storage-key workaround.
- This PoC uses one shared, authorized project dataset, not per-requester ACLs. Restrict its audience until authenticated ownership/result-link controls are implemented.

## Questions to close with IT/Microsoft
1. Assign the actual hosted identity's least-privilege storage/model roles after deployment identifies its principal.
2. Verify staged selection, authenticated result access and tenant approval during slice 8; do not promise direct Copilot uploads or downloadable Blob paths.
3. The sponsor has RG Contributor and project/resource Foundry User. Verify Bot Service provider registration and tenant publishing approval separately.
4. The sponsor accepts the current tools for the document classifications involved. Confirm production channel residency, access, retention and operational ownership with IT.

## Consequences
Slice 7 uses the same bounded model workflow and deterministic tools as slice 6. Local HTTP invocation against staged synthetic Blob inputs has produced a packet and separate reviewer summary; that is not proof of cloud-hosted execution. Request claims prevent duplicate execution, but interrupted requests require operator recovery rather than automatic restart. Durable crash recovery and production retention remain later work.

## Sources
- Hosted agents in Foundry Agent Service: https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents
- Publish agents to Microsoft Copilot and Teams: https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot
- Microsoft 365 Agents SDK overview: https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/agents-sdk-overview
- SharePoint grounding tool: https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/sharepoint
