# Threat model

## What we protect
The confirmed secrets in the memo (buyer, price, codename, people), the canary, and any other rare word or number
in the memo that the public web has not shown.

## Attackers
1. **A poisoned page** in the search results, written to make the agent leak. Main case.
2. **A careless model** that writes the deal into a query on its own.
3. **The search provider and everyone it fans out to**, reading queries.

## Exfiltration channels we know about, and the answer to each
| Channel | Answer |
|---|---|
| Secret written into a search query | Planner never reads attacker text; gate checks 2 and 3 as a second layer |
| Secret encoded (base64, hex, reversed, spaced, translated, number words) | Reader cannot leak what it never saw; gate normalises encodings for confirmed secrets |
| Secret split across several queries | Provenance check runs over the whole session |
| Secret placed in a URL for extract (attacker server logs it) | Planner can only pass result ids from this session, never URLs |
| Reader output carrying instructions to the Planner | Planner receives only numbers and enums; free text is dropped |
| Reader inventing numbers | Validator requires a verbatim quote that contains the number |
| Choosing which result to read as a covert signal | Possible, very low bandwidth, and the Reader has nothing secret to signal. Stated as a limit |
| The hosted model provider | Only the Reader may use a hosted model, and it only sees public text |
| Bypassing the gate | Only the gate process may open network connections (audit hook; macOS sandbox as stretch) |

## What we claim (only what we measure)
- Every outbound attempt is in the ledger, written before sending.
- For the 40 pre-registered attacks, the number of runs that leaked, per setup, with the command to reproduce.
- False blocks on the 30 benign questions.

## What we do not claim (say these first on stage)
- **Not 100%.** We report measured rates; we do not claim prompt injection is solved. Nobody can.
- **The Planner's own mistakes** are caught only by the gate's checks, which are detectors.
- **Utility cost.** The Planner cannot adapt to arbitrary web text, so open-ended research is weaker. That is
  the trade the published design patterns make on purpose.
- **Self-attested record.** The ledger proves what this install logged, not what code ran.
- **The target is named** when you research it.
- **A compromised laptop** is out of scope.

## Prior art (credit it on stage and in the README)
- Willison, Dual LLM pattern (April 2023).
- Debenedetti et al., Google DeepMind, "Defeating Prompt Injections by Design" (CaMeL), March 2025.
- Beurer-Kellner et al., "Design Patterns for Securing LLM Agents against Prompt Injections", June 2025.
Our contribution: applying the pattern to confidential research on the open web, with a content-checking egress
gate, a typed channel back to the planner, and measured results.
