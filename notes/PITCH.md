# Pitch notes

## One line
Doublethink lets a deal team use an AI agent on the open web without the web ever learning the deal: the model
that knows the secret never reads a web page, and the model that reads the web never sees the secret.

## Tracks (from the attendee packet)
- **Privacy-First (main track):** "Local AI, anonymization, encrypted apps." Our Planner is local; the secret
  never reaches a cloud model.
- **Most Startup-able (Misneach and FuzionX):** "Real problem, paying customer, right team."
- **Surge (Tavily and Exa):** "Build on Tavily or Exa search, with sources." Every number in our answer has a
  quote and a source.
- Ask the organizers whether one project can win the main track and sponsor prizes.

## Why now
- Agents with web search are standard tooling, and prompt injection that leads to data theft is the open problem.
  Willison lists real incidents in Microsoft 365 Copilot, GitHub's MCP server and GitLab Duo (2025).
- Filters are detectors. Willison: vendors advertise around 95%, which is a failing grade in security.
- A search query is not private to one company: Tavily fans out to several sources in real time.

## Buyer
First: the chief compliance officer at an M&A advisory boutique or a PE fund, whose firm must have written
procedures to stop misuse of material non-public information, and who is being asked to allow research agents.
Later: any team running agents over confidential documents (legal, pharma, audit).
Price: [team to decide, or leave pricing out]. No customers yet: say so.

## Competitors, honestly
| Who | What they do | Our sentence |
|---|---|---|
| Pipelock (open source) | content-inspecting egress proxy, credential DLP with decoding, hash-chained recorder, signed receipts | They filter what a possibly compromised agent sends. We make sure the model holding the secret never reads attacker text. Their detectors look for credential-shaped data; deal words are ordinary words. |
| MCP gateways (Docker MCP Gateway, PointGuard, Runlayer, mcp-firewall and others) | tool access control, secret-shaped data blocking, audit logs | Same: they sit outside the agent. We change how the agent is built. |
| Zero-data-retention contracts (Exa Enterprise, Nebius) | limit what the provider stores | Does not stop a hijacked agent from sending the secret. |
| CaMeL, Dual LLM, design patterns papers | the research we build on | Credit them. Our contribution is the confidential-research application, the gate and the measurements. |

Do not say "nobody does this". Say what we do and what we measured.

## Why this team
[Each member: one true, checkable line.]

## Sponsor angles (for the 13:00 fair and Q&A)
- **Tavily**: Tavily is both the research engine and the thing being protected; show finance topic, preferred
  primary-source domains, extract with reranking, credits per run.
- **Misneach, FuzionX**: buyer, wedge, why now. Ask what they would need to see to fund it.
- **SSOJet** has written publicly about CaMeL; their people may know the prior art. Ask them.

## Hard questions
1. "Isn't this just CaMeL?" It builds on it, credited. Different job: research on the open web with a secret
   memo, plus an egress gate and measured leak rates.
2. "Can the Planner still leak by itself?" Yes, by its own mistake; the gate is the second layer, with measured
   false blocks.
3. "What do you lose?" The Planner cannot react to arbitrary web text; numbers on usefulness are in the demo.
4. "Your proof is signed by your own code." Correct, it shows what this install logged.
5. "Did you write this during the weekend?" Yes. Planning notes and the attack list were written Friday; the
   attack list's hash was fixed then. All code after 11:00 Saturday.
6. "Who pays?" The buyer above. No customers yet; say so.
