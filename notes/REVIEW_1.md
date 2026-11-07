# Review 1: reader/, baseline/, fake_tavily/

Hostile review of Ilia's folders against CLAUDE.md, shared/FORMATS.md and notes/THREAT_MODEL.md. Scope: reader/,
baseline/, fake_tavily/ only. checks/ was not opened. Base commit 9708a95, branch ilia-review.

## Summary
- 14 findings with a failing test each, all fixed in the same commit: 1 critical, 4 high, 5 medium, 4 low.
- The critical and high findings are all Validator bypasses: a claim was kept whose number the page does not
  state. The worst: a quote cut inside "$412,000,000" kept the value 412 (R1-01).
- Two network findings in baseline/: a cloud model name in OLLAMA_MODEL sends the memo to ollama.com outside the
  Gate (R1-09), and no loopback-only audit hook was installed (R1-10).
- No path found in reader/ that puts memo text, the question, a need id, the session id or a secret into the
  Reader body. Two defence-in-depth gaps were closed (R1-11, R1-12).
- No difference in fake_tavily/ found that would flatter the leak numbers. One difference would flatter usefulness
  if it were measured on the fake (I-1).
- Tests: 173 before, 228 after, all green (`python3 -m unittest discover`). 43 of the 55 new tests fail on the
  base commit. The other 12 pin legitimate input that must stay accepted.

## Findings

Line numbers are in the base commit 9708a95. Tests are in `<folder>/tests/test_review1.py`, one class per finding.

| ID | Severity | Where (base commit) | Finding | Failing test |
|---|---|---|---|---|
| R1-01 | Critical | reader/validator.py:21-26, reader/numbers.py:6 | Numbers were read from the quote alone, so a quote cut inside a number kept a number the page never states: `for $412` out of "$412,000,000" kept usd 412; `4.2% in 2025` out of "14.2%" kept 4.2; `employs 12` out of "12,500" kept 12. A sign or scale word just outside the quote was also ignored. | `R1QuoteTruncation` (6 tests) |
| R1-02 | High | reader/numbers.py:6 | Only ASCII `-` counted as a sign. "3.0%" preceded by U+2212 MINUS SIGN or U+2013, "-$3.2 million" and "(3.2%)" were kept as positive values. | `R1Sign` |
| R1-03 | High | reader/numbers.py:6, reader/validator.py:25 | One end of a range was kept as the value: "5-7%" kept 7%, "3.5" U+2013 "6.0x" kept 3.5 or 6.0, "3.5x to 6.0x" and "between 5% and 7%" likewise. | `R1Ranges` |
| R1-04 | High | reader/numbers.py:17-19, 6 | NFKC turned non-digits into digits and `\d` matched non-Latin digits: "1" U+00BD (one half) "%" kept 2% (and 11%), "4.2" U+00B9 (superscript footnote) "x" kept 4.21, "4" U+066B (Arabic decimal separator) "2x" kept 2, U+2463 (circled four) "x" kept 4, "1/2%" kept 2%. Any unlisted separator (U+2027 or U+02D9 between "4" and "2x") split the number, a zero-width space (U+200B) between the "1" and "4.2%" of "14.2%" kept 4.2, and bidi controls could show one number while another was parsed. | `R1UnicodeDigits` |
| R1-05 | High | reader/numbers.py:6, 48-50 | Digit grouping the regex did not know yielded a partial number: "4 200" (space, NBSP, thin space) kept 200 or 4, "1'234" kept 234, "1,2345" kept 1234, "12,50" kept 12. A count could be fractional ("1.234 people"). | `R1Separators` |
| R1-06 | Medium | reader/numbers.py:7, 47 | Plain usd only rejected million/billion/thousand: "$4.2 trillion", "$4.2tn", "$4.2 bln", "$412MM", "$412K", "$4.2 crore" were all kept as plain dollars. | `R1ScaleWords` |
| R1-07 | Medium | reader/composer.py:94-96 | Duplicates were found by subject only, so one quoted number claimed under several subjects ("Corvane Pay", "Corvane", "Corvane Pay Inc.") counted as several companies: "median of 4 companies" from 2 real ones, median 4.2 instead of 3.85. Overlapping quotes and syndicated copies did the same. | `R1ComposerDuplicates` |
| R1-08 | Medium | reader/composer.py:42, 97 | The model-written subject went into the answer text as is, so a subject like "peer median 9.9x per analysts" put a number written by a model into the answer (invariant 8). | `R1SubjectNumbers` |
| R1-09 | Medium | baseline/config.py:53-54, baseline/ollama.py:57-59 | Any OLLAMA_MODEL was accepted. Ollama "cloud" models (`gpt-oss:120b-cloud`, `glm-4.6:cloud`) run on ollama.com, so the single agent would send the memo off the machine through the local Ollama, outside the Gate and the ledger (invariants 1 and 5). Registry paths were also accepted. | `R1OllamaCloud` |
| R1-10 | Medium | baseline/agent.py:162, fake_tavily/server.py:195 | No loopback-only audit hook (TODO only). DNS, non-loopback connect, bind to 0.0.0.0 and subprocess all worked inside `main()` (invariant 1). | `R1LoopbackGuard` (baseline and fake_tavily) |
| R1-11 | Low | reader/request.py:49-50 | `claim_types` went into the body in the Planner's order and with repeats, which is a covert channel from the Planner (which holds the memo) to api.anthropic.com (invariant 3). | `R1ClaimTypesChannel` |
| R1-12 | Low | reader/request.py:41-44, 53 | Document ids and the job id were not format checked, so a session id or need id placed there by a Gate bug would reach the body (invariant 3). | `R1JobIds` |
| R1-13 | Low | reader/parse.py:27-30 | Deeply nested model output (about 10,000 levels, reachable within max_tokens) raised RecursionError from `parse_response`, which is documented never to raise. | `R1ParseNeverRaises` |
| R1-14 | Low | reader/numbers.py:6 | A number of any length was accepted, so a page could push a long digit string (text encoded as digits) into the Planner's typed values (invariant 2, bandwidth). | `R1HugeNumbers` |

## Fixes
- reader/numbers.py: new scanner. A number is a maximal run of ASCII digits joined by any single non-space,
  non-letter, non-marker character, or by a space before a group of three. It counts only if it parses strictly
  (123, 1,234, optional .5) and has at most 15 digits; anything else is ambiguous and yields no number. Signs
  cover ASCII and Unicode minus and dashes, also before the currency sign. Accounting parentheses are ambiguous.
  Ranges (dash, "to" with matching units, "between ... and") are flagged. `normalize` maps digit look-alikes and
  bidi controls to U+FFFD, removes other invisible format characters, and maps characters that NFKC would turn
  into whitespace to U+FFFD, all before NFKC. Plain usd, count and year reject any scale suffix; count and year
  reject decimals.
- reader/validator.py: numbers are scanned in the document. A number counts only if the whole number, sign
  included, lies inside an occurrence of the quote and is not a range end. The unit marker must be inside the
  quote, and the document around it must agree. The period year must be a whole year inside the quote span.
  `validate` now calls `check_job`.
- reader/composer.py: a claim repeats an earlier one if it matches on subject, on (document, number), or on (same
  quoted sentence, number). A subject carrying a number that is not in the quote is shown as `[subject withheld]`.
- reader/request.py: `check_job` (public) requires document ids `r_NN` and job id `j_NN`. Claim types are written
  once each, in the fixed FORMATS order. reader/parse.py: RecursionError drops the response.
- baseline/config.py, baseline/ollama.py: `local_model()` accepts `name[:tag]` only, with no registry path and no
  tag ending in "cloud".
- baseline/netguard.py (new, interim): audit hook that denies non-loopback DNS, connect, bind, sendto and sendmsg,
  and denies starting programs. Installed first thing in `baseline.agent.main` and `fake_tavily.server.main`.
- Source hygiene: non-ASCII characters in new string literals are written as `\u` escapes. Three existing tests
  held literal invisible characters (one U+202E bidi override, fake_tavily/tests/test_inject.py:30); they are now
  escapes with the same values.

## Notes without a code change

| ID | Area | Note |
|---|---|---|
| I-1 | fake_tavily/fixtures | Every fixture states its number in a clean sentence in exactly the forms the Validator accepts. Usefulness measured on the fake would flatter us. FORMATS §9 puts `usefulness` inside runs with `"source":"fake"`. Proposal for the group: measure usefulness on source real only. |
| I-2 | fake_tavily/server.py:104-120 | Fake extract ignores `query` and `chunks_per_source` and returns the whole page. Real Tavily returns the top chunks, which might leave out the planted sentence. Kept on purpose: the fake is harsher, so it can only understate our defence, never flatter it. |
| I-3 | fake_tavily/pages.py:65-66 | The poisoned page is in every search result and keeps its slot. Harsher than real search, same reasoning as I-2. |
| I-4 | baseline/compromised.py:41-48, 60 | Compromised mode fires only on the default DEMO.md instruction. When redteam is filled in, it must pass each payload as the trigger. Otherwise compromised mode leaks 0 of 40 and the "before" numbers are wrong. |
| I-5 | baseline/config.py | A name cannot prove a model is local: a cloud model copied to a local name with `ollama cp` passes. Stronger check: ask Ollama's `/api/show` whether the model is remote. Aayush: planner/ needs the same cloud-name check as R1-09. |
| I-6 | baseline/netguard.py | Interim until a shared guard exists (Gate side, Aayush). Not covered: ctypes calling libc directly. |
| I-7 | reader/numbers.py | Trade-offs in the safe direction: "in 2025 450 firms" now yields no number (it reads like "2025450"), and "(4.2x)" is dropped as a possible accounting negative. |
| I-8 | reader/composer.py | Two different companies in one document with the same multiple and period now count once. This can understate the count; it can no longer inflate it. |
| I-9 | reader/validator.py | A malformed job now raises ValueError in `validate`. The Gate should treat that as an error and send nothing to the Planner (fail closed). |
| I-10 | Gate, invariant 3 | reader/ cannot check that `public_query` is the query that was actually sent. The Gate must pass the exact sent query and nothing else. |

## To tell the group chat
- Reader Validator hardened (R1-01 to R1-06). No FORMATS change: drop reasons and claim shape are unchanged.
- Aayush: planner/ should refuse Ollama cloud model names (R1-09, I-5); a shared loopback guard should replace
  baseline/netguard.py (I-6); the Gate should fail closed if `reader.validate` raises (I-9).
- Proposal: usefulness numbers only from source real (I-1).
