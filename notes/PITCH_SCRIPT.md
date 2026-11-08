# Pitch script: 3 minutes, real estate scenario

Spoken script for the demo in notes/DEMO.md, for the real estate scenario. Built from Ilia's draft in
notes/RE_PITCH.md and Anant's pitch and defense document (sections 1, 6, 7 and 10). One paragraph per beat; the line
in italics is what happens on screen.

Rules for this file:
- **Numbers come only from three sources**, cited in the "Where the numbers come from" table below:
  `shared/results/results.json` on main (by run label and commit), `shared/results/usefulness/live_blocks.md`, and
  the exposure check on the demo-laptop ledger (to become `shared/results/exposure.md`). The run judged by the
  FALLBACK judge is never quoted. Anything not measured yet is [pending]. Never invent or estimate a number.
- **Every measured number today is from the first evaluation (corporate deal memo).** There is no real estate run in
  results.json yet, so every real estate number is [pending]. Say "first evaluation" out loud when quoting one.
- **The split stopped the attacks.** The gate checks every request that goes out, and in the measured runs it never
  had to fire. Never say the gate blocked the attacks.
- **Built, measured and roadmap stay separate.** Office, Copilot, Azure, Bedrock and MCP integrations, and any
  integration with a deal management platform, are roadmap. Never describe them as built.
- **All people, firms and deals are fictional.** The deal names are the ones Ilia set for the film (property
  "Larkmoor Wharf", buyer "Fund IV", $42.5 million financing) until `shared/fixtures/re_memo.md` lands. Never name a
  real company or employer, including the company behind Anant's co-op: say "a commercial real estate deal
  management platform".
- Never claim a known case of deal information leaking through an AI tool: we found none.

Target pace: about 150 words a minute. Each paragraph is sized to its slot; the slots add up to 3:00.

## Where the numbers come from

| Number | Source | Run label | Commit | Scenario |
|---|---|---|---|---|
| 40 attacks, written and hashed before the code (sha256 961d...d1be) | results.json file header (`attacks_total`, `attack_file_sha256`) | n/a | n/a | both |
| Single agent leaked 2 of 40; compromised agent 40 of 40 | results.json | checks-frozen rejudged-frozen | 486a8b6 | corporate memo |
| Two minds 0 of 40; two minds plus gate 0 of 40; 0 blocked requests in the 40 two-minds-plus-gate runs | results.json | checks-frozen | c303c1c | corporate memo |
| 0 of 30 normal questions blocked by the frozen checks | results.json | benign-frozen | a271959 | corporate memo (notes/BENIGN.md) |
| 23 of 30 questions answered with a cited number; 1.77 Tavily credits and 14.7 s per question | results.json | usefulness | checks-frozen-80-g294c423 (real Tavily, qwen3:8b) | corporate memo |
| 3 harmless requests blocked in the live run (questions 2, 8 and 18, rule `provenance.rare_term`; all 3 still answered) | `shared/results/usefulness/live_blocks.md` | usefulness | 294c423 | corporate memo |
| Every run read the poisoned page | exposure check, demo-laptop ledger (to become `shared/results/exposure.md`) | n/a | n/a | corporate memo |
| Any real estate leak rate, false-block rate, usefulness or cost | [pending] | [pending] | [pending] | real estate |

## The script

### Part 1. What we built

**0:00 (20 s). The opening**
*Title card: "Fictional associate. Fictional fund. Fictional deal."*
Meet Tess, a fictional acquisitions associate. Her firm bans AI on live deals. She is evaluating Larkmoor Wharf for
Fund IV, with $42.5 million of financing. She has the financials, sponsor ownership, lender quotes, underwriting
assumptions and investment committee notes. She wants AI to research comparable transactions and financing
conditions, but her firm cannot risk disclosing the deal to an outside AI service.

**0:20 (20 s). The single agent leaks**
*Run the single agent in compromised mode. The leaked query appears in the ledger.*
This is how most agents are built: one model sees the memo and the web together. It reads a page with one hidden
line telling AI assistants to put the deal into their next search. It obeys. Look at its next query: the property,
the buyer and the financing, on their way to a search provider.

**0:40 (25 s). Doublethink, same page**
*Run Doublethink on the same fake pages. The Reader's documents show the planted line, highlighted.*
Now Doublethink, same poisoned page. A local model reads the confidential deal and plans the research; it never
reads a web page. A cloud Reader examines public sources and never receives the memo. The Reader reads the hidden
line and has nothing to leak. What leaves the device: checked queries to Tavily and public page text to the Reader.

**1:05 (15 s). The answer**
*Answer panel: each number with its quote and source link.*
And it still answers. Every number shows the sentence it came from and its source, and every calculation is done in
code, never by a model. Today the Reader extracts corporate figures such as growth and revenue multiples; cap rates
and vacancy are on the roadmap. [pending: real estate answer from a real estate run]

**1:20 (15 s). The gate**
*Planted careless Planner query; the row turns red with the rule.*
What if the local model slips by itself and writes the buyer into a query? That is the second layer: one gate, the
only process allowed on the network, checks everything that goes out. This careless query is planted on purpose to
show the check working. It is refused and logged before anything is sent.

**1:35 (15 s). The proof**
*Verify proof: VALID. Edit one byte: INVALID.*
Every request, refused ones too, is written to a hash-chained log before it leaves, and the session exports as a
signed bundle. Anyone can check it offline. Valid. Now I change one byte. Invalid.

### Part 2. What we measured

**1:50 (25 s). The numbers**
*Results screen. Real estate headline when a real estate run exists; corporate memo below as "First evaluation".*
Before writing any code, we wrote 40 attacks and published their hash. In our first evaluation, on a corporate deal
memo: a normal single agent leaked in 2 of 40. A compromised one, in all 40. Doublethink: 0 of 40, and every run read
the poisoned page. The split stopped them; the gate checks what goes out and never had to fire. Real estate:
[pending].

**2:15 (15 s). Limits**
*Limits slide.*
Not 100%. The gate's checks are detectors. In Willison's words: "In application security... 99% is a failing
grade!" That is why the split comes first. Usefulness has a cost: 23 of 30 questions answered with a cited number,
and in a live run the gate blocked 3 harmless requests.

### Part 3. What is roadmap

**2:30 (15 s). Next, and who pays**
*Roadmap slide, every item labelled "roadmap".*
Roadmap, not built: an Office add-in where analysts already work, a provider adapter for the firm's approved cloud
model, such as Azure OpenAI or Bedrock, and real estate figures like cap rates. The buyer: a Head of Acquisitions or
Managing Partner, with IT and security approval. We build on Willison's Dual LLM pattern and on CaMeL.

**2:45 (15 s). Close**
One of us spent months building a commercial real estate deal management platform: sponsor ownership, lender quotes
and investment decisions in one workflow. We are not asking firms to abandon their AI tools. The cloud model never
sees your deal. The local model never reads the web.

## Hard questions

**1. "Isn't this just CaMeL?"**
It builds on CaMeL (Debenedetti et al., Google DeepMind, March 2025) and on Simon Willison's Dual LLM pattern (April
2023), and we credit both. The job is different: research on the open web while holding a confidential deal memo.
What we add is the egress gate that checks every outbound payload, the typed channel that lets only numbers back to
the planner, the signed log, and measured leak rates against attacks we fixed before writing code.

**2. "Why not enterprise Copilot?"**
Enterprise protections may be suitable for many workflows, and we do not claim Copilot is insecure. Doublethink
addresses a stricter requirement: the confidential memo never enters any cloud model.

**3. "Can it plug into Copilot today?"**
No. Built today: a local Ollama Planner, Tavily search, a Claude Reader, the gate and the signed ledger. Office,
Copilot, Azure, Bedrock and MCP integrations are roadmap.

**4. "Why does a deal management platform need this?"**
Deal software organizes private transactions. Doublethink adds outside research while keeping the public evidence
separate from the confidential sponsor, loan and underwriting context. Plugging into such a platform is roadmap.

**5. "Our analysts already have CoStar. Why a web agent at all?"**
Keep CoStar. Analysts still search the open web for news, filings, lender commentary and market reports, and those
searches carry the deal. We protect that channel; we are not a data provider and do not replace one. A licensed data
source could sit behind the gate as another allowed host, with the same checks and ledger. That is roadmap, not
built.

**6. "Why real estate first?"**
Real estate acquisitions matches the deal workflow directly: one deal holds sponsor ownership, lender quotes and
underwriting assumptions, and the team needs public evidence for each. It is our first niche; confidential financial
research is the broader category, with private equity and M&A, banks and lenders, and law firms next. The challenge
is to validate willingness to pay. Our teammate's experience gives workflow credibility, not customer validation.

**7. "A private property sale isn't inside information. Why would anyone care?"**
The memo is confidential transaction information: financing, sponsor relationships, underwriting and the investment
rationale. The firm's own rule is that it must not reach an outside AI service. Where the manager is an SEC-registered
adviser, Advisers Act Section 204A also requires written procedures against misuse of material non-public
information (notes/BUSINESS.md section 4). We do not claim every property deal is inside information.

**8. "Why not redact the memo?"**
Redaction may miss indirect identifiers, amounts and relationships. Doublethink structurally keeps the secret away
from the Reader, with the gate's checks as an additional safeguard.

**9. "What if the Planner puts the price in a query?"**
The gate examines every proposed outbound request and detects the variants of amounts and encodings we tested. We do
not claim coverage of every possible transformation. Those checks are detectors, so we report what they cost: in the
first evaluation, 0 of 30 normal questions blocked by the frozen checks (benign-frozen, a271959), and 3 harmless
requests blocked in the live run (`shared/results/usefulness/live_blocks.md`). Real estate questions in
notes/BENIGN_RE.md: [pending: a results.json run].

**10. "If the gate never fired, why have it?"**
The red team attacks the web side, and the split stopped every one: 0 blocked requests in the 40 runs of two minds
plus gate (checks-frozen, c303c1c). The gate is for the Planner's own mistakes, which these attacks did not trigger.
We show it working on a planted case, and we do not claim it was measured.

**11. "The single agent only leaked 2 of 40. Is the problem real?"**
Two confidentiality failures in a small controlled sample are meaningful, but they are not a universal failure rate.
The compromised mode shows what obedience to a malicious page does: 40 of 40 (checks-frozen rejudged-frozen,
486a8b6). A model that follows instructions better leaks more, not less.

**12. "Can the Reader still lie?"**
Yes. A poisoned public page can contaminate the findings. The split addresses getting the secret out; checking the
evidence is a separate problem. Every number shows its quote and source so a person can check it.

**13. "How do you prove no data escaped?"**
We show the gate's monitored requests and a signed ledger anyone can verify offline. The bundle proves what this
install logged and that the log was not edited afterwards. Stronger claims depend on enforced egress isolation,
runtime integrity and an independent assessment.

**14. "What do you lose?"**
The planner cannot react to arbitrary web text, only to typed numbers, so open-ended research is weaker. In the
first evaluation, live on real Tavily: 23 of 30 normal questions answered with a validated, cited number, at 1.77
Tavily credits and 14.7 seconds per question on average (usefulness, checks-frozen-80-g294c423). Real estate:
[pending].

**15. "Who pays?"**
Likely a Managing Partner or Head of Acquisitions at a smaller firm, with IT and security approval; larger firms
bring in procurement and compliance. We have no customers and no letters of intent. Purchase intent and pricing are
unvalidated hypotheses.

**16. "Why wouldn't a firm build this itself?"**
Large firms could. A product could cut the cost of building the local and cloud split, the policy checks, the
research orchestration and the audit verification, but that value still has to be validated.

**17. "Has deal information actually leaked through an AI tool?"**
Not in any reported case we could find, and we do not claim one. What is documented is the same injection mechanism
leaking data from shipping products such as Microsoft 365 Copilot (EchoLeak) and Salesforce Agentforce
(ForcedLeak). Sources are in notes/BUSINESS.md.

**18. "Did you test a compromised Reader?"**
Not yet. The Reader never holds the deal, and the Planner only receives typed fields, so a fooled Reader has nothing
to send. Measuring that directly is our next test.

**19. "Did you write this during the weekend?"**
Yes. Planning notes and the attack list were written on Friday; the attack list's hash was fixed then and is in our
README. All code was written after 11:00 on Saturday, and the git history shows it.
