# Interfaces (starting point; shared/FORMATS.md replaces this once agreed)

Field names are suggestions. The team fixes them at 11:15 in shared/FORMATS.md and nobody changes one without
telling the group chat.

## 1. Planner to Gate: research request
| Field | Meaning |
|---|---|
| session | session id |
| need | which research need this serves (for example "revenue_latest") |
| kind | "search" or "extract" |
| query | the search text (search only) |
| result_ids | ids from an earlier search in this session (extract only); never raw URLs |
| options | the Tavily options allowed for this need (topic, domains, depth), chosen from a fixed list |

## 2. Gate response to Planner
| Field | Meaning |
|---|---|
| status | sent, blocked or error |
| rule | the rule that fired, if blocked |
| ledger_seq | the ledger row number |
| result_ids | opaque ids for the results (the Planner never gets titles, snippets or URLs) |
| typed | after the Reader and Validator run: per need, found or not found, plus validated numbers with unit and period |

## 3. Gate to Reader: reading job
| Field | Meaning |
|---|---|
| job | job id |
| public_query | the query that was sent (already public) |
| documents | id, URL and text for each result being read |
| schema | the claim schema below |

## 4. Reader output: claim schema (strict)
| Field | Allowed values |
|---|---|
| claim_type | one of a fixed list: revenue, revenue_growth, ev_revenue_multiple, ebitda, employees, founded_year, headquarters_country |
| value | a number |
| unit | one of: usd, usd_millions, usd_billions, percent, multiple, count, year |
| period | a year or "ttm", or empty |
| quote | the sentence the number comes from, copied exactly |
| document_id | one of the ids in the job |

Anything else the Reader writes is thrown away. The Validator keeps a claim only if the quote is found verbatim in
that document's text, the value parses from the quote, and the unit and period are consistent with the quote.

## 5. Ledger row
| Field | Meaning |
|---|---|
| seq | increasing integer |
| time | timestamp |
| session | session id |
| component | planner, reader or baseline |
| destination | host |
| payload | commitment SHA-256(nonce \|\| payload bytes); the payload and nonce stay in the local ledger |
| bytes | length |
| status | sent, blocked or error |
| rule | rule id if blocked |
| prev_hash | previous row's hash |
| hash | hash of the previous hash plus this row's canonical form |

## 6. Bundle
| Part | Meaning |
|---|---|
| rows | all ledger rows for the session, payloads as commitments; sent rows may carry a reveal {payload, nonce} |
| head | last hash |
| code_hashes | hashes of the gate and checks source files |
| public_key | the install's Ed25519 public key |
| signature | signature over head plus code_hashes |

## 7. UI events (from the app to the page)
memo_loaded, parties_confirmed, ledger_row, blocked, reader_claims, answer, proof_result, run_done.

## 8. Results file (for the UI results screen)
shared/results/results.json: leaks out of 40 per setup (single_agent, compromised, two_minds, two_minds_gate),
false blocks out of 30, the commit hash, the command used, and whether it is example data.
