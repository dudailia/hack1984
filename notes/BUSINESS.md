# Business notes

Researched Nov 7, 2026 from public web sources. Every claim has a URL. Anything in [brackets] is a placeholder: we
could not source it, or the team has not measured it yet. Read this with notes/PITCH.md and notes/PITCH_SCRIPT.md.

## 1. One paragraph

Deal teams at M&A advisers and private equity funds are being asked to approve AI research agents. US and EU law
already requires their firms to have written procedures that stop material non-public information (MNPI) from being
misused or disclosed, and the SEC fines firms whose procedures fail even when nobody traded. A web-research agent
that holds the deal memo sends text to third parties on every search. Today's agent security tools filter that text
for credential-shaped data; a codename, a buyer's name and a price are ordinary words. Doublethink is built so the
model that holds the memo never reads attacker text, every outbound byte goes through one gate, and the firm gets a
signed record of exactly what left. That record is the artifact a compliance officer can file.

## 2. The buyer

**Who signs:** the chief compliance officer (CCO) of an SEC-registered adviser that runs private equity funds, or of a
FINRA-member broker-dealer that does M&A advisory. Rule 206(4)-7 requires every registered adviser to name a CCO and
keep written compliance policies (https://www.ecfr.gov/current/title-17/chapter-II/part-275/section-275.206(4)-7).

**Who uses it:** analysts, associates and VPs on deal teams, and corporate development groups, doing public-market
research (sector growth, trading multiples, comparable deals) while holding a confidential memo.

**How many firms (sourced counts, our segment is a subset):**
- 3,184 FINRA member firms at the end of 2025.
  https://www.finra.org/media-center/blog/four-insights-from-finras-2026-industry-snapshot
- 16,544 investment advisers in 2025, 92.8% of them with 100 or fewer employees (Investment Adviser Association
  snapshot). https://www.investmentadviser.org/iaatoday/press-release/2026-investment-adviser-industry-snapshot-shows-continued-growth-in-demand-for-adviser-services/
- Of those, firms that advise private equity funds or do M&A advisory: not measured.

**Why small firms first:** most advisers are small (92.8% at 100 or fewer staff, above), so they buy tools rather
than build an in-house AI security team. That is a hypothesis about buying behaviour, not a sourced fact.

## 3. The pain

1. **The rules already exist and are enforced on policy failures alone.** The SEC fined OEP Capital Advisors, a
   private equity adviser, $4,000,000 on Dec 26, 2023 for failing to maintain and enforce written MNPI policies.
   The conduct: senior staff emailed merger-related MNPI to investors and industry contacts. No insider trade was
   alleged. https://www.sec.gov/enforce/ia-6514-s and
   https://stblaw.com/docs/default-source/Publications/regulatoryenforcementalert_01_03_24
   A search query that carries the deal is the same kind of disclosure, to a search provider instead of a person.
2. **AI agents leak through prompt injection in real products.** Section 5 lists 13 sourced cases from 2024 to 2026,
   including Microsoft 365 Copilot (EchoLeak), Salesforce Agentforce (ForcedLeak) and Slack AI.
3. **Employees already put confidential data into AI tools.** Cyberhaven (vendor telemetry, about 3M workers, May
   2024): 27.4% of the corporate data employees put into AI tools was sensitive, up from 10.7% a year earlier.
   https://www.scworld.com/news/shadow-ai-on-the-rise-sensitive-data-input-by-workers-up-156
   LayerX (vendor report, Oct 2025): 77% of employees who use AI paste data into prompts, 82% of that through
   unmanaged accounts. https://www.theregister.com/2025/10/07/gen_ai_shadow_it_secrets
4. **It has reached an SEC filing.** CB Financial Services (a bank holding company) filed an 8-K under Item 1.05
   after an employee put customer names, Social Security numbers and dates of birth into an unauthorized AI
   application; it learned of it on May 5, 2026.
   https://www.sec.gov/Archives/edgar/data/0001605301/000160530126000021/cbfv-20260507.htm
5. **No public case of MNPI leaking through an AI tool has been reported** that we could find. Say so. The pain is
   the rule plus the demonstrated mechanism, not a headline.

## 4. The rules that create the budget

| Rule | Who it binds | What it says, in plain words | Source |
|---|---|---|---|
| Advisers Act Section 204A, 15 U.S.C. 80b-4a | Investment advisers subject to Section 204, including registered PE fund managers | Must "establish, maintain, and enforce written policies and procedures reasonably designed" to prevent misuse of MNPI by the firm or its people. | https://www.law.cornell.edu/uscode/text/15/80b-4a |
| Advisers Act Rule 206(4)-7, 17 CFR 275.206(4)-7 | Registered advisers | Written compliance policies, reviewed at least once a year, and a named chief compliance officer. Charged alongside 204A in the MNPI cases below. | https://www.ecfr.gov/current/title-17/chapter-II/part-275/section-275.206(4)-7 |
| Advisers Act Rule 204A-1, 17 CFR 275.204A-1 | Registered advisers | Written code of ethics; access persons report holdings and trades. | https://www.ecfr.gov/current/title-17/chapter-II/part-275/section-275.204A-1 |
| Exchange Act Section 15(g), 15 U.S.C. 78o(g) | Registered broker-dealers | "Every registered broker or dealer shall establish, maintain, and enforce written policies and procedures reasonably designed" to prevent misuse of MNPI. | https://www.law.cornell.edu/uscode/text/15/78o |
| Exchange Act Section 21A, 15 U.S.C. 78u-1 | Firms that control a person who trades on MNPI | If the firm "knowingly or recklessly failed to establish, maintain, or enforce" the 15(g) or 204A procedures and that contributed to the violation, it faces a civil penalty up to the greater of $1,000,000 or three times the profit gained or loss avoided. | https://www.law.cornell.edu/uscode/text/15/78u-1 |
| Exchange Act 10(b) and Rule 10b-5 | Everyone | The insider trading prohibition itself. | https://www.law.cornell.edu/cfr/text/17/240.10b-5 |
| FINRA Rule 3110(d) | FINRA members | Supervisory procedures must review trades for insider trading. Members doing investment banking, which includes "acting as a financial adviser in a merger or acquisition", report investigations to FINRA quarterly. | https://www.finra.org/rules-guidance/rulebooks/finra-rules/3110 |
| EU MAR (Reg. 596/2014) Art. 10 and 14 | Anyone holding inside information | Disclosing inside information to anyone is unlawful, "except where the disclosure is made in the normal exercise of an employment" (or profession or duties); Art. 14 prohibits it. | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32014R0596 |
| EU MAR Art. 9(1) | Legal persons | A defence for firms that have "adequate and effective internal arrangements and procedures" (information barriers). | same |
| EU MAR Art. 11 | Bidders and their advisers | Takeover-bid soundings: written records of what was disclosed to whom. | same |
| EU MAR Art. 16(2) | "Any person professionally arranging or executing transactions" | "effective arrangements, systems and procedures" to detect and report suspicious orders. | same |
| EU MAR Art. 18 | Issuers and anyone acting on their behalf (M&A advisers) | Keep an insider list of everyone with access to inside information. | same |

**Enforcement that shows the budget is real (all SEC, all under 204A and Rule 206(4)-7):**

| Firm | Date | Penalty | Source |
|---|---|---|---|
| Ares Management (PE) | May 26, 2020 | $1,000,000 | https://www.sec.gov/news/press-release/2020-123 |
| MIO Partners (McKinsey affiliate) | Nov 19, 2021 | $18,000,000 | https://www.sec.gov/newsroom/press-releases/2021-241 |
| OEP Capital Advisors (PE) | Dec 26, 2023 | $4,000,000 | https://www.sec.gov/enforce/ia-6514-s |
| Sound Point Capital Management | Aug 26, 2024 | $1,800,000 | https://www.sec.gov/newsroom/press-releases/2024-106 |
| Marathon Asset Management | Sep 30, 2024 | $1,500,000 | https://www.sec.gov/newsroom/press-releases/2024-158 |

**Related, not MNPI-specific:**
- SEC Regulation S-P amendments (May 16, 2024): broker-dealers and registered advisers need a written incident
  response program and must notify affected individuals within 30 days of unauthorized access.
  https://www.sec.gov/newsroom/press-releases/2024-58
- FINRA Regulatory Notice 24-09 (June 27, 2024) on generative AI: creates no new rules, but says policies should
  address "technology governance, including model risk management, data privacy and integrity".
  https://www.finra.org/rules-guidance/notices/24-09
- We found no SEC statement that ties AI tools to MNPI specifically. Do not claim one.

**Caveat on M&A boutiques:** since March 29, 2023, Exchange Act 15(b)(13) exempts some M&A brokers from SEC
registration (private targets under $25M EBITDA or $250M revenue, no handling of funds, no financing). An exempt
broker is not a "registered broker or dealer", so 15(g) and FINRA 3110 do not bind it by their terms; 10b-5 still
does. This is our reading of the statute, not legal advice. https://www.law.cornell.edu/uscode/text/15/78o
So the sharpest buyer is the registered broker-dealer or registered PE adviser, not the smallest exempt boutique.

## 5. AI leaks through prompts and agents, 2024 to 2026

Every row is a disclosed vulnerability or incident with a source. Dates are disclosure dates.

| Date | Product | Found by | What could leak, and how | Fixed | Source |
|---|---|---|---|---|---|
| Aug 20, 2024 | Slack AI | PromptArmor | A message in a public channel made Slack AI put private-channel data into a link to the attacker. | Slack says patched | https://promptarmor.substack.com/p/data-exfiltration-from-slack-ai-via |
| Sep 2024 | ChatGPT macOS app, memory ("SpAIware") | Johann Rehberger | Injected content wrote a lasting instruction into memory, so later chats were sent to the attacker. | Yes | https://embracethered.com/blog/posts/2024/chatgpt-macos-app-persistent-data-exfiltration/ |
| May 2025 | GitLab Duo | Legit Security | Hidden prompts in merge requests made Duo leak private source code through HTML image tags. | Yes | https://www.legitsecurity.com/blog/remote-prompt-injection-in-gitlab-duo |
| May 2025 | GitHub MCP server | Invariant Labs | A malicious public issue made the user's agent copy private repo contents into a public pull request. | No code fix; called architectural | https://invariantlabs.ai/blog/mcp-github-vulnerability |
| Jun 11, 2025 | Microsoft 365 Copilot (EchoLeak, CVE-2025-32711) | Aim Security | Zero-click: one email got Copilot to put mailbox and SharePoint data into an image URL, past Microsoft's injection classifier. | Yes, server side | https://msrc.microsoft.com/update-guide/vulnerability/CVE-2025-32711 |
| Jul 2025 | Supabase MCP with Cursor | General Analysis | A support ticket made a privileged agent read a token table and paste it into a reply the attacker could see. | Mitigation guidance only | https://simonwillison.net/2025/Jul/6/supabase-mcp-lethal-trifecta/ |
| Aug 20, 2025 | Perplexity Comet browser | Brave | Hidden text in a Reddit comment made "summarize this page" read a Gmail one-time code and send it to the attacker. | Perplexity says fixed; Brave disputed | https://brave.com/blog/comet-prompt-injection/ |
| Sep 2025 | Notion AI agents | CodeIntegrity; PromptArmor | Hidden text in a PDF made the agent build a URL from private workspace data and send it through its web-search tool. | [unconfirmed] | https://www.codeintegrity.ai/blog/notion |
| Sep 25, 2025 | Salesforce Agentforce (ForcedLeak) | Noma Security | A web lead form made the agent send CRM data to an expired allowlisted domain, which the researchers bought for $5. | Yes | https://www.theregister.com/2025/09/26/salesforce_agentforce_forceleak_attack/ |
| Sep 30, 2025 | Google Gemini ("Gemini Trifecta") | Tenable | Prompts hidden in logs or search history made Gemini put user data into a browsing request to an attacker server. | Yes | https://www.infosecurity-magazine.com/news/gemini-trifecta-dangers-indirect/ |
| Oct 8, 2025 | GitHub Copilot Chat (CamoLeak) | Legit Security | Hidden pull request comments made Copilot leak keys and private code through GitHub's own image proxy. | Image rendering turned off | https://www.legitsecurity.com/blog/camoleak-critical-github-copilot-vulnerability-leaks-private-source-code |
| Oct 2025 | Claude code interpreter ("Claude Pirate") | Johann Rehberger | Injected instructions made Claude upload user files to the attacker's account through api.anthropic.com, a host the default network allowlist permits. | [unconfirmed] | https://embracethered.com/blog/posts/2025/claude-abusing-network-access-and-anthropic-api-for-data-exfiltration/ |
| Feb 2026 | Microsoft 365 Copilot Chat | Microsoft service alert | A bug let Copilot summarize emails labelled confidential, bypassing DLP rules. Not an attack; shows label-based controls fail. | Yes | https://www.bleepingcomputer.com/news/microsoft/microsoft-says-bug-causes-copilot-to-summarize-confidential-emails |

Employee leaks through prompts (no attacker):
- CB Financial Services 8-K, May 2026 (section 3). https://www.sec.gov/Archives/edgar/data/0001605301/000160530126000021/cbfv-20260507.htm
- NSW Reconstruction Authority, Australia: a contractor uploaded a spreadsheet with data on up to 3,000 flood
  program applicants to ChatGPT (March 2025, made public October 2025).
  https://www.itnews.com.au/news/nsw-gov-contractor-uploaded-excel-spreadsheet-of-flood-victims-data-to-chatgpt-620815
- UK solicitor put client documents into ChatGPT; the Upper Tribunal referred the matter to the regulator (Feb
  2026). https://www.legalfutures.co.uk/latest-news/solicitor-faces-probe-after-putting-client-documents-into-chatgpt

Not a prompt leak, do not present it as one: McKinsey's internal AI platform Lilli (Mar 2026) was breached by a
security startup's AI agent through a SQL injection in unauthenticated APIs; McKinsey says forensics found no
evidence of client data access. https://www.theregister.com/2026/03/09/mckinsey_ai_chatbot_hacked

Two lessons for our pitch, straight from these rows:
- **Allowlists answer "where", not "what".** ForcedLeak used an allowlisted domain. Claude Pirate used
  api.anthropic.com, which is on our own allowlist (for Reader jobs). Our answer: the Reader never holds the secret,
  and the Gate builds the Reader request itself. [Aayush to confirm: the Gate pins its own API key and the exact
  endpoint path, not only the host.]
- **Classifiers miss.** EchoLeak got past Microsoft's injection classifier. That is Willison's 95% point in practice.

## 6. The wedge

**Start narrow:** public-market research while holding a deal memo. Sector growth, trading multiples, comparable
deals. The research question is public; the reason for asking is the secret. This is the exact case where an
agent's search query is the leak.

**What we sell to the CCO is the record, not the model.** The signed ledger shows every outbound payload (as a
commitment, shareable without the payload), the rule that blocked it, and which gate and check code ran. That maps
onto what the rules ask for: written procedures that are "maintained and enforced" (204A, 15(g)), records of what
was disclosed to whom (MAR Art. 11), and an annual policy review (Rule 206(4)-7).

**Why the architecture and not a filter:** every competitor below inspects traffic around one agent, and their
secret detection is shape-based (credential patterns, PII, entropy) or a hand-entered list. A deal codename is an
ordinary word. We remove the path instead: the model that knows the deal never reads attacker text.

**Expand later:** legal (privileged documents), pharma (trial data), audit, corporate development. Same pattern:
a private document plus open-web research.

**First step:** design-partner conversations with compliance officers (how many so far: not measured). We have no
customers and no letters of intent. Say so.

## 7. Pricing hypothesis (a hypothesis, not validated)

> **Hypothesis:** an annual firm licence (our price: not measured), near the enterprise tier of egress-security tools, plus
> pass-through search and model costs. Design partners at a discount for the first year.

What anchors it (sourced):
- Pipelock, the closest open-source competitor, publishes its prices: Community $0, Pro $49/month founding price
  (regular $99/month), Enterprise $25,000/year, a 60-day evaluation at $5,000, a design-partner deal at $15,000.
  https://pipelab.org/pricing/
- Tavily pay-as-you-go is $0.008 per credit; basic search costs 1 credit. https://www.tavily.com/pricing and
  https://docs.tavily.com/documentation/api-reference/endpoint/search
- The penalties in section 4 run from $1,000,000 to $18,000,000. A licence is cheap next to one enforcement action.
  That is the argument, not proof anyone will pay.

What we do not know:
- Tavily credits per research question: 1.77 on average (median 1.5, max 5), from our live benign run at commit 294c423.
- Claude Reader cost per question: not measured.
- What a CCO at a PE adviser actually pays for compliance tooling today: not measured.
- Willingness to pay: not measured.

## 8. Competitors (from their own pages, checked Nov 7, 2026)

| Product | What it is | What it inspects and how | Audit | Price | Source |
|---|---|---|---|---|---|
| Pipelock (PipeLab) | Open-source "AI agent firewall": egress, fetch, WebSocket and MCP proxy in one binary | Outbound headers, bodies, MCP arguments and responses. 65 credential patterns, decoding (base64, hex, URL and others), entropy checks, a hand-entered secrets file, 34 injection patterns. Its docs say it does not decode reversed text or rot13. | Hash-chained log, Ed25519-signed checkpoints, signed receipts verifiable offline | Apache 2.0 core; Pro $49 to $99/month; Enterprise $25,000/year | https://github.com/pipelab-org/pipelock , https://raw.githubusercontent.com/pipelab-org/pipelock/main/docs/configuration.md and https://pipelab.org/pricing/ |
| Docker MCP Gateway | Docker CLI plugin between the AI client and MCP servers running in containers | `--block-secrets` (on by default) blocks "secrets" in tool calls; `--block-network`; image signature checks; custom interceptor scripts. The detection method is not documented. | Call logs | MIT, free | https://docs.docker.com/reference/cli/docker/mcp/gateway/run/ |
| PointGuard AI | Commercial "zero-trust gateway" for MCP servers and agents, plus a guardrails API | Every tool call against policy; DLP on inputs and outputs (PII, PHI, financial data, custom patterns) with block, mask or redact; ML-based injection detection | Violation logs and alerts | Not published (demo only) | https://www.pointguardai.com/mcp-security-gateway and https://www.pointguardai.com/ai-intelligent-guardrails |
| mcp-firewall (ressl) | Open-source gateway that wraps an MCP server | YAML allow and deny rules, argument rules, rate limits, approval prompts; secret and PII scanners; pattern-based injection detection; blocks SSRF and private IPs (destination, not content) | Hash chain, optional Ed25519 signing, SIEM export | AGPL-3.0 or commercial | https://github.com/ressl/mcp-firewall |

Also in the market (one line each): Lakera (acquired by Check Point, announced Sep 16, 2025,
https://www.checkpoint.com/press-releases/check-point-acquires-lakera-to-deliver-end-to-end-ai-security-for-enterprises/),
Prompt Security (SentinelOne, announced Aug 5, 2025,
https://www.sentinelone.com/press/sentinelone-to-acquire-prompt-security-to-advance-genai-security/), Protect AI
(Palo Alto Networks, closed Jul 22, 2025,
https://www.paloaltonetworks.com/company/press/2025/palo-alto-networks-completes-acquisition-of-protect-ai),
Invariant Labs (Snyk, announced Jun 24, 2025,
https://snyk.io/news/snyk-acquires-invariant-labs-to-accelerate-agentic-ai-security-innovation), Runlayer
(independent MCP and LLM gateway, https://www.runlayer.com). Large security vendors are buying this category, which
says the budget exists.

**Tavily itself** advertises layers that "block PII leakage, prompt injection, and malicious sources" and zero data
retention (https://www.tavily.com/). That is a complement, not a competitor: Tavily can block an email address, but
only the client knows that "Halyard" or "$412 million" is the secret, so that check has to happen before the query
leaves the machine.

**What none of them does:** on their own pages, none of the four separates the model that holds secrets from the
model that reads untrusted content. Pipelock's "capability separation" separates the agent from the network, not
two models. The design we build on is published research: Willison's Dual LLM pattern
(https://simonwillison.net/2023/Apr/25/dual-llm-pattern/) and Google DeepMind's CaMeL
(https://arxiv.org/abs/2503.18813). Credit them. Never say "nobody does this".

**Where they are ahead of us:** Pipelock already ships a hash-chained, signed record and decoding-aware DLP, and
it is free to start. Our signed bundle is not a differentiator on its own. The difference is the split.

## 9. The people (public professional information only)

| Who | Public role | What they have said they care about | So in the pitch |
|---|---|---|---|
| **HACK1984 judging** | Main track asks "What leaves the device, who can read it, and can you prove it?" Surge asks "how central Tavily or Exa is to what the project does, and how well it works". Most Startup-able asks "Who is it for, would they pay, and why is this team the one to build it?" https://claudeneu.com/hackathon/ | | Answer the main-track question word for word: what leaves (checked queries only), who reads it (Tavily; Anthropic for public text only), how we prove it (the signed bundle). |
| **Tavily (Nebius)** | Real-time search API for agents. Nebius announced the acquisition on Feb 10, 2026; Tavily keeps its brand and CEO Rotem Weiss. Nebius did not disclose a price; Calcalist reports $275M in cash, up to $400M with milestones. Financial services is a named vertical. https://nebius.com/newsroom/nebius-announces-agreement-to-acquire-tavily-to-add-agentic-search-to-its-ai-cloud-platform and https://www.calcalistech.com/ctechnews/article/r168bhodbe | "Enterprise-grade security, built in"; partnership with Pillar Security: "AI agents are particularly vulnerable to indirect injection attacks." https://www.tavily.com/ and https://www.tavily.com/blog/tavily-partners-with-pillar-to-deliver-enterprise-grade-ai-web-access-with-built-in-security-to-secure-ai-agents-web-access-2 . Nebius: agents "can verify information against live sources." https://nebius.com/blog/posts/bringing-agentic-search-into-the-production-ai-stack | Tavily is the only search egress and the channel we protect. Show finance topic, extract, credits per run, and that every number has a source. Frame the Gate as making Tavily safe for regulated buyers. |
| **Misneach** | Boston "founder propulsion platform", invests from formation through seed, "no external limited partners". Co-founders Mark Coffey and Spencer Gaffney; Executive Chair Chris Gaffney, co-founder of the PE firm Great Hill Partners. https://misneach.ai/ and https://aiweek.boston/partners-misneach-ai | "Pedigree is not the signal. Execution is." https://linkedin.com/company/misneach-ai . Coffey's profile: making "non-deterministic AI systems trustworthy and deployable." https://linkedin.com/in/mjcoffey | Lead with execution (what ran today) and a buyer a PE person recognises. The proof bundle is "trustworthy and deployable" made concrete. |
| **FuzionX** | Boston venture studio co-building "AI-native software and solutions companies". CEO and founder Tom Stanford. https://fuzionx.com/team/ | Product viability: "Build customer cohort, prove usage, and establish client references." Commercial viability: "Generate ARR, validate pricing." https://fuzionx.com/founders/ | Have the ICP, the pricing hypothesis (section 7) and the design-partner path ready. Admit we have no customers. |
| **Jhooma Coppisetti** (Privacy and Security fireside, Sat 3 PM) | Event bio: "Director of Data Architecture. Nearly two decades in data management, data governance, and enterprise architecture." https://partiful.com/e/Nzd4LVCSg1LHisIYysK5 . The event does not name an employer; a LinkedIn profile matching the bio lists Fidelity Investments. https://linkedin.com/in/jhooma-coppisetti | Breaking data silos, first-principles questions ("What are we assuming to be true?"). https://www.linkedin.com/posts/jhooma-coppisetti_firstprinciplesthinking-sixsigma-innovationculture-activity-7345197535822553090-J56t | Show the data-flow diagram with trust boundaries and state our assumptions (threat model) out loud. |
| **Sanjay Krishna** (named judge) | Event bio: "Director of Architecture. Background in systems engineering and computational intelligence." https://partiful.com/e/Nzd4LVCSg1LHisIYysK5 . Employer not stated by the event; a matching LinkedIn profile lists Fidelity Investments. https://linkedin.com/in/sanjaykrishna1 | Built an LLM extraction pipeline where "Every claim carries a verbatim quote and page number. No quote, no record." and the run fails closed. https://www.linkedin.com/posts/sanjaykrishna1_llms-have-helped-me-recently-get-some-interesting-activity-7368655206194106370-KMgy | Our Validator is the same idea: no verbatim quote, no number; numbers computed in code. Show a dropped claim. |
| **Mehr Anand** (moderator, co-organizer) | Northeastern CS student, founder of the Claude Builders Club, HACK1984 co-organizer; data co-op at General Atlantic (growth equity). https://www.mehr-anand.com/ and https://www.mehr-anand.com/leadership | Interests listed as "finance, AI, and applied machine learning" and private equity. https://www.mehr-anand.com/leadership | Knows how PE firms handle data. Keep the deal workflow realistic: memo, public research, compliance sign-off. |

Unconfirmed: the other judges and which people judge each prize.

## 10. The 10 hardest judge questions

1. **"Who has said they would pay for this?"**
   Nobody yet. We have no customers and no letters of intent. The budget comes from a legal requirement that already
   exists (204A, 15(g)) and from fines of $1M to $18M for policy failures. Next step: design-partner
   conversations with compliance officers.

2. **"Why wouldn't a firm just ban AI agents?"**
   Many do today. A ban is a policy the CCO has to enforce, and employees already use unmanaged AI accounts (LayerX:
   82% of pasting through unmanaged accounts). We give the CCO an approved path with a record, instead of a ban
   people work around.

3. **"Why not Pipelock or an MCP gateway? They are free."**
   Their secret detection looks for credential-shaped data or a hand-entered list. A codename and a buyer's name are
   ordinary words, and paraphrase gets past lists. We stop the model that knows the deal from reading attacker text.
   We still keep a gate, because the Planner can slip on its own. Pipelock is ahead of us on mature DLP and signed
   logs; we say so.

4. **"Isn't this just CaMeL or the Dual LLM pattern?"**
   It builds on both and we credit them. Our part is the application to confidential web research, the egress gate,
   the typed channel back to the planner, and measured leak rates on attacks fixed before any code.

5. **"Is a search query really 'misuse' or 'disclosure' of MNPI?"**
   The SEC fined OEP $4M for emailing merger MNPI to outside contacts, with no trade alleged. A query that names the
   buyer, the target and the price goes to a third party that fans it out to others. Whether a regulator would call
   it a violation is for lawyers; a CCO does not want to find out. We are not giving legal advice.

6. **"Your allowlist includes api.anthropic.com. Claude Pirate exfiltrated through exactly that host."**
   Right, which is why the host list is not our defence. The Reader never holds the secret, has no tools, and the
   Gate writes the request. [Aayush to confirm: the Gate pins its own key and the exact endpoint path.]

7. **"The local model can still leak by mistake. What is your real leak rate?"**
   Single agent: 2 of 40. Two minds plus gate: 0 of 40, and the gate never fired. Attacks hashed on Friday, before any code, and the
   check builder never saw them. Not 100%, and we do not claim it.

8. **"What does it cost in usefulness?"**
   The planner only sees numbers, so open-ended research is weaker. 23 of 30 normal questions answered with a cited
   number, at 1.77 Tavily credits and 14.7 seconds per question on average (live run, commit 294c423).

9. **"How big is the market?"**
   3,184 FINRA member firms and 16,544 investment advisers (2025 counts). The share that does M&A or advises PE funds
   is not measured. Expansion is any team with a private document and open-web research: legal, pharma, audit.

10. **"Why this team, and what stops a big vendor from copying it?"**
    [Each member: one true, checkable line.] Honest answer on defensibility: the idea is published, so the moat is
    not the idea. It is a product a compliance officer can sign off on, measured results, and a record format that
    fits their filing. Large vendors bought Lakera, Prompt Security, Protect AI and Invariant in 2025, which says
    the category matters; it also means we should expect them.

## 11. Things not to say

- "Nobody does this." Say what we do and what we measured.
- "100%" or "solves prompt injection".
- Any number not in this file with a source, or in `shared/results/results.json`.
- That MNPI has leaked through an AI tool in a reported case. We found none.
- That Tavily or any sponsor endorses us.
