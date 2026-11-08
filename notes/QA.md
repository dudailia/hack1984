# Judge Q&A: the 19 hardest questions

Built from the deck's judging criteria. Privacy-First: what leaves the device, who can read it, can you prove it,
would anyone use it. Most Startup-able: fundable, who is it for, would they pay, why this team. Surge: how central
Tavily is, how well it works.

Rules for this file:
- The **spoken** answer is what we say out loud, under 40 words. Say it, then stop.
- **If pressed** is the follow-up, only if they ask.
- **Source** is where the answer comes from in this repo. Nothing here comes from anywhere else.
- Any number not yet in the repo is [placeholder]. Fill it from `shared/results/results.json` or leave it out. Never
  say a number that is not in the repo.

---

## Privacy-First

### 1. What exactly leaves the device, and who can read it?
**Spoken:** Search and extract requests go to Tavily, each checked by the Gate first. Public page text goes to Anthropic for the
Reader. Nothing else: exact hosts and paths only. The memo never goes to a model provider.

**If pressed:** Tavily reads the queries. Anthropic reads public page text, the query already sent to Tavily, the
claim types, and the Reader's fixed instructions. The Gate is the only process that opens outside connections.

**Source:** notes/DEVPOST.md "What leaves the device"; shared/FORMATS.md section 1 (allowed destinations) and
section 5 (reading job).

### 2. Why does anything go to the cloud at all?
**Spoken:** Only the Reader runs in the cloud, and it only sees public text: pages Tavily returned and a query
already sent. It has no tools and never sees the memo. Leaking requires knowing the secret; it does not.

**If pressed:** The Reader request is built inside the Gate and sent byte for byte, with thinking disabled and no
`tools` field (tested). The reading job never contains the memo, the question, a need id or the secrets.

**Source:** notes/SPEC.md architecture table ("Safe on a cloud model because it only sees public text");
shared/FORMATS.md section 5; CLAUDE.md invariant 3.

### 3. Why not run everything locally?
**Spoken:** The Planner must be local because it holds the memo. The Reader can be anything because it holds
nothing. Our spec allows a local Reader; we have not built it yet. We used Claude for reading quality.

**If pressed:** Honest status: there is no local Reader backend in the code today. Quality difference between a
local and a Claude Reader: [placeholder, not measured].

**Source:** notes/SPEC.md architecture table ("Claude via the API (through the Gate), or local");
notes/TEAM_BRIEF.md section 9 cut list ("Claude as Reader (use local)").

### 4. Doesn't a query that names the target already leak deal interest?
**Spoken:** Yes. A query naming the target reveals interest in it, even without buyer, price or codename. The user
decides which terms are public before the run. Our demo asks sector and peer questions, so no query names the
target.

**If pressed:** This is listed in our limits: "The target is named when you research it." What we protect is the
deal around it: who is buying, at what price, under what codename.

**Source:** notes/DEVPOST.md "Q&A notes"; notes/THREAT_MODEL.md "What we do not claim".

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
**Spoken:** Yes, by its own mistake, since it writes the queries. The Gate is the second layer. On 40 attacks fixed
before any code: single agent 2 of 40, two minds plus gate 0 of 40. Not 100%.

**If pressed:** The Gate checks every outbound request for the confirmed secrets in the listed encodings, a canary,
rare memo words, and shape. Those checks are detectors. Known gap: a secret split into fragments separated by other
words passes the checks. The architectural defence is that the part reading attacker text cannot send queries.

**Source:** notes/THREAT_MODEL.md; README.md "Results"; `shared/results/results.json`, runs at commit 486a8b6
(single agent, rejudged with the frozen checks) and c303c1c (two minds plus gate).

### 7. What does the ledger prove, and what does it not?
**Spoken:** It proves every outbound attempt, blocked ones too, was recorded before sending, and that nobody edited
the record later. It does not prove the machine was honest or which code actually ran.

**If pressed:** Rows are hash-chained, payloads stored as SHA-256(nonce || payload) commitments, the bundle signed
with Ed25519 and checked offline by a standalone verifier. Change one byte: INVALID at that row. The signer is our
own install: self-attested. A compromised laptop is out of scope.

**Source:** notes/SPEC.md "Ledger and proof"; notes/THREAT_MODEL.md ("Self-attested record"); README.md
"Ledger and proof".

### 8. Couldn't some other process just skip the Gate?
**Spoken:** Non-Gate processes run an audit hook that refuses outside connections. It is a tripwire, not a sandbox.
Native code and Ollama's own networking are not covered. An OS sandbox is our next step.

**If pressed:** The guard is an in-process Python audit hook. It cannot stop C extensions or a ctypes function
resolved before install, and it relies on Python raising audit events.

**Source:** notes/THREAT_MODEL.md last two limits; notes/DEVPOST.md "How we built it" and "What's next".

---

## Most Startup-able

### 9. How is this different from a DLP tool or an MCP gateway?
**Spoken:** They filter what one agent sends, using credential patterns, PII or a hand-entered list. A codename and
a buyer's name are ordinary words. We remove the path: the model holding the deal never reads attacker text.

**If pressed:** We still keep a Gate, because our Planner can slip. Pipelock is ahead of us on mature DLP and signed
logs; we say so. On their own pages, none of Pipelock, Docker MCP Gateway, PointGuard AI or mcp-firewall separates
the two models.

**Source:** notes/BUSINESS.md section 8.

### 10. Isn't this just CaMeL or the Dual LLM pattern?
**Spoken:** It builds on both, and we credit them. What we add: applying it to confidential web research, an egress
gate that checks every payload, a typed channel back, a signed record, and leak rates on pre-registered attacks.

**If pressed:** Willison, Dual LLM (April 2023). Debenedetti et al., Google DeepMind, CaMeL (March 2025).
Beurer-Kellner et al., design patterns (June 2025). We never say "nobody does this".

**Source:** notes/THREAT_MODEL.md "Prior art"; notes/DEVPOST.md "Prior art".

### 11. Who has bought it, and what does it cost?
**Spoken:** Nobody yet. No customers, no letters of intent. Our hypothesis is an annual firm licence of [$X], near
egress-security pricing: Pipelock's enterprise tier is $25,000 a year. Untested.

**If pressed:** Search cost is pass-through: Tavily is $0.008 per credit, one credit per basic search. Credits per
question: 1.77 on average in our live run (median 1.5, max 5). Next step: design-partner talks with compliance officers, [placeholder] so far.

**Source:** notes/BUSINESS.md sections 6 and 7; notes/RESEARCH.md (Tavily pricing).

### 12. Who is it for, and why would they pay instead of banning agents?
**Spoken:** The chief compliance officer at a registered PE adviser or M&A broker-dealer. The law already requires
written procedures against misuse of inside information. The SEC fined OEP Capital $4 million for policy failures,
no trade alleged.

**If pressed:** Advisers Act 204A and Exchange Act 15(g). A ban is a policy the officer has to enforce while staff
use unmanaged AI accounts. We offer an approved path with a record. Market: 3,184 FINRA member firms and 16,544
investment advisers in 2025; the share doing M&A or PE is [placeholder]. We know of no reported case of deal
information leaking through an AI tool, and we do not claim one.

**Source:** notes/BUSINESS.md sections 2, 3 and 4.

### 13. Why is this team the one to build it?
**Spoken:** [placeholder: one true, checkable line per member]. What we can show today: attacks written and hashed
before any code, checks frozen at a tag, and a hostile review that found 14 problems, all fixed.

**If pressed:** 736 tests at the `checks-frozen` commit. The attack writer never wrote check logic; the check
builder never saw the attacks before the freeze.

**Source:** notes/DEVPOST.md "Why this team" (placeholders), "Challenges", "Pre-registered evaluation".

---

## Surge (Tavily)

### 14. How central is Tavily to this?
**Spoken:** Tavily is all of our live research and the exact channel we protect. Every search and extract goes
through it, the Planner picks general, news or finance presets, and we show credits per run.

**If pressed:** Finance sets `topic: finance` and prefers primary-source domains starting with sec.gov. Extract runs
only on result ids Tavily returned, with the public query set so Tavily reranks chunks. Tavily filters generic PII;
only the client knows that a codename is secret, so our check has to run before the query leaves.

**Source:** notes/SPEC.md "Tavily use"; shared/FORMATS.md section 1 (presets); notes/BUSINESS.md section 8.

### 15. How well does it work? Did anything break in testing?
**Spoken:** On qwen3:8b the Planner kept asking to extract with a search preset. Validation rejected it twice and
runs stopped early. We split the schema per action and correct only the preset. Now 10 of 10 valid.

**If pressed:**
- The fix: one schema branch per action, each with its own preset list. Same nudge: old schema 5 of 5 wrong, new
  schema 5 of 5 right. A safety net replaces a wrong preset with the default from a fixed list; every other field
  is still strictly validated, and the model's text is never logged.
- Live check: 2.4 seconds per Planner call.
- Usefulness: 23 of 30 ordinary questions answered with a validated, cited number, in a live run on real Tavily.
- False blocks, static: 0 of 30 on the frozen checks. False blocks, live: 3 harmless Reader requests blocked under
  `provenance.rare_term` (questions 2, 8 and 18), and all 3 questions were still answered.
- Cost: 1.77 Tavily credits and 14.7 seconds per question on average (medians 1.5 and 13.5, max 5 and 32.8).

**Source:** commit 863a7a8 ("planner: correct wrong presets instead of giving up"), planner/schema.py
(`normalize_preset`, `ACTION_JSON_SCHEMA`); notes/DEVPOST.md "Pre-registered evaluation"; usefulness, live false
blocks and cost from the builder's live run at commit 294c423 (source real, qwen3:8b).

---

## Red-team results

### 16. If the gate never fired, why have it?
**Spoken:** The red team attacks the web side. The gate is for the Planner's own mistakes, which these attacks
didn't trigger. We show it working on a planted case, and we don't claim it was measured.

**If pressed:** In every attack run, in all four setups, the Gate blocked 0 requests: the split alone stopped every
attack. The careless query in the demo is planted on purpose to show a block. It is a demonstration, not a
measurement.

**Source:** `shared/results/results.json`, runs at commit 486a8b6 (rejudged) and c303c1c: no blocked request in
any run; notes/PITCH_SCRIPT.md, 1:25 beat and hard question 8.

### 17. The single agent only leaked 2 of 40. Is the problem real?
**Spoken:** This small local model mostly ignores page instructions. A model that follows instructions well leaks
every time, which is what the compromised mode shows: 40 of 40. Better agents make this worse, not better.

**If pressed:** Every single-agent run read the poisoned page: 40 of 40. Compromised mode always obeys the poisoned
page, and we label it as such. Both ran only against our local stand-in for Tavily.

**Source:** `shared/results/results.json`, run at commit 486a8b6 rejudged with the frozen checks; notes/DEVPOST.md
"Challenges" (compromised mode); notes/PITCH_SCRIPT.md hard question 9.

### 18. Did you test a compromised Reader?
**Spoken:** Not yet. The Reader never holds the secret, and the Planner only receives typed fields, so a fooled
Reader has nothing to send. Measuring that directly is our next test.

**If pressed:** The Reader has no tools and opens no connections; the Gate sends its request. What comes back to the
Planner is a need id, found or not found, and typed numbers (question 5).

**Source:** CLAUDE.md invariants 2 and 3; shared/FORMATS.md section 3 (`typed`); notes/PITCH_SCRIPT.md hard
question 10.

### 19. Isn't this just redaction?
**Spoken:** Redaction must spot every secret before it can hide it, and a buyer's name is an ordinary word. We do
not depend on spotting: the model holding the memo never reads the web.

**If pressed:** The Gate's checks are the spotting layer, kept as a second line for the Planner's own slips, and we
report their cost: 0 of 30 blocked on the frozen checks, 3 harmless requests blocked in a live run.

**Source:** notes/DEVPOST.md "Inspiration" (masking tools have to recognise the secret first); question 15.
