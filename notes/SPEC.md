# Doublethink: spec

## One line
A research agent for confidential work, split into two minds: the one that knows your secret never reads the web,
and the one that reads the web never learns your secret. Every byte that leaves goes through one gate and is
recorded.

## The problem
An agent that holds private data, reads untrusted web content and can send requests out can be steered by a
poisoned page into leaking that data (Willison's "lethal trifecta"). Filters that try to catch the leak on the
way out are detectors; Willison's point is that a detector that stops 95% is a failing grade. Host allowlists
answer "where", not "what": the leak rides inside an allowed request, such as a Tavily search query. And a search
query is not seen by one company only: Tavily fans out to several sources and engines in real time.

## Persona
An analyst at an M&A advisory boutique researching a target for a confidential mandate.

## Architecture

| Component | Sees | Can do | Runs on |
|---|---|---|---|
| **Planner** (privileged) | memo, user question, typed results only (numbers, units, periods, found or not found, result ids) | write research queries, decide follow-ups, choose which result ids to read | local model (Ollama). It holds the memo, so it never goes to a cloud model |
| **Reader** (quarantined) | one public query and the web text returned for it | output a strict schema of claims; no tools, no network | Claude via the API (through the Gate), or local. Safe on a cloud model because it only sees public text |
| **Gate** (egress) | every outbound payload, the confirmed secrets list, the memo's word list for the provenance check | the only process with network access; check, ledger, send to Tavily (and to Anthropic for the reader) | Python process |
| **Validator** (code, no model) | reader output plus the raw web text | keep a claim only if its quote appears verbatim in the fetched text, its number parses from the quote, and its URL came from this session | Python |
| **Composer** (code, no model) | validated claims | fill an answer template: numbers, quotes, citations | Python |
| **UI** | what the user is allowed to see | show memo, live ledger, blocked rows, answer with sources, proof check | static page on loopback with a per-launch token |

### Data flow for one research need
1. Planner writes a query (for example "payments processing sector growth 2025").
2. Gate checks it (confirmed secrets, provenance, shape), ledgers it, sends it to Tavily search.
3. Gate gives the results to the Reader, never to the Planner.
4. Reader returns claims in the strict schema. Validator drops anything that fails the checks.
5. Planner receives only typed fields per need. Free text from the web never reaches it.
6. Planner decides the next query. Repeat within a session budget.
7. Composer writes the answer for the user, with sources.

### Why this holds even when a model is fooled
- A poisoned page reaches only the Reader. The Reader does not know the secret, so it cannot leak it, and it has
  no tools, so it cannot send anything.
- The Planner knows the secret but never sees attacker text. Its only input from the web is numbers and enums.
- If the Planner still writes a careless query on its own, the gate's checks catch it as a second layer.
- What remains is narrow and is listed in THREAT_MODEL.md.

### Baseline for comparison (the "before" in the demo)
A single agent with the memo, the web text and the search tool in one context, the way most agents are built
today. Plus a "compromised agent" mode that always obeys the poisoned page, so the demo is predictable.

## Gate checks on every outbound query (second layer)
1. **Canary**: a random token planted in the memo. If it ever appears outbound, block.
2. **Confirmed secrets**: the user confirms what detection found (buyer, price, codename, people). Block them
   in any form: case, spacing, punctuation, number formats and number words, units ("$0.412bn"), base64, hex,
   URL encoding, reversed text, letters split by spaces.
3. **Provenance**: block a query containing a rare word or number from the memo that has not appeared in the
   user-approved public terms (the target name, the sector) or in public text the gate already received this
   session. Checked across the whole session, so splitting a secret over several queries is caught.
4. **Shape**: length cap, session call budget, extract only on URLs the gate itself returned this session.

Blocked attempts are ledgered with the rule that fired.

## Tavily use (Surge track)
- Search: `topic: finance` for company figures, `search_depth: basic` (1 credit), `max_results` 10,
  `include_domains` with mode `prefer` for primary sources (sec.gov, company investor-relations sites),
  `include_usage` to show credits per run.
- Extract: on chosen result ids only, with `query` set so Tavily reranks the chunks, `extract_depth: advanced`
  when tables matter (2 credits per 5 URLs).
- Show credits per research run in the UI.
- Event code HACK1984 gives 8,000 Tavily credits (valid Nov 6 to 9). Exa code EXA50NORTHEASTERN gives $50.

## Ledger and proof
- Append-only SQLite, one row per outbound attempt, written before sending: sequence, time, session, component,
  destination, exact bytes, status, rule, previous hash, hash.
- Bundle signed with Ed25519 (via the `cryptography` package: the standard library has no Ed25519, and writing
  our own crypto at a hackathon is a red flag), plus a standalone verifier.
- Private values stored as salted digests so the bundle can be shared.
- Stretch: the macOS kernel sandbox on the Planner and Reader processes, so the isolation is enforced by the OS
  and not only by our code.

## Measurements (each reproducible with one command)
1. **Attacks**: the 40 pre-registered payloads (hash fixed Friday). For each setup (single agent, compromised
   agent, two minds, two minds plus gate): how many runs leaked a confirmed secret or the canary.
2. **False blocks**: the 30 questions in BENIGN.md. How many the gate wrongly blocked.
3. **Usefulness**: on the same 30, share answered with a validated, cited number.
4. **Cost and time**: Tavily credits and seconds per question.
5. **Proof**: the verifier rejects every single-byte edit of a sample bundle.

## MVP (by 21:00 Sat)
Gate with Tavily search and extract, checks 1 to 4, ledger; Planner and Reader with the strict schema and
validator; single-agent baseline and compromised mode; one live run on a real public company; bundle and verifier;
UI running the demo.

## Stretch, in order
UI polish; full attack and false-block numbers; macOS sandbox; MCP server version.

## Team split
See notes/TEAM_BRIEF.md section 7 and the personal files (AAYUSH.md, ANANT.md, ILIA.md, SHEARA_UI.md).
