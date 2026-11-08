# Judge Q&A: the hardest questions, real estate scenario

Built from the deck's judging criteria. Privacy-First: what leaves the device, who can read it, can you prove it,
would anyone use it. Most Startup-able: fundable, who is it for, would they pay, why this team. Surge: how central
Tavily is, how well it works. Rewritten for the real estate scenario from Ilia's draft in notes/RE_PITCH.md and
Anant's pitch and defense document (sections 1, 6, 7 and 10).

Rules for this file:
- The **spoken** answer is what we say out loud, under 40 words. Say it, then stop.
- **If pressed** is the follow-up, only if they ask.
- **Source** is where the answer comes from in this repo. Nothing here comes from anywhere else.
- **Measured numbers come only from three sources:** `shared/results/results.json` on main (by run label and
  commit), `shared/results/usefulness/live_blocks.md`, and the exposure check on the demo-laptop ledger (to become
  `shared/results/exposure.md`). The run judged by the FALLBACK judge is never quoted. Anything not measured yet is
  [pending]. Never invent or estimate.
- **Every measured number is from the first evaluation (corporate deal memo).** Say "first evaluation" when quoting
  one. The real estate scenario (Larkmoor) is a demo, not a measurement: never put a 40-attack number next to
  Larkmoor or the real estate scenario. For real estate numbers, say "not measured: the real estate scenario is a demo".
- **The split stopped the attacks.** The gate checks what goes out and never had to fire in the measured runs. Never
  say the gate blocked the attacks.
- Business facts (law, fines, prices, market counts) are quoted only with their source in notes/BUSINESS.md.
- **Office, Copilot, Azure, Bedrock and MCP integrations, and any integration with a deal management platform, are
  roadmap.** Never describe them as built.
- The deal is fictional. Its names are the ones Ilia set for the film: codename "Project Larkmoor", property
  "Larkmoor Wharf", buyer "Fund IV", "$42.5 million financing", contacts Odile Farrant and Ruaridh Penhallow. Never
  name a real company or employer, including the company behind Anant's co-op: say "a commercial real estate deal
  management platform".

---

## Ground truth: built, measured, roadmap

Every answer below stays inside these three lists. If a question needs something from the third list, say
"roadmap".

### What we built (in the repo today)
- Planner on a local model (Ollama, qwen3:8b), which holds the memo and never reads web text.
- Reader on Claude, which reads public page text and never sees the memo. It has no tools; the Gate sends its
  request.
- The Gate, the only process with network access. It checks every outbound request (confirmed secrets in the listed
  encodings, a canary, rare memo terms, shape limits), and writes a hash-chained ledger before sending. Sessions export
  as an Ed25519-signed bundle, checked offline by a standalone verifier.
- Tavily search and extract with general, news and finance presets.
- A typed channel back to the Planner: a need id, found or not found, and numbers with type, unit, period and result
  id. Calculations are done in code.
- notes/BENIGN_RE.md: 30 normal real estate analyst questions (written; not measured: the real estate scenario is a demo).

### What we measured (results.json on main; first evaluation, corporate deal memo)

| Measurement | Value | Run label | Commit |
|---|---|---|---|
| Pre-registered attacks | 40 (sha256 961d...d1be) | file header | n/a |
| Single agent leaks | 2 of 40 | checks-frozen rejudged-frozen | 486a8b6 |
| Compromised agent leaks | 40 of 40 | checks-frozen rejudged-frozen | 486a8b6 |
| Two minds leaks | 0 of 40 | checks-frozen | c303c1c |
| Two minds plus gate leaks | 0 of 40, with 0 blocked requests | checks-frozen | c303c1c |
| Every run read the poisoned page | yes | exposure check, demo-laptop ledger (to become `shared/results/exposure.md`) | n/a |
| False blocks on normal questions (static, frozen checks) | 0 of 30 (notes/BENIGN.md) | benign-frozen | a271959 |
| Answered with a cited number (live, real Tavily) | 23 of 30 | usefulness | checks-frozen-80-g294c423 |
| Cost per question (live) | 1.77 Tavily credits, 14.7 s | usefulness | checks-frozen-80-g294c423 |
| Harmless requests blocked in the live run | 3 (questions 2, 8 and 18, rule `provenance.rare_term`; all 3 still answered) | `shared/results/usefulness/live_blocks.md` | 294c423 |

All rows above are the first evaluation, on the corporate deal memo. Real estate numbers: not measured: the real estate scenario is a demo.

### What is roadmap (not built: say "roadmap", never "we have")
- Real estate claim types: cap rate, vacancy, delinquency, loan rate, cost per square foot, REIT return. Today the
  Reader extracts revenue, growth, multiples, EBITDA, market size, employees and founded year.
- A real estate memo fixture and a real estate red-team and usefulness run.
- Office add-in: ask from where analysts already draft and model; numbers come back with quote and source. A local
  client is not automatically private (document storage, syncing, telemetry and the host application matter), so it
  needs a security review.
- Integration with a commercial real estate deal management platform: invoke Doublethink locally from the deal
  workspace, so the user does not paste the memo.
- A provider adapter for the firm's approved cloud model (Azure OpenAI or Bedrock) instead of our Anthropic key. This
  changes the Gate's exact host allowlist (CLAUDE.md invariant 5), so it is a reviewed change, not a setting. Only
  Claude is built.
- Copilot and MCP: exposing safe research as an agent tool. It cannot undo a secret already pasted into a cloud
  assistant, so it is only safe with local-first input. Not built.
- A local Reader backend, a licensed data source behind the Gate, and an OS sandbox for non-Gate processes.

---

## Privacy-First

### 1. What exactly leaves the device, and who can read it?
**Spoken:** Search and extract requests go to Tavily, each checked by the Gate first. Public page text goes to
Anthropic for the Reader. Nothing else: exact hosts and paths only. The deal memo never goes to a model provider.

**If pressed:** Tavily reads the queries. Anthropic reads public page text, the query already sent to Tavily, the
claim types, and the Reader's fixed instructions. The Gate is the only process that opens outside connections.

**Source:** notes/DEVPOST.md "What leaves the device"; shared/FORMATS.md section 1 (allowed destinations) and
section 5 (reading job).

### 2. Why does anything go to the cloud at all?
**Spoken:** Only the Reader runs in the cloud, and it only sees public text: pages Tavily returned and a query
already sent. It has no tools and never sees the memo. Leaking requires knowing the deal; it does not.

**Why not enterprise Copilot, then?** Enterprise protections may suit many workflows, and we do not claim Copilot is
insecure. We address a stricter requirement: the confidential memo never enters any cloud model.

**If pressed:** The Reader request is built inside the Gate and sent byte for byte, with thinking disabled and no
`tools` field (tested). The reading job never contains the memo, the question, a need id or the secrets.

**Source:** notes/SPEC.md architecture table; shared/FORMATS.md section 5; CLAUDE.md invariant 3.

### 3. Why not run everything locally?
**Spoken:** The Planner must be local because it holds the deal. The Reader can be anything because it holds
nothing. Our spec allows a local Reader; it is roadmap. We used Claude for reading quality.

**If pressed:** Honest status: there is no local Reader backend in the code today. Quality difference between a
local and a Claude Reader: [pending, not measured].

**Source:** notes/SPEC.md architecture table; "Ground truth: roadmap" above.

### 4. Doesn't a query that names the market or the property already leak interest?
**Spoken:** It can. A query naming the property or a narrow submarket reveals interest, even without buyer or price.
The user decides which terms are public before the run. Ask market questions, not property questions.

**If pressed:** This is in our limits: "The target is named when you research it." What we protect is the deal
around it: who is buying, at what price, with what financing. notes/BENIGN_RE.md is written as market-level
questions for this reason.

**Source:** notes/DEVPOST.md "Q&A notes"; notes/THREAT_MODEL.md "What we do not claim"; notes/BENIGN_RE.md.

### 5. What if the Planner is fooled through the typed fields?
**Spoken:** The Planner gets no words from the web. Only a need id, found or not found, and numbers with a fixed
type, unit, period and result id. A page can plant a false number. It cannot plant an instruction.

**If pressed:**
- A page could push text encoded as digits; numbers are capped at 15 digits (review finding R1-14, fixed).
- A false number on a page passes the Validator if the quote is verbatim. That gives a wrong figure with its source
  shown, not a leak. The next query still goes through the Gate.
- Choosing which result to read as a covert signal: possible, very low bandwidth, and stated as a limit.

**Source:** planner/schema.py (`_TYPED_KEYS`, `_VALUE_KEYS`); reader/numbers.py (`MAX_DIGITS = 15`);
notes/REVIEW_1.md R1-14; notes/THREAT_MODEL.md channel table.

### 6. Can the Planner still leak by itself? What is your real leak rate?
**Spoken:** Yes, by its own mistake, since it writes the queries. In our first evaluation, a corporate memo: single
agent 2 of 40, two minds plus gate 0 of 40. Not 100%.

**If pressed:** The Gate checks every outbound request for the confirmed secrets in the listed encodings, a canary,
rare memo words, and shape. Those checks are detectors. Known gap: a secret split into fragments separated by other
words passes the checks. The architectural defence is that the part reading attacker text cannot send queries.

**Source:** notes/THREAT_MODEL.md; `shared/results/results.json`: "checks-frozen rejudged-frozen" at 486a8b6 (single
agent) and "checks-frozen" at c303c1c (two minds plus gate).

### 7. What does the ledger prove, and what does it not?
**Spoken:** It proves every outbound attempt, refused ones too, was recorded before sending, and that nobody edited
the record later. It does not prove the machine was honest or which code actually ran.

**If pressed:** Rows are hash-chained, payloads stored as SHA-256(nonce || payload) commitments, the bundle signed
with Ed25519 and checked offline by a standalone verifier. Change one byte: INVALID at that row. The signer is our
own install: self-attested. A compromised laptop is out of scope.

**Source:** notes/SPEC.md "Ledger and proof"; notes/THREAT_MODEL.md ("Self-attested record"); README.md
"Ledger and proof".

### 8. Couldn't some other process just skip the Gate?
**Spoken:** Non-Gate processes run an audit hook that refuses outside connections. It is a tripwire, not a sandbox.
Native code and Ollama's own networking are not covered. An OS sandbox is roadmap.

**If pressed:** The guard is an in-process Python audit hook. It cannot stop C extensions or a ctypes function
resolved before install, and it relies on Python raising audit events.

**Source:** notes/THREAT_MODEL.md last two limits; notes/DEVPOST.md "How we built it" and "What's next".

---

## Most Startup-able

### 9. How is this different from a DLP tool or an MCP gateway?
**Spoken:** They filter what one agent sends, using credential patterns, PII or a hand-entered list. A fund name or
a property name is an ordinary word. We remove the path: the model holding the deal never reads attacker text.

**If pressed:** Filters are detectors. In Willison's words: "In application security... 99% is a failing grade!"
(his May 2023 prompt injection talk, https://simonwillison.net/2023/May/2/prompt-injection-explained/). We still
keep a Gate, because our Planner can slip. Pipelock is ahead of us on mature DLP and signed logs; we say so. On
their own pages, none of Pipelock, Docker MCP Gateway, PointGuard AI or mcp-firewall separates the two models.

**Source:** notes/BUSINESS.md section 8; the Willison quote as in PR #54.

### 10. Isn't this just CaMeL or the Dual LLM pattern?
**Spoken:** It builds on both, and we credit them. What we add: applying it to confidential deal research on the
open web, an egress gate that checks every payload, a typed channel back, a signed record, and measured leak rates.

**If pressed:** Simon Willison, Dual LLM pattern (April 2023). Debenedetti et al., Google DeepMind, CaMeL (March
2025). Beurer-Kellner et al., design patterns (June 2025). We never say "nobody does this".

**Source:** notes/THREAT_MODEL.md "Prior art"; notes/DEVPOST.md "Prior art".

### 11. Who has bought it, and what does it cost?
**Spoken:** Nobody yet. No customers, no letters of intent. Our hypothesis is an annual firm licence, price
[pending], near egress-security pricing. Untested.

**If pressed:** Pipelock's enterprise tier is $25,000 a year (notes/BUSINESS.md section 7). Search cost is
pass-through: Tavily is $0.008 per credit, one credit per basic search (notes/RESEARCH.md). Measured in the first
evaluation: 1.77 credits per question (usefulness, checks-frozen-80-g294c423). Design-partner talks: [pending].

**Source:** notes/BUSINESS.md sections 6 and 7; notes/RESEARCH.md; `shared/results/results.json` run "usefulness".

### 12. Who is it for, and why would they pay instead of banning agents?
**Spoken:** Real estate acquisitions teams: analysts and associates, with a Head of Acquisitions or Managing Partner
as buyer. Many firms simply ban AI on live deals. We offer an approved path with a record they can check.

**If pressed:** The buyer is likely a Managing Partner or Head of Acquisitions at a smaller firm, with IT and
security approval; larger firms bring in procurement and compliance. Purchase intent and pricing are unvalidated
hypotheses. A ban is a policy someone has to enforce while staff use unmanaged AI accounts. Where the manager is an SEC-registered adviser, Advisers Act Section 204A already requires written
procedures against misuse of material non-public information (question 21). We know of no reported case of deal
information leaking through an AI tool, and we do not claim one.

**Source:** notes/RE_PITCH.md sections 2 and 3; notes/BUSINESS.md section 4.

### 13. Why is this team the one to build it?
**Spoken:** Anant spent months building a commercial real estate deal management platform, with sponsor ownership,
lender quotes and investment decisions in one workflow. Sheara: "I build Python and MATLAB tools that simulate
rocket flight, orbital insertion and heat shield ablation, and this weekend I built Doublethink's interface."
[pending: one true, checkable line for each other member].
What we can show today: attacks written and hashed before any code, checks frozen at a tag, and a hostile review
whose findings are all fixed.

**If pressed:** The attack writer never wrote check logic; the check builder never saw the attacks before the
freeze.

**Source:** notes/DEVPOST.md "Why this team" (placeholders), "Challenges", "Pre-registered evaluation";
notes/REVIEW_1.md.

---

## Surge (Tavily)

### 14. How central is Tavily to this?
**Spoken:** Tavily is all of our live research and the exact channel we protect. Every search and extract goes
through it, the Planner picks general, news or finance presets, and we show credits per run.

**If pressed:** Extract runs only on result ids Tavily returned, with the public query set so Tavily reranks
chunks. Tavily filters generic PII; only the client knows that a fund or property name is secret, so our check has
to run before the query leaves.

**Source:** notes/SPEC.md "Tavily use"; shared/FORMATS.md section 1 (presets); notes/BUSINESS.md section 8.

### 15. How well does it work? Did anything break in testing?
**Spoken:** On qwen3:8b the Planner kept asking to extract with a search preset, and runs stopped early. We split
the schema per action and correct only the preset. In the first evaluation, 23 of 30 questions were answered with a
cited number.

**If pressed:**
- The fix: one schema branch per action, each with its own preset list. A safety net replaces a wrong preset with
  the default from a fixed list; every other field is still strictly validated, and the model's text is never
  logged.
- Usefulness and cost, live on real Tavily: 23 of 30 answered, 1.77 credits and 14.7 seconds per question on
  average (usefulness, checks-frozen-80-g294c423).
- False blocks, static: 0 of 30 on the frozen checks (benign-frozen, a271959). False blocks, live: 3 harmless
  Reader requests blocked under `provenance.rare_term` (questions 2, 8 and 18; evidence in
  `shared/results/usefulness/live_blocks.md`), and all 3 questions were still answered.
- Real estate questions (notes/BENIGN_RE.md): not measured: the real estate scenario is a demo.

**Source:** commit 863a7a8 ("planner: correct wrong presets instead of giving up"), planner/schema.py
(`normalize_preset`, `ACTION_JSON_SCHEMA`); `shared/results/results.json` runs "usefulness" and "benign-frozen".

---

## Red-team results

### 16. If the gate never fired, why have it?
**Spoken:** The red team attacks the web side, and the split stopped every attack. The gate is for the Planner's own
mistakes, which these attacks didn't trigger. We show it on a planted case, not as a measurement.

**If pressed:** Every run read the poisoned page (exposure check on the demo-laptop ledger, to become
`shared/results/exposure.md`). In the 40 runs of two minds plus gate, the Gate refused 0 requests: it checked
everything that went out and never had to fire. The careless query in the demo is planted on purpose to show a refusal. It is a
demonstration, not a measurement.

**Source:** `shared/results/results.json`, run "checks-frozen" at c303c1c: no blocked request in any attack;
notes/PITCH_SCRIPT.md, the gate beat and hard question 5.

### 17. The single agent only leaked 2 of 40. Is the problem real?
**Spoken:** This small local model mostly ignores page instructions. A model that follows instructions well leaks
every time, which is what the compromised mode shows: 40 of 40. Better agents make this worse, not better.

**If pressed:** Two confidentiality failures in a small controlled sample are meaningful, but not a universal
failure rate. Every run read the poisoned page (exposure check). Compromised mode always obeys the poisoned page, and
we label it as such. Both ran only against our local stand-in for Tavily, on the corporate memo.

**Source:** `shared/results/results.json`, run "checks-frozen rejudged-frozen" at 486a8b6; notes/DEVPOST.md
"Challenges" (compromised mode); notes/PITCH_SCRIPT.md hard question 6.

### 18. Did you test a compromised Reader?
**Spoken:** Not yet. The Reader never holds the deal, and the Planner only receives typed fields, so a fooled Reader
has nothing to send. Measuring that directly is our next test.

**If pressed:** The Reader has no tools and opens no connections; the Gate sends its request. What comes back to the
Planner is a need id, found or not found, and typed numbers (question 5).

**Source:** CLAUDE.md invariants 2 and 3; shared/FORMATS.md section 3 (`typed`).

### 19. Isn't this just redaction?
**Spoken:** Redaction must spot every secret before it can hide it, and a buyer's name is an ordinary word. We do
not depend on spotting: the model holding the memo never reads the web.

**If pressed:** The Gate's checks are the spotting layer, kept as a second line for the Planner's own slips, and we
report their cost: 0 of 30 normal questions blocked on the frozen checks in the first evaluation (benign-frozen,
a271959), and 3 harmless requests blocked in a live run (`shared/results/usefulness/live_blocks.md`). Redaction may
also miss indirect identifiers, amounts and relationships.

**Source:** notes/DEVPOST.md "Inspiration"; question 15.

---

## Real estate

### 20. "Our analysts already have CoStar. Why do they need a web agent at all?"
**Spoken:** Keep CoStar. Analysts still search the open web for news, filings, lender commentary and market reports.
Those searches carry the deal. We protect that channel; we are not a data provider.

**If pressed:** A licensed data source could sit behind the Gate as another allowed host, with the same checks and
ledger. That is roadmap, not built. Deal software organizes the private transaction; Doublethink adds outside
research while keeping the public evidence separate from the confidential sponsor, loan and underwriting context.

**Source:** notes/RE_PITCH.md section 5.

### 21. "A private property sale isn't inside information. Why would compliance care?"
**Spoken:** The memo is confidential transaction information: financing, sponsor relationships, underwriting and
the investment rationale. The firm's own rule is that it must not reach an outside AI service.

**If pressed:** Advisers Act Section 204A matters when the manager is an SEC-registered adviser handling material
non-public information, or the deal touches a listed REIT. We do not claim every property deal is MNPI.

**Source:** Anant's pitch and defense document, sections 1 and 6; notes/BUSINESS.md section 4.

### 22. "Why real estate first, and why wouldn't a firm build this itself?"
**Spoken:** Real estate acquisitions matches the deal workflow directly. It is our first niche; confidential
financial research is the broader category. Large firms could build it; a product cuts that cost, but the value
still has to be validated.

**If pressed:** Next niches: private equity and M&A (strong incumbent competition), banks and lenders (compliance and
procurement), law firms (specialized research needs). Our teammate's experience gives workflow credibility, not
customer validation.

**Source:** Anant's pitch and defense document, sections 6 and 7.

### 23. "Can the Reader still lie, and how do you prove nothing escaped?"
**Spoken:** Yes, a poisoned page can contaminate findings; the split addresses getting the secret out, and every
number shows its quote and source. For escape, we show monitored gate requests and a signed ledger anyone can verify.

**If pressed:** Stronger claims depend on enforced egress isolation, runtime integrity and an independent
assessment. A compromised laptop is out of scope.

**Source:** Anant's pitch and defense document, section 6; question 7.
