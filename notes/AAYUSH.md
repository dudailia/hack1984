# Aayush: Gate, Planner, run loop

Read notes/TEAM_BRIEF.md first. Your Claude Code prompt is in TEAM_BRIEF.md section 11. This file is the detail
behind it.

## Your mission in one line
Build the only door to the internet, and the mind that holds the secret. Everyone else plugs into you.

## You are the critical path
- **By 13:00:** the Gate makes one real Tavily search and writes a ledger row before sending. Post a screenshot of
  the row in the group chat.
- **By 17:00:** the Planner runs on Ollama and produces valid research requests from the memo.
- **By 21:00:** `app/run.py` runs the full loop end to end and streams UI events to Sharon's page.
If you slip, say so in the group chat immediately. Ilia checks in with you at 12:30.

## What you build

### 1. gate/ (one process, the only one with network)
- Loopback HTTP server, standard library (`http.server`, `urllib.request`, `json`, `sqlite3`).
- Endpoints (finalize names in shared/FORMATS.md): one for search, one for extract, one for Reader jobs.
- Exact host allowlist: `api.tavily.com`; `api.anthropic.com` only for Reader jobs. Anything else: refuse and
  ledger it as blocked.
- Order for every outbound request, never changed: build payload, call `checks.run_all(payload, session)`, write
  ledger row (status sent or blocked, rule), then send only if allowed, then update the row with the result
  (or write a result row: agree with Anand which).
- Result ids: keep a session map `result_id -> url, title, content` inside the Gate. The Planner gets ids only.
  Extract accepts only ids this session returned.
- Tavily details (see notes/RESEARCH.md): POST https://api.tavily.com/search with `Authorization: Bearer <key>`.
  Set `search_depth` explicitly to `basic` (do not use `auto_parameters`: it can switch to advanced and cost
  more). `topic: finance` for company figures, `max_results: 10`, `include_domains` with
  `include_domains_mode: prefer` for primary sources, `include_usage: true` to read credits. Extract: POST
  /extract with up to 20 URLs, `query` for reranking, check both `results` and `failed_results`.
- Use the team Tavily key from the event code HACK1984 (8,000 credits, valid Nov 6 to 9) on the demo laptop.

### 2. Ledger (SQLite, append only)
Row: seq, time, session, component (planner, reader, baseline), destination host, exact payload bytes, byte
length, status (sent, blocked, error), rule, prev_hash, hash = SHA-256(prev_hash + canonical JSON of the row).
Test: there is no function that sends without first writing a row. Anand builds the bundle and verifier on top
of your table, so agree the canonical form with him by 12:30.

### 3. Audit hook (invariant 1)
`sys.addaudithook` in every non-Gate process: on `socket.connect`, raise if the address is not 127.0.0.1 or ::1.
Test: the Planner process cannot open a connection to any outside host.

### 4. planner/
- Ollama on `http://localhost:11434/api/chat`, with `format` set to the JSON schema of a research request so the
  model can only return valid JSON. `stream: false`, temperature low.
- Model: try `qwen3:8b` first, `llama3.1:8b` as fallback. Pick the one that follows the schema on 10 tries.
- Inputs only: memo, question, and typed fields per research need (numbers, units, periods, found or not found).
  Never titles, snippets, URLs or page text. Test: feed a fake web string into the Gate and assert it never
  appears in any Planner input.
- Outputs: research request (need, kind search or extract, query, result_ids, options from a fixed list) or
  "done".
- System prompt: you research public facts for this memo; never put the buyer, price, codename or people in a
  query; ask only about the target's sector and public peers.

### 5. app/run.py
- Loop: Planner -> Gate -> Reader job via Gate -> Ilia's Validator -> typed fields -> Planner, until done or the
  session budget (calls and credits) runs out. Then Ilia's Composer.
- Emits UI events (names in shared/FORMATS.md) over Server-Sent Events on loopback for Sharon.
- One command for the demo: memo file, question, mode (doublethink, single, compromised).

## Who you depend on, who depends on you
| You need | From | Fallback until it lands |
|---|---|---|
| `checks.run_all` | Anand | stub that allows everything, loudly marked |
| Reader request builder, Validator, Composer | Ilia | stub returning a fixed claim |
| UI | Sharon | print events to the terminal |

| Needs you | What |
|---|---|
| Anand | ledger table and canonical row form |
| Ilia | Gate endpoint for Reader jobs, fake Tavily wiring for baseline |
| Sharon | SSE stream with the agreed event names |

## Tests you own
No send without a row; non-allowlisted host refused and ledgered; Planner never sees web text; non-Gate process
cannot reach outside; extract only on session ids; one live Tavily call shows credits used.

## Workshop
"Off the Telescreen: Local AI" at 16:00, Curry 346 (local models with Ollama). Go only if the Gate and Planner are
on track; it is directly about your part.
