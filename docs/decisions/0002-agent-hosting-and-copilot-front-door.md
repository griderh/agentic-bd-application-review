# 0002 - Agent hosting and Copilot front door

Status: **Open** - to be decided with IT before slice 7. Researched October 28, 2026 from Microsoft Learn; re-verify before deciding because these services change quickly.

## Context

Slices 7 and 8 must run the agent with the developer workstation off and let a user upload a blank PDF from M365 Copilot or Teams. The model is a Foundry model deployment in every option. The agent code (`agent.py`, tools, gate, writer) is hosting-independent; hosting only changes the web wrapper around `run_packet_agent` and the storage adapter.

## Options

### A. Foundry hosted agent (leading option)
- Packages the agent as a container in Azure Container Registry; Agent Service provides the endpoint, a dedicated Entra agent identity, per-session VM-isolated sandboxes with persistent `$HOME` and `/files`, scaling and session state.
- Accepts any framework (Agent Framework, LangGraph, Semantic Kernel, custom code) over the Responses, Invocations, and Activity protocols.
- Publishing to Teams/Microsoft 365: Microsoft documents that the platform bridges Responses to the Activity protocol automatically; publishing is done from the Foundry portal and creates an Azure Bot Service resource. Prerequisites: Azure Bot Service Contributor (or Contributor/Owner) on the resource group, Foundry User on the project, `Microsoft.BotService` provider registered.
- Clients can upload content to a session through the `/files` endpoint. Whether Copilot/Teams file attachments reach that endpoint is **unverified** and must be proven in slice 8.
- Python adapter: `agent-framework-foundry-hosting` is pre-release only (tested `1.0.0b261022`, on Python 3.12 and 3.13), and its `azure-ai-agentserver-*` dependencies are betas. The Learn pages I read carried no explicit preview/GA label for hosted agents, so **service GA status is unverified**; confirm with Microsoft/IT before relying on it.
- Caution from Microsoft: data published to M365/Teams is subject to M365 data-handling and residency terms; evaluate against the confidentiality rules in this repo.

### B. Azure Container Apps (or App Service) with our own HTTP wrapper
- Our container, managed identity, scale-to-zero, no pre-release hosting package required. Longer runs are fine (unlike Functions timeouts).
- We own endpoint authentication, session/run state (the run store is already file-based and would move to Blob Storage), and observability.
- Copilot/Teams front door needs the Microsoft 365 Agents SDK or Azure Bot Service. The Microsoft 365 Agents SDK documents Python **3.9 to 3.11**, which does not cover this repository's Python 3.12 and 3.13. A separate front-door service on a supported runtime (or a C#/Node front door calling our HTTP API) would be needed, or the repository's Python floor would change. Treat this as a significant cost of option B.

### C. AKS
- Works but adds operational overhead with no PoC benefit unless IT already standardizes on it.

## Provisional direction
Plan on A for slices 7-8, with B as the fallback if hosted agents are unavailable to the tenant, are not GA when needed, or cannot receive Copilot/Teams uploads. Do not change the Python floor or add a second runtime without agreement.

## Questions to close with IT/Microsoft
1. Is Foundry hosted-agent service GA for our tenant and region, and is a pre-release Python adapter acceptable for the PoC?
2. Can a Copilot/Teams user upload a PDF that reaches the hosted agent, and what are the size limits?
3. Who holds Azure Bot Service Contributor and Foundry roles, and can the tenant admin approve publishing?
4. Does M365/Teams processing of agent responses meet the confidentiality and residency requirements for packets and reviewer summaries?
5. Where do evidence sets and outputs live (Blob Storage account, access method, retention)?

## Consequences
Slice 6 is unaffected. Slice 7 starts only after this record is Accepted; the hosting package pin (or the fallback wrapper) is chosen then.

## Sources
- Hosted agents in Foundry Agent Service: https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents
- Publish agents to Microsoft Copilot and Teams: https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot
- Microsoft 365 Agents SDK overview: https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/agents-sdk-overview
