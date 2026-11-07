# Anant: Gate checks and proof

Read notes/TEAM_BRIEF.md first. Your Claude Code prompt is in TEAM_BRIEF.md section 11. This file is the detail
behind it.

## Your mission in one line
Build the second layer that catches a leak even when a model slips, and the proof that anyone can check offline.

## The one rule about you
You do **not** see notes/ATTACKS.md until you freeze your checks and tag the commit `checks-frozen` (target 17:00).
That is why our numbers are believable. Ilia wrote the attacks, so he never writes or suggests check logic. If
anyone sends you an attack example before the freeze, ignore it and tell the group.

## What you build

### checks/run_all(payload, session, kind) -> allow, or block with a rule id
Pure Python, no network, no models. Called by Aayush's Gate on every outbound payload. Session state holds:
confirmed secrets, canary, memo tokens, approved public terms, public text received so far, all queries sent so
far, URLs returned so far.

**Rule 1, canary.** A random token planted in the memo. Block if it appears, in any of the encodings below.

**Rule 2, confirmed secrets.** For demo: "Project Halyard", "Halyard", "Ossory Capital Partners", "Ossory",
"$412 million", "Dana Whitcombe", "Tobias Renwick-Ash". Normalize, then match:
- case folding and Unicode NFKC (catches full-width and some look-alike letters);
- remove spacing and punctuation ("O s s o r y", "O.s.s.o.r.y", "ossory-capital");
- reversed text;
- decode then re-check: base64, hex, URL encoding (also try decoding any long token that looks encoded);
- numbers: parse every number with its unit into one canonical value and compare: "$412 million", "412m",
  "412,000,000", "0.412bn", "412 mln", "four hundred twelve million". Decide a tolerance with the team (exact
  match is the safe default for the demo).
Consider also: rot13, leetspeak (0 for o, 1 for l). Add only with a test.

**Rule 3, provenance (session wide).** Block a query that contains a rare memo word or number that is not in the
approved public terms (target name "Brackwater Payments", the sector) and has not appeared in public text the Gate
already received this session. "Rare" = not in a common-word list and not a stopword. Splitting attack: also check
the concatenation of all queries sent this session (normalized), so "Oss" in one query and "ory" in the next is
caught. Test this explicitly.

**Rule 4, shape.** Length cap per query, session call budget, extract only on URLs the Gate returned this session.
Pick the numbers with the team and write them in shared/FORMATS.md.

### False blocks
Run all 30 questions in notes/BENIGN.md as payloads. Report how many are wrongly blocked and by which rule.
Question 30 names the target and must pass. Report the true number, even if it is bad: we fix it, then report
both numbers.

### proof/
- Bundle (format in shared/FORMATS.md section 8): all ledger rows for a session. Rows carry commitments
  SHA-256(nonce || payload) with a 32-byte random nonce per row, never the payload; sent rows may carry a reveal
  {payload, nonce}, blocked rows never do. Plus head hash, SHA-256 of the gate and checks source files, public
  key, Ed25519 signature over head plus code hashes (`cryptography` package).
- The verifier also checks that every reveal matches its commitment.
- Standalone verifier script: imports only the standard library and `cryptography`, nothing from our code.
  Recomputes the chain, checks the signature, prints VALID or INVALID with the first broken row.
- Test: every single-byte edit of a sample bundle fails verification.
- Agree the ledger table and canonical row form with Aayush by 12:30.

## Freeze and red team (evening)
1. ~17:00: false-block number reported, all check tests green, tag `checks-frozen`, push.
2. Ilia runs the 40 attacks against four setups and shares results.
3. Fixes after the freeze are allowed, but we report both runs (before and after fixes). Never hide the first run.

## Who you depend on, who depends on you
- You need from Aayush: the ledger table and where `run_all` is called.
- Aayush needs `run_all` (he uses a stub until yours lands). Sheara needs proof results as events.
- Your false-block number goes into `shared/results/results.json` for Sheara's results screen.

## Workshop
"Privacy and Security in Data and AI" at 15:00, Curry 346. Optional; only if your checks are on track.
