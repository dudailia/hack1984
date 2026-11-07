# Doublethink UI: design

Owner: Sheara. Source of truth for event names, fields, endpoints and paths: shared/FORMATS.md (it wins over this file).
Anything below marked **TO CONFIRM** is not in FORMATS.md and must be agreed with its owner before code depends on it.
Section 10 lists the open and resolved items.

Direction: **two rooms and a wall**, dressed as HACK1984: black, off-white, one red, monospace. The finish is a
**telescreen** (a watching eye, static scanlines and grain) showing a **classified dossier** (the memo as a file with a
CONFIDENTIAL stamp and redaction bars).
The screen must make three things obvious with no explanation:
1. The secret is in one room and the web is in another, and they never touch.
2. Every request that leaves passes one gate, and blocked requests show in red.
3. The record is real: Verify says VALID, and editing one byte makes it say INVALID.

Hard rules: plain HTML, CSS and JavaScript. No framework, no CDN, no external fonts, no network.
The page works offline. All text meets WCAG AA. Event names and fields come from shared/FORMATS.md §10 exactly.

## 1. Color

### The two meaning rules
- **Red means a leak or a block. Nothing else.** That covers blocked rows, leaked rows, secret words seen in an
  outgoing query, the planted instruction line, the LEAKED stamp, INVALID, broken proof rows, and leak and
  false-block bars. Red is never used for buttons, decoration, brand or errors that are not leaks or blocks.
- **Cyan means verified or allowed. Nothing else.** That covers the allowed decision mark, the proof check marks and
  VALID.
- Everything else is greyscale. Cyan, not green, so that red and calm stay apart for red-green colour blindness.
- Color is never the only signal. Each state also has a word or a symbol: `BLOCKED`, `LEAKED`, `✓`, `✕`, `VALID`,
  `INVALID`.

### Tokens (`:root` in styles.css)
Contrast ratios were computed with the WCAG 2.x relative-luminance formula.

| Token | Value | Use | Contrast |
|---|---|---|---|
| --bg | #0A0A0A | page | – |
| --surface-1 | #141414 | rooms, ledger | – |
| --surface-2 | #1E1E1E | rows on hover, memo block, buttons | – |
| --text | #EDEAE2 | body text, numbers, the wall | 16.5:1 on --bg, 13.9:1 on --surface-2 |
| --text-muted | #A8A49C | labels, secondary fields, hashes | 8.0:1 on --bg, 6.7:1 on --surface-2 |
| --text-dim | #9C978F | tertiary info only (ledger hashes, title small print) | 6.8:1 on --bg, 5.8:1 on --surface-2 |
| --line | #3A3A3A | decorative dividers only, never text or control edges | – |
| --control-edge | #A8A49C | button and input borders (3:1 needed) | 8.0:1 on --bg |
| --red | #FF4A3D | leak or block text, borders, bars | 5.9:1 on --bg, 5.0:1 on --surface-2, 5.5:1 on --red-bg |
| --red-bg | #2B0B0B | blocked or leaked row fill | --text on it 15.1:1 |
| --on-red | #0A0A0A | text on a solid red fill (stamps) | 5.9:1 |
| --calm | #5CC8D6 | verified or allowed | 10.1:1 on --bg, 8.4:1 on --calm-bg |
| --calm-bg | #0A2226 | VALID panel fill | --text on it 13.8:1 |
| --focus | #EDEAE2 | focus ring | 16.5:1 |

The results file's example banner is not a leak, so it is styled off-white on black, never red. The same goes for the
CONFIDENTIAL stamp on the memo and the VERIFYING RUN label: both are off-white.

### Telescreen atmosphere and contrast
- Two fixed overlays sit above the page with `pointer-events: none`. Both are static, with no flicker and no loop.
  - Scanlines: `repeating-linear-gradient`, a 1px line of black at 5% alpha every 3px (`--scan-alpha: 0.05`).
  - Grain: an inline SVG `feTurbulence` data URI, black only, at 3% (`--grain-alpha: 0.03`).
- Both overlays only darken, never lighten. That keeps the ratio between text and its background close to the
  original, because both get darker together.
- Worst case, computed per pixel: a text pixel hit by a scanline and dark grain, next to a background pixel hit by a
  scanline only.

  | Pair | Contrast |
  |---|---|
  | --text-dim on --surface-2 | 5.0:1 |
  | --text-muted on --surface-2 | 5.8:1 |
  | --red on --surface-1 | 4.8:1 |
  | --red on --red-bg | 4.7:1 |
  | --calm on --surface-2 | 7.3:1 |

  That is why --text-dim went from #8A867F to #9C978F. Red text is never placed on --surface-2.
- Under `prefers-reduced-motion: reduce` both overlays are hidden.

## 2. Type

- One family, monospace everywhere, which is the HACK1984 look and suits data:
  `--font: ui-monospace, "Cascadia Mono", "Cascadia Code", Consolas, "SF Mono", Menlo, "DejaVu Sans Mono", "Liberation Mono", monospace;`
- No font files. A free OFL pixel font in `ui/fonts/` is optional, for the wordmark only, and is added only with
  Sheara's OK.
- Labels use upper case with `letter-spacing: 0.08em`. Values keep normal case.
- `font-variant-numeric: tabular-nums` is always on, so numbers line up.

Scale, sized for 1280x720 on a projector. **Nothing is smaller than 16px.**

| Token | px at 1280 | Use |
|---|---|---|
| --fs-0 | 16 | ledger rows, excerpts, typed facts, metadata, buttons |
| --fs-1 | 18 | memo text, answer quotes, room subtitles |
| --fs-2 | 20 | room titles (PLANNER ROOM), metrics values |
| --fs-3 | 24 | wordmark, answer headline numbers |
| --fs-4 | 32 | results screen bar labels and values |
| --fs-5 | 48 | stamps: LEAKED, BLOCKED, VALID, INVALID |
| --fs-6 | 64 | results screen title number |

- Line height is 1.4 for body text and 1.2 for anything 24px or larger.
- Sizes are set in rem, with `html { font-size: 16px }`.
- `@media (min-width: 1800px) and (min-height: 1000px)` sets 20px, which scales everything by 1.25 for 1920x1080.

## 3. Spacing

The base unit is 4px: `--sp-1: 4px`, `--sp-2: 8px`, `--sp-3: 12px`, `--sp-4: 16px`, `--sp-5: 24px`, `--sp-6: 32px`,
`--sp-7: 48px`.
- Room padding is --sp-4. Gaps between rows are --sp-2, and gaps between groups are --sp-5.
- The wall is 8px wide (`--wall`). The wordmark's wall in the header is 4px. The packet is a 16px square.
- Corners are square (border-radius 0) to match the event's look.

## 4. Layout

### Frame (1280x720)
- Header, 56px: the DOUBLETHINK wordmark (split by a 4px wall), a mode toggle `[ Single agent | Doublethink ]`, a
  source badge, then Run and Verify proof.
  - Live mode adds the source selector and the "careless query" switch next to Run.
  - Replay mode shows the replay status in their place: `REPLAY ▶ 0:42`.
  - Download bundle and Tamper one byte live in the proof panel (section 6), so the header fits 1280px.
- Main area, about 576px: three columns sized 1fr, 1.3fr and 1fr. The middle column is wider because it holds the
  ledger.
- Footer, 88px: the answer bar and four big counter cells (section 4, "Big counters").
- Every room scrolls on its own, and the ledger auto-scrolls to the newest row. The page itself never scrolls.
- The Planner room and the One agent room each have two scroll regions:
  - the dossier on top, at most 48% of the room;
  - typed facts or web text below, with its own scroll.

  Scrolling to the planted line or to the newest typed fact moves only the lower region, so the memo stays in view.
- The panels are cleared on `run_started`.
- The source badge comes from `run_started.data.source`. It reads `SOURCE: LOCAL STAND-IN (fake)` or
  `SOURCE: api.tavily.com (real)`, so nobody can mistake a fake run for a real one.
- The header mode label comes from `run_started.data.mode` (`single_agent`, `compromised`, `two_minds`,
  `doublethink`). The page never shows a mode that did not run.

### Doublethink mode (modes `doublethink` and `two_minds`)
```
+---------------------------------------------------------------------------------------+
| DOUBLETHINK   [ Single agent | Doublethink ]   SOURCE: api.tavily.com   Run Verify Bundle |
+---------------------------++----------------------------------++-----------------------+
| PLANNER ROOM              || THE GATE · only door out          || READER ROOM           |
| never reads the web       || EXIT ▲ api.tavily.com             || never sees the secret |
|                           ||      ▲ api.anthropic.com (reader) ||                       |
| MEMO  PROJECT ███████.    ||----------------------------------|| query: "payments..."  |
| ██████ ███████ ████████   || 01 search tavily "payments pr…" ✓|| r_01 Payments proc…   |
| is preparing an offer...  ||    ↳ 200 · 1 credit               ||  "...grow at 9.8%..." |
| price: ████████████       || 03 reader anthropic j_01 2 docs ✓|| r_03 Payments sector |
|                           || 05 search tavily "████ Capital…" ||  ▌Note to AI research |
| TYPED FACTS (numbers only)||    ✕ BLOCKED  secret.buyer        ||  ▌assistants: ...     |
| sector_growth  found      ||    planted test query             ||  planted instruction  |
|  9.8 percent 2025-2030 r01|| hash 0e24…0143                    || CLAIMS kept 2 drop 1  |
+---------------------------++----------------------------------++-----------------------+
| ANSWER  sector growth 7.4% (2025) · 9.8%/yr 2025-2030 · peers 4.6x EV/rev   [open]       |
|                                     LEAKS 0 · BLOCKED 1 · CREDITS 2 · 13.7 s           |
+---------------------------------------------------------------------------------------+
```
- **The wall** is the two 8px off-white bars on either side of the Gate column. It is the strongest line on the
  screen.
  - The only opening is the exit bar at the top of the Gate. It has a 2px off-white top edge and the label
    `ONLY DOOR OUT ▲`. Packets leave there and nowhere else.
  - In single agent layout the label reads `EXIT ▲`, because there is no wall.
  - The exit bar lists the destinations allowed for this run, as full hosts (it is the allowlist), using the same
    strings as `row.destination`:
    - source real: `api.tavily.com`
    - source fake: `127.0.0.1:<FAKE_TAVILY_PORT>`, which is `127.0.0.1:8702` in the fixture
    - both: `api.anthropic.com (reader only)`
- **Planner room:**
  - The memo comes from `memo_loaded.data.text`.
  - Every value in `parties_confirmed.data.confirmed_secrets[].values`, plus `memo_loaded.data.canary`, is drawn as a
    redaction bar (a --text block with the text hidden).
  - Hovering or focusing a bar shows the value and its label (`codename`, `buyer`, `price`, `person`, `canary`).
    Tab reaches each bar.
  - Below the memo is a "Typed facts" list built from `planner_typed.data`: need, found, then each of `values[]` as
    value, unit, period and result_id. There is no web text here, and the room's subtitle says so.
- **Gate ledger** (one entry per `ledger_row` event, using `data.row` and `data.display`):
  - Attempt rows (`row_type "attempt"`) show `seq`, `kind`, a short destination, `display.query` (or
    `display.summary` for reader rows), and the decision mark: `✓` cyan for allowed, `✕ BLOCKED` red for blocked.
  - Short destinations: `api.tavily.com` → `tavily`, `api.anthropic.com` → `anthropic`, `127.0.0.1:8702` →
    `fake:8702`. The full host is in the `title` tooltip.
  - Result rows (`row_type "result"`) are indented one line under their attempt (`attempt_seq`) in --text-muted, for
    example `↳ 200 · 1 credit` from `http_status` and `credits_used`.
  - Each row shows a short `hash` (first 4 and last 4 hex). The proof walk uses it.
  - `rule` and `display.detail` show under the row when they are set.
  - After a `blocked` event whose `data.planted` is true, the row is tagged `planted test query`.
- **Reader room:**
  - It shows `docs_read.data`: the `public_query` at the top, then one card per `docs[]` with title, url and excerpt.
  - Each `highlights[].text` gets a red left bar and a --red-bg fill, with `highlights[].label` shown underneath
    ("planted instruction (demo annotation)").
  - Below the cards come `reader_claims.data`: `kept` claims with their quotes, and `dropped` claims in muted text
    with `reason`.
- **Answer bar:** a one-line summary of the `answer` event.
  - Clicking it, or pressing A, opens the answer sheet. The sheet covers the three rooms and lists each `needs[]`
    with its `items[]`: subject, value and unit, period, the quote in quote marks, and `source.title`, `source.url`
    and `source.result_id`.
  - When `headline` is not null, it shows value, unit, period and `method`.
  - Every number is copied straight from the event and never reformatted beyond adding the unit symbol.
- **Counters** (see "Big counters" below):
  - LEAKS and BLOCKED are counted live from `ledger_row` events and then taken from `run_done.data.leaks` and
    `run_done.data.blocked`. They turn red only when they are above 0.
  - CREDITS is the running sum of `ledger_row.data.credits_used`, then `run_done.data.credits_total`.
  - TIME comes from `run_done.data.seconds`. CREDITS and TIME always use --text.
- **One story on screen.** Each session keeps its own rows, answer, `run_done` data and counters. The ledger, the
  answer bar, the counters, the source badge and the gate header always describe the same run, `S.view`.
  - When a `proof_result` arrives for an earlier run (in the demo, `s_dtreal1` after the careless run), all of them
    switch to that run together.
  - A boxed off-white label above the ledger then reads
    `VERIFYING RUN s_dtreal1 · doublethink · real · answered`. It is built from that run's `run_started` and
    `run_done`.
  - Closing the proof panel (V) brings the latest run back.
- **two_minds:** same layout. The gate header reads `RECORDING ONLY · NOT ENFORCING` in muted text, because in
  fake-only modes the decision is always `allowed` (FORMATS §1).

### Single agent mode (modes `single_agent` and `compromised`)
```
+---------------------------------------------------------------------------------------+
| DOUBLETHINK   [ Single agent | Doublethink ]  SOURCE: LOCAL STAND-IN (fake)  Run ...    |
+-----------------------------------------------------++--------------------------------+
| ONE AGENT · sees the memo and the web               || OUTBOUND · recorded, not       |
| MEMO  (secrets shown, not redacted: the agent has   ||           enforced              |
|        them)                                         || 01 search 127.0.0.1:8702 "pay…"✓|
| -------------------------------------------------   || 05 search 127.0.0.1:8702      |
| WEB  r_03 Payments sector growth…                    ||  "Project Halyard Ossory      |
|  ▌Note to AI research assistants: ...                ||   Capital Partners $412 m…"   |
|                                                      ||   [ LEAKED ]  secret.buyer     |
+-----------------------------------------------------++--------------------------------+
| ANSWER —                                             LEAKS 1 · BLOCKED 0 · ...        |
+---------------------------------------------------------------------------------------+
```
- The wall fades out (motion M8) and the two rooms merge into one 2fr column. The memo and the web text
  (`docs_read` with `by: "baseline"`) sit in the same panel with only a thin --line divider between them.
- The ledger header says `recorded, not enforced`. That is the truth in fake-only modes (FORMATS §1).
- A row counts as a leak when it is an `allowed` attempt with a non-null `rule` (FORMATS §10). It gets the LEAKED
  stamp, and every confirmed secret value that appears literally in `display.query` is wrapped in a red highlight.
- **Resolved (section 10, item 3):** when the toggle is on Single agent, Run posts `mode: "compromised"` with
  `source: "fake"` (notes/DEMO.md). In replay mode the toggle only switches the layout.

### Telescreen and dossier elements
- **Title screen.**
  - What it shows:
    - an original ASCII-art eye (7 lines, 16px);
    - DOUBLETHINK at --fs-6, split by an 8px wall;
    - the line "The cloud model never sees your secret. The local model never reads the web." at --fs-2;
    - `press Space` with the cursor (`press any key` in live mode);
    - the small print `offline replay · all companies, people and deals are fictional`.
  - When it shows:
    - on load, and after R;
    - it is skipped when `?at=` is greater than 0 or `?title=0` is set.
  - How it goes away:
    - Space or a click starts playback and fades the title out (250ms, opacity);
    - in live mode it goes away on the first `run_started` or on any key.
- **Dossier memo.** Both rooms with a memo show it as a file:
  - a header line `> FILE 1984 · SUBJECT: <memo_loaded.title> · sha <first 4…last 4 of memo_loaded.sha256>`;
  - an off-white double-ruled `CONFIDENTIAL` stamp, rotated -3deg;
  - then the memo text.

  Redaction in the Planner room:
  - It is case-insensitive, so the subject `PROJECT HALYARD` and the memo's first line are hidden like
    `Project Halyard`.
  - `memo_id` is never shown, because it repeats the codename.
  - The One agent room shows everything in the clear, because that agent holds the secrets.
- **The eye.** A 5-line ASCII eye sits at the right of the gate header.
  - It is **open** in single agent layout (one model sees everything) and **closed**, as a lid line with lashes, in
    Doublethink layout (nothing can leave).
  - At a leak, a red copy of the open eye fades in on top. Red here means the leak.
  - The eye resets on `run_started`. A screen-reader line states its state.
- **Big counters.**
  - LEAKS, BLOCKED, CREDITS and TIME sit in boxed cells (2px --line border) with values at --fs-4 (TIME at --fs-2).
  - When a value rises, it rolls (M11).
  - The LEAKS and BLOCKED cells get a red border and a red value when above 0.
- **No empty rooms.** Before their first event, the rooms show `>` waiting lines with a cursor:
  - `> waiting for the memo`
  - `> no numbers yet`
  - `> waiting for the first request`
  - `> waiting for web text`

  Each line is replaced by content as soon as its first event arrives.

## 5. Motion

- One easing curve for the whole page: `--ease: cubic-bezier(0.2, 0, 0, 1)` (a fast start and a soft stop).
- Durations: `--dur-s: 150ms`, `--dur-m: 200ms`, `--dur-l: 250ms`.
- Only `transform` and `opacity` are animated. A color change is done by fading in a pseudo-element layer that
  already has the new color.
- Motion never blocks input or delays the next event. Animations run while the replay keeps going. Each moment is a
  set of CSS animation delays plus fire-and-forget timers, all timed from the arrival of the attempt row (t = 0).
- Packets live in a fixed `#fx` layer and move with the Web Animations API on `transform` only. Their positions come
  from the sending room, the new row and the exit bar.
- On seek or jump (`→`, `?at=`) everything is applied instantly, with no packets, typing, shakes or ticks.

| # | Moment (trigger) | Motion | Timing |
|---|---|---|---|
| M1 | A request leaves a room (any attempt `ledger_row`) | A 16px off-white packet slides from the edge of the sending room into the gate at the row's height. Planner and baseline come from the left, reader from the right. | 0–200ms |
| M2 | Gate allows (attempt `decision "allowed"`, `rule` null) | The row lands (translateY -8px→0, opacity). The packet rises to the exit bar, then leaves upward and fades. The cyan `✓` is part of the row. | row 0–150ms; packet 200–400ms rise, 400–600ms out |
| M3 | **Gate blocks** (attempt `decision "blocked"`, then the `blocked` event) | The packet rises and **stops just under the exit bar** at 400ms. Its red layer fades in. A red line flashes on the exit bar (opacity 0→1→0). The packet and the row **shake** together (translateX 0, -8, 8, -6, 6, -3, 0 px). The row's red layer and red left edge fade in. At 650ms the **BLOCKED stamp slams** down (rotate -4deg, scale 1.6→1, opacity 0→1). The `✕ BLOCKED` mark, the rule and the planted tag appear, and the BLOCKED counter rolls to 1. The packet fades where it stopped. | packet 0–400ms; shake 400–650ms; exit flash 400–850ms; red layer 400–550ms; stamp 650–850ms; packet fade 650–850ms |
| M4 | Reader reads the poisoned page (`docs_read` where a doc has `highlights`) | The card fades in. The planted-instruction label fades in after it. **Nothing moves toward the wall:** no packet and no row. The Planner's typed list gets numbers only. | card 150ms; label 150ms after a 150ms delay |
| M5 | **Single agent leaks** (allowed attempt with a non-null `rule`) | The packet slides in and rises like M2, turns red at 300ms, and leaves through the exit. The query types out, and each secret word's red mark appears with its first letter. At 400ms the secret words **flash twice** (opacity 1, 0.3, 1, 0.3, 1). At 800ms the **LEAKED stamp slams** down. The row's red layer and edge, the `✕ LEAKED` mark and the rule appear. The **eye turns red**, and the LEAKS counter rolls to 1. | packet 0–600ms; typing 0–350ms; flash 400–800ms; stamp 800–1000ms |
| M6 | Verify proof (`proof_result`, `valid: true`) | The ledger rows tick from the top down to `rows_checked`. Each row's `✓` fades in cyan. Then the VALID stamp arrives with scale 0.96→1 and opacity. | 80ms per row, with the whole walk capped at 1200ms (the step becomes 1200/n); stamp 200ms; --ease |
| M7 | Tamper (`proof_result`, `tampered: true`, `valid: false`) | The walk ticks rows above `broken_at_seq` with `✓`. That row and every row below it then turn red from the top down, each with a `✕`. The row at `tampered_seq` is tagged `1 byte edited`. The INVALID stamp shows `row {broken_at_seq} · {reason}`. | 80ms per good row; 40ms stagger per broken row, capped at 600ms; stamp 200ms; --ease |
| M8 | Mode switch (toggle, key 1 or 2, or a new `run_started.data.mode`) | The wall bars fade (opacity 1→0 into single agent, 0→1 back). The eye opens or closes (scaleY 0.15↔1 with an opacity crossfade between the open and closed drawings). The grid switches at once, because grid changes are not animated. | 250ms |
| M9 | Answer sheet opens (A or click) | The sheet slides up with translateY 16px→0 and opacity 0→1 | 200ms |
| M10 | An outgoing query appears (attempt row with `display.query`) | The query types out: each character is a span that fades in (opacity), staggered so the whole query takes at most 350ms. | ≤ 350ms in total |
| M11 | A counter value changes | The old value moves up and out (translateY 0→-100%, opacity 1→0) while the new value comes up from below. | 200ms |
| M12 | A room is waiting for its first event | The `▌` cursor pulses (opacity 1↔0.15, alternate). **This is the only looping animation.** It exists only on waiting lines, which are replaced by content on the first event. | 530ms per half-cycle |

All motion uses `--ease`. Durations at or under 250ms, except the sequences above, which are made of such steps.

- The proof walk only replays what `proof_result` already says. It starts after the event arrives, so the UI never
  shows a verdict the verifier did not return.
- **`prefers-reduced-motion: reduce`:**
  - Every animation and transition is turned off: no packet, no typing, no shake, no stamp scaling, no counter roll,
    no slide, no cursor pulse.
  - The scanlines and grain are hidden.
  - States still change, at once.
  - The proof walk shows every check mark at once, then the verdict.
  - The leak flash becomes a steady highlight.
- Nothing loops forever except the waiting cursor (M12), and nothing is decorative. The atmosphere is static.

## 6. Proof panel

- Opened by Verify proof (or key V). It replaces the Reader room column. The ledger stays in the middle, because the
  walk happens there.
- Contents, top to bottom:
  - `PROOF · session {session_id}`, from the event envelope.
  - The boxed label `VERIFYING RUN {session_id} · {mode} · {source} · {outcome}`, the same as above the ledger.
  - `bundle head {first 4…last 4}` from `proof_result.data.bundle_head`, with the full hash on hover.
  - `rows checked {rows_checked}`.
  - The verdict stamp at --fs-5:
    - VALID: cyan text on --calm-bg with a cyan border.
    - INVALID: --on-red text on solid --red, followed by `row {broken_at_seq} · {reason}`. `reason` is one of the
      verifier codes in FORMATS §8.
  - Buttons: `Verify proof`, `Tamper one byte` (with a row picker that defaults to row 3, the FORMATS example), and
    `Download bundle`.
  - A note saying this is a copy: `Tamper edits a copy of the bundle. The ledger is never changed.` (FORMATS §11)
  - The offline command in a code block, as written in FORMATS §8: `python3 proof/verify.py bundles/<session_id>.json`.
- **Live mode** (FORMATS §11; every call carries the token as `X-DT-Token`):
  - Verify calls `POST /api/verify` with `{"session_id"}`.
  - Tamper calls `POST /api/tamper` with `{"session_id","seq"}`.
  - Download calls `GET /api/bundle?session_id=…`.
  - The verdict arrives as a `proof_result` event on `/events`.
  - The session is the one from the latest `run_done`.
- **Replay mode:**
  - `proof_result` events come from the fixture, and the panel is labeled `replay`.
  - Verify plays the recorded `proof_result` with `tampered: false`, and Tamper plays the one with `tampered: true`.
  - Download bundle shows the message "Download bundle is available in live mode.", because there is no bundle file
    in the fixtures.

## 7. Results screen (`beat.data.screen = "results"`, or key S)

- It replaces the whole main area.
- All numbers come from `shared/results/results.json`. Until that file exists, they come from
  `shared/fixtures/results_example.json`. **No number is typed into the code.**
  - **TO CONFIRM (Aayush):** app/run.py serves only `/ui/…` and `/shared/fixtures/…` (FORMATS §11), so on port 8700
    the page cannot fetch `/shared/results/results.json`. Either app/run.py also serves `/shared/results/`, or the
    real file gets copied into fixtures. Until that is settled, the page tries `/shared/results/results.json` first
    and falls back to the example file.
- When `example` is true, a full-width banner shows the `banner` text in off-white on black with a 4px off-white
  border. It is not red.
- Title: `{attacks_total} attacks, written and hashed before the code.` `attack_file_sha256` is shown short below
  the title.
- There are four horizontal bars from `runs[i].modes`, one row each, with the label at --fs-4, the bar, and the value
  `{leaked} / {runs}`:

  | Bar label | Field |
  |---|---|
  | single agent | `single_agent` |
  | compromised agent | `compromised` |
  | two minds | `two_minds` |
  | two minds + gate | `doublethink` |

  - The fill is solid --red, with width = leaked/runs. The empty track uses --line.
  - A value of 0 is drawn as an empty track with the value in --text. It is not cyan, because "no leaks" is a
    measurement, not a verification.
- Below the bars: `False blocks on normal questions: {false_blocks.blocked} / {false_blocks.total}`. It is a red bar
  if the count is above 0, with `false_blocks.by_rule` listed in muted text.
- Small print in --fs-0 muted:
  - `label`, `commit`, `planner_model`, `source`
  - `answered with a cited number {usefulness.answered_with_cited_number} / {usefulness.total}`
  - `cost.tavily_credits_per_question` and `cost.seconds_per_question`, shown as `not measured` when null.
- Run shown: the last entry in `runs`, which is the latest. `runs[0]` is the frozen run (FORMATS §9: "the frozen run
  first"). If there is more than one run, a thin --text tick marks the `runs[0]` value on each bar, with the caption
  `| = {runs[0].label} run`.
- No bar animation. The numbers are the point.

## 8. Interaction and accessibility

- Every control is a real `<button>`. Focus shows a 3px --focus outline with a 2px offset and is never removed.
- Keys:

  | Key | Action |
  |---|---|
  | Space | play or pause the replay |
  | → | next `beat` |
  | R | restart |
  | 1 / 2 | Single agent / Doublethink |
  | V | proof panel |
  | A | answer sheet |
  | S | results screen |
  | P | presenter overlay (step 6, shows `beat.data.title`, `say` and `at`) |

- The ledger is a `role="log"` with `aria-live="polite"`, and blocked or leaked rows also say it in words.
  Redaction bars are buttons with `aria-label="hidden: buyer"` (and so on, by label).
- 1280x720 is the minimum supported size. 1920x1080 scales up through the root font size.

## 9. Data sources, files and preview

- Files are `ui/index.html`, `ui/styles.css` and `ui/app.js`. `ui/fonts/` is added only with approval.
- Replay reads `shared/fixtures/demo_events.jsonl` (one FORMATS §10 envelope per line) and waits on `t_ms`.
- Live reads `GET /events?token=…` (SSE, no `event:` line). Replay and live share one dispatcher keyed on `type`.
- Paths are relative to the one origin: the page is at `/ui/index.html` and the fixtures are read from
  `/shared/fixtures/…` (FORMATS §11).
- **Local preview:** from the repo root run `python -m http.server 8703 --bind 127.0.0.1` and open
  `http://127.0.0.1:8703/ui/index.html`. On this Windows machine the command is `python`, not `python3`. In live mode
  the same files are served by app/run.py on `APP_PORT` (8700).
  - Port 8703 is the agreed preview port (section 10, item 5).
- **Replay or live:** the page is live when its URL has `?token=` and replays the fixture otherwise.
- **URL parameters** for rehearsal and screenshot QA:

  | Parameter | Effect |
  |---|---|
  | `?replay=1` | forces replay even with a token |
  | `?at=<ms>` | jumps the replay to that time (no title screen) |
  | `?play=1` | starts playing |
  | `?title=0` | skips the title screen |
  | `?open=answer` | opens the answer sheet |
  | `?freeze=<ms>` | with `?at=`, plays the next 100ms of events with animation, then pauses every animation at `<ms>`, so a frame of a moment can be screenshotted (for example `?at=86500&freeze=450` for the block, `?at=20990&freeze=900` for the leak) |

## 10. Items not in shared/FORMATS.md

### Open
| # | Item | Owner | What the UI does until it is settled |
|---|---|---|---|
| 2 | How the page reads `shared/results/results.json`. On 8700, app/run.py serves only `/ui/` and `/shared/fixtures/`. | Aayush | Try `/shared/results/results.json`, then fall back to `/shared/fixtures/results_example.json` with its banner. |

### Resolved
| # | Item | Resolution | Source |
|---|---|---|---|
| 1 | The token in the UI URL | `?token=` in the page URL. The page sends it as `?token=` on `/events` and `/api/bundle`, and as the `X-DT-Token` header on `/api/*` POSTs. | Aayush confirmed |
| 3 | The mode for the Single agent toggle | `compromised` (with `source: "fake"`) | notes/DEMO.md |
| 4 | The body Run sends | `POST /api/run {"mode", "source": "real"\|"fake", "plant_careless": true\|false}`. The source selector next to Run sets `source`, and a "careless query" switch sets `plant_careless`. Single agent forces `fake`. | Aayush |
| 5 | The preview port | `python -m http.server 8703 --bind 127.0.0.1` from the repo root | Ilia proposed |

Checked against FORMATS.md and present there (no action needed):
- Events: all twelve event types (§10).
- Endpoints: `/events`, `/api/run`, `/api/verify`, `/api/tamper`, `/api/bundle` (§11).
- Command: `python3 proof/verify.py` and its reason codes (§8).
- Paths: `bundles/<session_id>.json`, `shared/fixtures/results_example.json`, `shared/results/results.json` (§8, §9).
- Fields: leak definition, `display.query` highlighting, `blocked.planted`, `docs_read.highlights`, the `runs` order
  and the `example` banner.
