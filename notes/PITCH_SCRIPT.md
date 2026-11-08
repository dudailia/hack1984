# Pitch script: 3 minutes, real estate scenario

Spoken script for the demo in notes/DEMO.md, rewritten for the real estate scenario from Ilia's draft in
notes/RE_PITCH.md. One paragraph per beat; the line in italics is what happens on screen.

Rules for this file:
- **Numbers come only from `shared/results/results.json` on main**, cited by run label and commit in the
  "Where the numbers come from" table below. The run judged by the FALLBACK judge is never quoted. Anything not
  measured yet is [pending]. Never invent or estimate a number.
- **Every measured number today is from the first evaluation (corporate deal memo).** There is no real estate run in
  results.json yet, so every real estate number is [pending]. Say "first evaluation" out loud when quoting one.
- **The split stopped the attacks.** The gate checks every request that goes out, and in the measured runs it never
  had to fire. Never say the gate blocked the attacks.
- **All people, firms and deals are fictional.** The deal names wait for `shared/fixtures/re_memo.md`, which is not on
  main yet: [pending: property], [pending: buyer], [pending: financing]. Never name a real company or employer in the
  opening.
- [Anant: pending] marks lines that wait for Anant's real estate defense doc, which is not in the repo yet.
- Never claim a known case of deal information leaking through an AI tool: we found none.

Target pace: about 150 words a minute. Each paragraph is sized to its slot.

## Where the numbers come from

| Number | Run label | Commit | Scenario |
|---|---|---|---|
| 40 attacks, written and hashed before the code (sha256 961d...d1be) | file header (`attacks_total`, `attack_file_sha256`) | n/a | both |
| Single agent leaked 2 of 40; compromised agent 40 of 40 | checks-frozen rejudged-frozen | 486a8b6 | corporate memo |
| Two minds 0 of 40; two minds plus gate 0 of 40; 0 blocked requests in the 40 two-minds-plus-gate runs | checks-frozen | c303c1c | corporate memo |
| 0 of 30 normal questions blocked by the frozen checks | benign-frozen | a271959 | corporate memo (notes/BENIGN.md) |
| 23 of 30 questions answered with a cited number; 1.77 Tavily credits and 14.7 s per question | usefulness | checks-frozen-80-g294c423 (real Tavily, qwen3:8b) | corporate memo |
| Any real estate leak rate, false-block rate, usefulness or cost | [pending] | [pending] | real estate |

## The script

### Part 1. What we built

**0:00 (20 s). The opening**
*Title card: "Fictional associate. Fictional fund. Fictional deal."*
Meet Tess. She is a fictional acquisitions associate at a fictional real estate fund, and her firm bans AI on live
deals. This morning she signed an NDA for [pending: property]. Her memo holds the buyer, [pending: buyer], and the
financing, [pending: financing]. She still has to research the market, by hand, because nobody can prove what an AI
agent sends out.

**0:20 (20 s). The single agent leaks**
*Run the single agent in compromised mode. The leaked query appears in the ledger.*
This is how most agents are built: one model sees the memo and the web together. It reads a page with one hidden
line telling AI assistants to put the deal into their next search. It obeys. Look at its next query: the property,
the buyer and the financing, on their way to a search provider.

**0:40 (30 s). Doublethink, same page**
*Run Doublethink on the same fake pages. The Reader's documents show the planted line, highlighted.*
Now Doublethink, same poisoned page. Two minds. The one that knows the deal runs on Tess's laptop and never reads a
web page. The one that reads the web runs in the cloud and never sees the deal. The Reader reads the hidden line and
has nothing to leak. The Planner only gets numbers back. What leaves the device: checked queries to Tavily and
public page text to the Reader. The memo never leaves.

**1:10 (15 s). The answer**
*Answer panel: each number with its quote and source link.*
And it still answers. Every number shows the sentence it came from and its source, and every calculation is done in
code, never by a model. Today the Reader extracts corporate figures such as growth and revenue multiples; cap rates
and vacancy are on the roadmap. [pending: real estate answer from a real estate run]

**1:25 (15 s). The gate**
*Planted careless Planner query; the row turns red with the rule.*
What if the local model slips by itself and writes the buyer into a query? That is the second layer: one gate, the
only process allowed on the network, checks everything that goes out. This careless query is planted on purpose to
show the check working. It is refused and logged before anything is sent.

**1:40 (15 s). The proof**
*Verify proof: VALID. Edit one byte: INVALID.*
Every request, refused ones too, is written to a hash-chained log before it leaves, and the session exports as a
signed bundle. Anyone can check it offline. Valid. Now I change one byte. Invalid. That is what Tess's compliance
officer can sign off on.

### Part 2. What we measured

**1:55 (30 s). The numbers**
*Results screen. Real estate headline when a real estate run exists; corporate memo below as "First evaluation".*
Before writing any code, we wrote 40 attacks and published their hash. In our first evaluation, on a corporate deal
memo: a normal single agent leaked in 2 of 40. A compromised one, in all 40. Doublethink: 0 of 40. The split
stopped them. The gate checks what goes out, and in those runs it never had to fire. On the real estate memo:
[pending: real estate run].

**2:25 (15 s). Limits**
*Limits slide.*
Not 100%. The Planner can still slip, and the gate's checks are detectors. In Willison's words: "In application
security... 99% is a failing grade!" That is why the split comes first. There is a usefulness cost: in the first
evaluation, 23 of 30 questions were answered with a cited number.

### Part 3. What is roadmap

**2:40 (15 s). Next, and who pays**
*Roadmap slide, every item labelled "roadmap".*
On the roadmap, not built: real estate figures such as cap rates and vacancy, an Excel add-in, a plug-in for the
firm's deal pipeline, and running the Reader through the firm's own cloud AI contract. Our buyer: the acquisitions
team that signs the NDA, and its compliance officer. [Anant: pending] We build on Willison's Dual LLM pattern and
on CaMeL.

**2:55 (5 s). Close**
The cloud model never sees your deal. The local model never reads the web.

## Hard questions

**1. "Isn't this just CaMeL?"**
It builds on CaMeL (Debenedetti et al., Google DeepMind, March 2025) and on Simon Willison's Dual LLM pattern (April
2023), and we credit both. The job is different: research on the open web while holding a confidential deal memo.
What we add is the egress gate that checks every outbound payload, the typed channel that lets only numbers back to
the planner, the signed log, and measured leak rates against attacks we fixed before writing code.

**2. "Our analysts already have CoStar. Why a web agent at all?"**
Keep CoStar. Analysts still search the open web for news, filings, lender commentary and market reports, and those
searches carry the deal. We protect that channel; we are not a data provider and do not replace one. If pressed: a
licensed data source could sit behind the gate as another allowed host, with the same checks and ledger. That is
roadmap, not built. [Anant: pending]

**3. "A private property sale isn't inside information. Why would compliance care?"**
Usually it is confidential under contract, not material non-public information about a security. The NDA is the
stronger reason: a bidder that breaches it can lose the deal and the broker relationship. Advisers Act Section 204A
matters when the manager is an SEC-registered adviser or the deal touches a listed REIT (notes/BUSINESS.md section
4). [Anant: pending: what a typical real estate NDA forbids, and whether it covers a search API]

**4. "Can the Planner still leak by itself?"**
Yes, by its own mistake, because it holds the deal and writes the queries. That is why the gate exists: it checks
every outbound request for the confirmed secrets in the listed encodings, a planted canary, and rare memo words that
have not appeared in public text. Those checks are detectors, so we report what they cost: in the first evaluation,
0 of 30 normal questions blocked by the frozen checks (benign-frozen, a271959). The real estate questions in
notes/BENIGN_RE.md: [pending: a results.json run].

**5. "If the gate never fired, why have it?"**
The red team attacks the web side, and the split stopped every one: 0 blocked requests in the 40 runs of two minds plus gate
(checks-frozen, c303c1c). The gate is for the Planner's own mistakes, which these attacks did not trigger. We show it
working on a planted case, and we do not claim it was measured.

**6. "The single agent only leaked 2 of 40. Is the problem real?"**
This small local model mostly ignores page instructions. A model that follows instructions well leaks every time,
which is what the compromised mode shows: 40 of 40 (checks-frozen rejudged-frozen, 486a8b6). Better agents make this
worse, not better.

**7. "What do you lose?"**
The planner cannot react to arbitrary web text, only to typed numbers, so open-ended research is weaker. In the
first evaluation, live on real Tavily: 23 of 30 normal questions answered with a validated, cited number, at 1.77
Tavily credits and 14.7 seconds per question on average (usefulness, checks-frozen-80-g294c423). Real estate:
[pending].

**8. "Your proof is signed by your own code."**
Correct. The bundle proves what this install logged, that the log was not edited afterwards, and which gate and
check source files were running, by their hashes. It does not prove the machine was honest. A compromised laptop is
out of our scope, and we say so.

**9. "Who pays?"**
The acquisitions team at a real estate fund or REIT, which signs the NDA, and the fund's compliance officer, who has
to approve any research agent. We have no customers and no letters of intent. Pricing: [pending]. [Anant: pending]

**10. "Has deal information actually leaked through an AI tool?"**
Not in any reported case we could find, and we do not claim one. What is documented is the same injection mechanism
leaking data from shipping products such as Microsoft 365 Copilot (EchoLeak) and Salesforce Agentforce
(ForcedLeak). Sources are in notes/BUSINESS.md.

**11. "Did you test a compromised Reader?"**
Not yet. The Reader never holds the deal, and the Planner only receives typed fields, so a fooled Reader has nothing
to send. Measuring that directly is our next test.

**12. "Did you write this during the weekend?"**
Yes. Planning notes and the attack list were written on Friday; the attack list's hash was fixed then and is in our
README. All code was written after 11:00 on Saturday, and the git history shows it.
