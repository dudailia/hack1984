# Expo runbook (real estate scenario)

For whoever is at the table. The scenario is in notes/DEMO.md. A fictional analyst at Corrib Vale Real Estate
Partners holds a confidential memo on acquiring Saltmarsh Point Logistics Park (codename Project Cindergate), with
a $42.5 million financing proposal. Everything here matches `app/run.py`, `ui/app.js` and `gate/` on main, except
the scenario switch, which is a [placeholder] until the builder tab's change lands.

Anything in [brackets] is not measured or not decided yet; fill it in at setup or leave it unsaid. Never say a
number that is not in `shared/results/results.json` or sourced in notes/BUSINESS.md. Every memo, firm, person,
property and deal on screen is fictional, and we say so if asked.

## 1. Start from cold (demo laptop)

Do this before the first visitor, on good Wi-Fi.

**1.1 Terminal and Python**

```bash
cd [path to the repo on the demo laptop]
git status                      # clean, on the commit we are demoing: [commit]
source .venv/bin/activate       # has `cryptography`
python3 --version               # 3.13 or 3.14 (what shared/guard.py is written for)
unset APP_PORT GATE_PORT FAKE_TAVILY_PORT OLLAMA_PORT OLLAMA_MODEL FAKE_TAVILY_STATE PYTHONPATH
```

The `unset` matters: `app.run` reads ports from the shell before `.env`, while the Gate reads only `.env`. A stray
`GATE_PORT` in the shell makes the app talk to a port the Gate is not on.

**1.2 Ollama with qwen3:8b**

```bash
ollama list | grep qwen3:8b     # if missing: ollama pull qwen3:8b  (needs Wi-Fi, do it the night before)
ollama ps                       # if Ollama is not running, open the Ollama app or run: ollama serve
PLANNER_LIVE=1 python3 -m unittest planner.tests.test_live -v
```

The live Planner test talks only to the local Ollama. Run it once at setup: it loads the model into memory, so the
first real run is not the slow one.

**1.3 The .env file**

`.env` sits in the repo folder and is never committed. It must contain these keys. Check names only; never print,
show or read out a value:

| Key | Who reads it | What breaks without it |
|---|---|---|
| `TAVILY_API_KEY` | Gate only | Doublethink with source real (search and extract on real Tavily) |
| `ANTHROPIC_API_KEY` | Gate only | Every Doublethink run, fake or real: the Reader is Claude, called by the Gate |
| `APP_PORT` (8700) | app | the app refuses to start (loopback guard) |
| `GATE_PORT` (8701) | Gate, app | the Gate refuses to start |
| `FAKE_TAVILY_PORT` (8702) | Gate, Tavily stand-in | the Gate refuses to start |
| `OLLAMA_PORT` (11434) | app, Planner | the app refuses to start: `guard: .env is missing OLLAMA_PORT` |
| `OLLAMA_MODEL` (`qwen3:8b`) | Planner, single agent | the Planner refuses to run; the single agent falls back to `qwen3:4b` |

Check without showing values:

```bash
grep -oE '^[A-Z_]+=' .env                                   # key names only
grep -cE '^(TAVILY_API_KEY|ANTHROPIC_API_KEY)=.+' .env      # must print 2
```

Do not open `.env` in an editor while a visitor can see the screen.

**1.4 Start the app on the real estate scenario**

```bash
python3 -m app.run [--scenario real_estate]
```

[Scenario switch: the flag name and value are placeholders until the builder tab's change lands. Without it,
`python3 -m app.run` runs the corporate deal memo (Project Halyard).]

This starts the Gate and the local Tavily stand-in as child processes, waits for both health checks, then prints
one line: the UI address with this launch's token, `http://127.0.0.1:8700/ui/index.html?token=...`. Ctrl-C stops
all three. Before the URL, check the Gate's startup line in the same terminal:

- `gate listening on 127.0.0.1:8701 checks=checks ...` is what we want.
- `*** CHECKS STUB ... (ALLOWS EVERYTHING) ***` or `checks=stub` means the Gate is running without its checks.
  Do not demo live. Stop (Ctrl-C) and go to section 3.
- `app: STUB LOOP` means runs replay the fixture file instead of running. Do not present that as live.

Open the printed address in the browser. Check the memo panel shows PROJECT CINDERGATE, not PROJECT HALYARD; if it
shows Halyard, the scenario switch did not take. Keep this tab for the whole session: the token changes on every
launch. Set the browser zoom so the whole page fits; then move the terminal off screen.

**1.5 Results file**

```bash
ls shared/results/results.json
```

The results screen falls back to example data if `shared/results/results.json` is missing: the page then loads
`shared/fixtures/results_example.json`, which is not a measurement. Check the label before showing anyone. Open the
results screen yourself (key S) with no visitor watching:

- Real results: no banner, and the last line reads `from /shared/results/results.json`.
- Example data: a banner `EXAMPLE DATA - not measured` at the top, and the last line reads
  `from /shared/fixtures/results_example.json`. Do not show this screen to anyone. Say the numbers are not in yet.

Check which scenario the results are for. Real estate results: [not measured yet; red-team command with the
scenario switch to be added when it lands]. Until then the screen shows the first evaluation, on the corporate
deal memo. Say so when you show it: "These are from our first evaluation, on a corporate deal memo."

Check again after every restart of `app.run`, since the page loads the file when it opens.

**1.6 One rehearsal run**

Do the button sequence below once before visitors arrive. Time a live run: [seconds per Doublethink run on fake]
and [seconds per Doublethink run on real]. Real runs spend Tavily credits: [credits per run].

## 2. Buttons, in order

Top bar: **Single agent** (key 1), **Doublethink** (key 2), the source menu (fake or real) and the **careless
query** box (both Doublethink only), **Run**, **Verify proof**.

| # | Do | What visitors should see |
|---|---|---|
| 1 | Press any key to clear the title screen. | The Project Cindergate memo with the confirmed secrets highlighted: buyer, property, lender, $42.5 million, contacts. |
| 2 | **Single agent**, then **Run**. It always runs compromised on source fake. | The ledger fills. Its next search after the poisoned page carries Project Cindergate, Corrib Vale and $42.5 million. [Exact query as the scenario fixture builds it.] |
| 3 | Wait for the run to finish. **Doublethink**, source **fake**, careless unticked, **Run**. | The same poisoned page shows up in the Reader's documents with the planted line highlighted. The Planner side shows only typed fields. |
| 4 | When the answer bar lights up, click it (key A). Esc closes it. | Each number with its quoted sentence and source link. On source fake those sources are the stand-in's fictional pages; say so. |
| 5 | Tick **careless query**, keep source fake, **Run**. Untick it afterwards. | A planted careless Planner query naming the buyer; the row turns red with the rule that blocked it. [Planted query text as the scenario switch sets it.] |
| 6 | **Verify proof** (key V opens the proof panel). | VALID with the signer key. |
| 7 | In the proof panel, set the row number to a row you can see in the ledger, then **Tamper one byte**. | INVALID at that row. The original bundle is untouched; only a copy was changed. |
| 8 | Optional: key S for the results screen, only after the label check in 1.5. If the banner says `EXAMPLE DATA`, close it at once (Esc). | Leaks per setup on the 40 pre-registered attacks, false blocks on 30 benign questions. Say which scenario they are for (1.5). |
| 9 | Optional, on good Wi-Fi: **Doublethink**, source **real**, **Run**. | Real Tavily results on industrial and logistics real estate, with real source links. The memo is still fictional. |

Verify, Tamper and Download bundle act on the last finished run. Run is refused while a run is still going; wait
for it to finish.

## 3. Switch to replay

Replay plays `shared/fixtures/demo_events.jsonl`: the demo's events, scripted, not a live run. When we use it we
say "this is a replay" if anyone asks whether it is live. The replay file is the corporate deal memo (Project
Halyard) until a real estate replay exists: [real estate replay file and URL, if the builder tab adds one]. If you
fall back to it, say "this replay uses our first scenario, a corporate deal memo".

**When:** Wi-Fi drops, Claude or Tavily errors, Ollama hangs, a run fails ("Run failed" toast) or takes far longer
than the rehearsal. One retry at most, then replay.

| Problem | What still works live | Do |
|---|---|---|
| Wi-Fi down, or Claude errors | Single agent (Ollama, Gate and stand-in are all local) | Show the single agent live, then replay for Doublethink. Doublethink needs Claude even on source fake. |
| Real Tavily errors, Claude fine | Everything on source fake | Use source fake. |
| Ollama slow or down | Nothing live | Replay. |
| The app will not start | Nothing live | Replay from the preview server (below). |

**Replay while the app is running:** open `http://127.0.0.1:8700/ui/index.html?replay=1` in a new tab.

**Replay without the app:** `python3 ui/preview.py`, then open `http://127.0.0.1:8703/ui/index.html`. It needs no
`.env` and no keys.

Replay keys: Space plays or pauses, Right arrow jumps to the next beat, R restarts, V proof panel, A answer, S
results, T switches the theme. Run restarts and plays the replay; Verify and Tamper show the recorded results.

**Last resort:** the backup video, on the laptop at [path] and on the USB stick. The submitted demo video (3:00
to 5:00, notes/VIDEO.md) is on YouTube at [link], if Wi-Fi works.

## 4. If the Gate refuses to start

`app.run` exits with `app: gate exited with code N` or `app: gate not healthy on 127.0.0.1:8701/v1/health`. The
Gate's own error is printed just above that line. Read it, then:

| Error | Fix |
|---|---|
| `.env is missing GATE_PORT` or `FAKE_TAVILY_PORT`, or no `.env` | Add the key (section 1.3). |
| Address already in use | An old run is still alive. `lsof -nP -iTCP:8700-8702 -sTCP:LISTEN`, then quit those Python processes (`kill <pid>`). |
| `not healthy` on a port that does not match `.env` | A shell variable overrides it. Run the `unset` line from 1.1 and start again. |
| `a 'checks' module outside this repo was found` | Start from the repo folder with `PYTHONPATH` unset. |
| Any other import error from the checks | Do not debug it at the table. Message Aayush (Gate) and Anant (checks). |
| `app: loopback guard not installed, refusing to start` | The app, not the Gate: a port key is missing from `.env`, usually `OLLAMA_PORT`. |
| The scenario switch is refused | [Error text when the builder tab's change lands.] Start without it only if you will present the corporate memo instead, and say so. |

Never at the table: edit `gate/` or `checks/`, delete `ledger/` (it is the record), point the single agent at real
Tavily, or start the Gate with a stub. Two minutes on a fix at most, then replay (section 3) and fix it between
visitors.

## 5. Reset between visitors

1. Let the current run finish.
2. Esc (closes the answer sheet and the results screen). Close the proof panel (key V) if it is open.
3. Key 2 (Doublethink), source **fake**, **careless query** unticked.
4. Reload the tab (same address, same token). The page may show the last run again; the next Run replaces it.
5. Only if someone planted their own text on the stand-in's poisoned page through the API (the page has no panel
   for it): `python3 -m fake_tavily.inject --reset`.

Do not restart `app.run` between visitors unless something broke; a restart prints a new address and token, and
must be started with the scenario switch again (1.4). Leave `ledger/` and `bundles/` alone.

## 6. Table scripts

Lines follow notes/PITCH_SCRIPT.md, adapted to the real estate memo. Numbers in [brackets] come from
`shared/results/results.json` on the day, or are left out.

### 30 seconds

Do not start a run; a live run takes longer than 30 seconds. Talk over a finished run already on screen, or the
replay.

| Do | Say |
|---|---|
| Point at the memo | "An analyst at a real estate investment firm has a confidential acquisition memo, and an AI agent that searches the web." |
| Point at the single agent's leaked row | "Most agents are one model that sees the memo and the web. It reads a poisoned page, and its next search carries the codename, the buyer and the $42.5 million financing." |
| Point at the Doublethink run | "Doublethink splits it in two. The one that knows the secret runs locally and never reads the web. The one that reads the web never sees the secret. Same page: nothing leaves." |
| Point at the answer | "And it still answers, every number with the sentence it came from and its source." |

### 90 seconds

| Do | Say |
|---|---|
| Memo on screen | "An analyst at a real estate investment firm has a confidential memo: the property, the buyer, a $42.5 million financing proposal, a codename. And an AI agent that searches the web. Every request goes to an allowed host. Nobody checks what is inside." |
| **Single agent**, **Run** (or a finished one) | "This is how most agents are built: one model sees the memo and the web together. It reads a page with one hidden line telling AI assistants to search with the codename, the buyer and the financing amount. It obeys. Look at its next search: Project Cindergate, Corrib Vale, 42.5 million." |
| **Doublethink**, source fake, **Run** | "Now Doublethink, same poisoned page. Two minds. The one that knows the secret runs locally and never reads the web. The one that reads the web runs in the cloud and never sees the secret. It reads the hidden line and has nothing to leak, and no tools to leak it with." |
| Answer bar | "And it still answers. Every number shows the sentence it came from and its source, and any arithmetic is done in code." |
| Point at a red row from a careless run | "If the local model slips by itself and writes the buyer into a query, every outbound request still goes through one gate, the only process allowed on the network. Blocked, and logged before anything was sent." |
| **Verify proof**, then **Tamper one byte** | "Every request, blocked ones too, is in a hash-chained log, and the session exports as a signed bundle anyone can check offline. Valid. Change one byte. Invalid." |
| Close | "Not 100%. On this scenario, Doublethink leaked in [x] of 40 pre-registered attacks. In our first evaluation, on a corporate deal memo, it leaked in 0 of 40. The cloud model never sees your secret. The local model never reads the web." |

If the real estate results are not in yet, drop the "On this scenario" sentence and keep the first evaluation.
