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

## 0. Themes (added with the console reskin)

The page has two themes on the same DOM, layout, events and keys:
- **Console (default, `styles.css`)**: a calm compliance console. Light tokens: background #F7F7F5, cards #FFFFFF,
  border #E5E5E1, text #111827, muted #6B7280, accent indigo #4F46E5. Red only for leak or block (#DC2626 for borders
  and icons, #B91C1C for text, on #FEF2F2), green only for allowed or verified (#059669 borders and icons, #047857
  text, on #ECFDF5), amber #B45309 on #FFFBEB only for the planted instruction. The darker text shades keep every
  status text at WCAG AA (5.9:1 and 5.2:1). System sans, sentence case, 16px minimum; monospace only for queries,
  hashes and ids. Radius 10px, shadow 0 1px 2px rgba(0,0,0,.06), 4/8px spacing. Motion 160 to 220ms ease-out,
  transform and opacity only. No eye, stamps, paper or scanlines; an incident banner at the top of the gate states
  the leak or block in words.
- **1984 (key T, `styles-1984.css`)**: everything below this section, unchanged. Remembered per browser;
  `?theme=1984` forces it.

Where the two themes need different words, app.js renders both (`.t-classic` and `.t-console`) and each stylesheet
hides the other's, so T switches instantly without re-rendering.

## 0b. Outbound panel (console theme)

A compact strip between the rooms and the footer. It answers, from the events alone, what left this device during the
run on screen.

- **Data:** only `ledger_row` attempt rows and `blocked` events (FORMATS §7, §10). No event schema change:

  | Panel needs | Field |
  |---|---|
  | Time | `row.time` (HH:MM:SS) |
  | Destination | `row.destination` |
  | Kind | `row.kind` |
  | Decision | `row.decision` (`allowed` shown as Sent) |
  | Rule | `row.rule` |
  | Detail | `blocked.detail` or `display.detail` |

  Queries are never shown in the panel. Neither are the memo, the canary or any secret value.
- **Logic:** `ui/outbound.js` holds pure functions with no DOM, loaded before app.js and tested on their own.
  `summarize(rows)` returns one item per attempt, the sent attempts grouped by (kind, host), and the blocked attempts.
  `summaryText()` and `check()` build the two lines. Every count, host, rule and detail comes from the rows.
- **Table:** one row per outbound attempt.
  - Columns: time, destination, kind, decision (Sent / Blocked), and rule (`—` when none).
  - Kind labels follow the data's three kinds: `search` is "search", `extract` is "page read" and `reader` is
    "reading job".
  - A blocked row, or a sent row whose rule is a confirmed-secret or canary rule, is red. Other sent rows are green
    (allowed).
  - The table scrolls inside the strip, and the newest row is always in view.
- **Summary line**, in this form: `Left this device: 2 search queries to api.tavily.com, 2 reading jobs to
  api.anthropic.com. Blocked: 0.`
  - **Loopback honesty rule:** a destination on 127.0.0.1, localhost or ::1 is the local Tavily stand-in. It plays
    the web in the demo, but it never leaves the device, so it gets its own clause: `Sent to the local stand-in for the
    web (stayed on this device): 2 search queries to 127.0.0.1:8702.` The single-agent leak therefore never reads as
    "nothing left" next to a "yes" secret line.
  - With no attempts: `Nothing has left this device yet.` With attempts but all blocked: `Nothing left this device.`
- **Check line,** from the Gate's check results (the `rule` on each attempt), never from matching strings in the page.
  - It answers whether a confirmed secret (`secret.*`) or the canary (`canary`) was in a **sent** request.
  - Yes: `Confirmed secret or canary in a sent request: yes, in 1 of 2 sent requests. Row 03 to 127.0.0.1:8702:
    matches a confirmed secret (codename) (secret.codename).` The detail and the rule are the Gate's own strings.
  - No: `…: no, 0 of 4 sent requests matched.` or `…: no, nothing was sent.`
  - Notes are added after the verdict in neutral text: `Blocked before sending: 1 (secret.buyer).` and the
    provenance check (`provenance.*`, a rare memo term, which is not a confirmed secret).
  - Only the verdict is coloured: red for yes, green for no.
  - With the fixture: **yes** in the single agent (compromised) run, **no** in both Doublethink runs, and **no** with
    one block in the careless run.
- **Timing:** the panel updates on every attempt. For a leak or a block, it changes at the same moment as the
  counters and the red row (`T.leakStamp` and `T.blockStamp`), so it never gives the moment away early. It follows
  `S.view`, so during the proof beats it shows the verified run like the ledger, answer bar and counters.
- **Layout at 1280x720:**
  - The strip is 9.75rem tall, a full-width card in grid row 4 (below the step strip, section 0c); the footer is
    row 5 and the results screen covers rows 2 to 5.
  - Text is 16px, with monospace for times and hosts.
  - The 1984 theme hides the strip (`.t-console`) and keeps its own layout.

## 0c. Step strip (both themes)

One line between the header and the rooms, so a judge always knows where the run is:
`1 Drop in the memo · 2 Confirm flagged names and figures · 3 Ask a research question · 4 Cited answer + signed log`.

- **Data:** existing events only, no new fields. `ui/runview.js` (pure, tested in `ui/tests/ui.test.html`) maps
  `run_started` to step 1, `memo_loaded` to 2, `parties_confirmed` to 3, and `answer` to 4. Every other event keeps
  the step, and a run never moves back. A run that ends without an answer (leaked, blocked, budget, error) stays on
  step 3, so the strip never claims a cited answer the run did not give; the answer bar says how it ended.
- **Which run:** it follows `S.view` like the ledger, so during the proof beats it shows the verified run (step 4).
  Before any run nothing is highlighted.
- **Marking:** the current item has `aria-current="step"`; earlier items have class `done`.
  - Console: the current item is a white pill, bold, with a filled ink badge. Done items are --text-2, later items muted.
  - 1984: the current item is inverted (text on --text, like a pressed button). Done items are --text-muted, later
    items --text-dim.
  - Neutral ink only: red and green (cyan) keep their meanings. No motion.
- **Layout:** grid row 2 (`auto`, about 2.25rem). Console rows: header, steps, rooms, Outbound, footer. 1984 rows:
  header, steps, rooms, footer. The answer sheet sits in row 3; the results screen covers the strip too.

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
| --bg | #0A0A0A | L0: the void and the gate floor | – |
| --surface-1 | #161616 | L1: rooms (darkening to --surface-1-edge #0E0E0E toward the screen edge) | – |
| --surface-2 | #1E1E1E | buttons and inputs | – |
| --surface-3 | #2B2926 | L2: receipt slips and browser chrome | --text on it 12.1:1, --text-muted 5.8:1, --calm 7.4:1 |
| --slip-edge | #5C5852 | 2px outline of slips and browser windows; tear lines | – |
| --paper | #E9E4D7 | the dossier card | – |
| --ink | #16130F | dossier text, CONFIDENTIAL stamp | 14.6:1 on --paper |
| --ink-muted | #4A443A | dashed rule on the dossier | 7.6:1 on --paper |
| --marker | #111111 | redaction marker strokes | --paper on it 14.9:1 (revealed text) |
| --web-page | #F2F4F5 | browser page body, tab and address bar | – |
| --web-ink | #14181B | page text, domain | 16.2:1 on --web-page |
| --web-muted | #4D5559 | URL path, nav glyphs | 6.9:1 on --web-page |
| --glow | rgba(237,234,226,.35) | the light from the wall and the door | – |
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

The results file's example banner is not a leak, so it is styled off-white on black, never red. The VERIFYING RUN
label is off-white too, and the CONFIDENTIAL stamp is dark ink on paper.

**Light surfaces (paper, web page) never carry red or cyan text.** On them, red is always a solid `--red` fill with
`--on-red` text (5.9:1): the planted instruction and its label. Cyan does not appear on light surfaces.

### Light and layers
- **Levels:**
  - L0 is the gate floor.
  - L1 is the rooms.
  - L2 is the slips and browser chrome.
  - The documents (paper, web page) are the lightest layer.
- **Depth comes from shapes, not faint gradients:**
  - hard offset shadows (`4–6px 4–6px 0 #000`);
  - 2px outlines;
  - punched perforations;
  - tear lines;
  - the light materials.
- **The wall is the light source.** The wall bars have a static `0 0 18px` glow. The exit bar has a 3px off-white
  top edge with an upward glow, and `ONLY DOOR OUT` has a text glow. The rooms catch a little of that light on the
  side facing the wall (an inset glow).
- **Vignette:** it lives in the room and gate backgrounds (a radial gradient to a darker edge). It is not an overlay,
  so it only darkens what is *behind* the text and contrast goes up, never down. An overlay vignette was tried and
  rejected: darkening text and background together dropped muted and red text below 4.5:1 at the corners.
- **Ink texture:** the BLOCKED, LEAKED and CONFIDENTIAL outline stamps carry a static speckle `mask-image` (an inline
  SVG noise data URI, mostly opaque), like a rubber stamp. The solid INVALID block does not, because on a solid fill
  the speckle reads as noise.

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
- New pairs under the same overlays (worst pixel):

  | Pair | Contrast |
  |---|---|
  | ink on paper (with its 5% grain) | 11.3:1 |
  | web-ink on web page | 13.6:1 |
  | on-red on red | 5.1:1 |
  | --text-muted on --surface-3 | 5.1:1 |
  | --calm on --surface-3 | 6.4:1 |

  --text-dim on --surface-3 would drop to 4.4:1, so slips use --text-muted for their footer and never --text-dim.
- Under `prefers-reduced-motion: reduce` both overlays are hidden.

### Projector check
Every screenshot of a key moment is also run through a projector simulation, then checked for whether these still
separate:
- the rooms from the gate;
- the slips from the gate floor;
- the documents from their rooms;
- the stamps from their slips.

The simulation (in Pillow): `out = 46 + 0.66 × in` per channel plus 5% brightness. That lifts black to about 18% grey
and compresses the contrast.

At the depth pass, the rooms and the gate floor came out close in tone, but the 8px glowing wall separates them. The
paper, the browser windows, the slip outlines and the stamps all held up.

## 2. Type

- One family, monospace everywhere, which is the HACK1984 look and suits data:
  `--font: ui-monospace, "Cascadia Mono", "Cascadia Code", Consolas, "SF Mono", Menlo, "DejaVu Sans Mono", "Liberation Mono", monospace;`
- No font files. A free OFL pixel font in `ui/fonts/` is optional, for the wordmark only, and is added only with
  Sheara's OK.
- Labels use upper case with `letter-spacing: 0.08em`. Values keep normal case.
- `font-variant-numeric: tabular-nums` is always on, so numbers line up.
- The dossier's typewriter header uses `"Courier New", Courier` (system fonts, no file) in bold at 18px. It is the only
  other face, and it appears only on paper.
- **Room headers:**
  - a HACK1984-style index (`01 / 03`, `02 / 03`, `03 / 03`; in single agent layout `01 / 02`, `02 / 02`) in muted
    16px;
  - then the title at 24px bold upper case;
  - then the subtitle at 18px muted;
  - then a 2px dotted --text-muted ruler.

  Dotted rulers also sit under the exit bar and above the claims.

Scale, sized for 1280x720 on a projector. **Nothing is smaller than 16px.**

| Token | px at 1280 | Use |
|---|---|---|
| --fs-0 | 16 | ledger rows, excerpts, typed facts, metadata, buttons |
| --fs-1 | 18 | memo text, dossier typewriter header, answer quotes, room subtitles, page titles |
| --fs-2 | 20 | the gate eye, TIME counter |
| --fs-3 | 24 | room titles (PLANNER ROOM), wordmark, answer headline numbers |
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
  - Below the memo is a "Typed facts" list built from `planner_typed.data`. Each entry is a need line
    (`sector_growth · found`), then one **receipt chip** per `values[]`:
    - the slip material (`--surface-3`, a 2px `--slip-edge` outline, a 3px hard shadow);
    - the **value large** (24px bold), then the **unit** word small and muted;
    - a dashed tear line, then a foot `period · result_id` in muted text.

    The unit stays the raw enum (`percent`, `multiple`), because that is exactly what the Planner receives. There is
    no web text here, and the room's subtitle says so.
  - The Planner room shows the session `S.view`, like the ledger. Its dossier and typed facts are stored per session
    and redrawn by `showRunSummary()`. During the proof beats they switch to the verified run together with the
    ledger, the answer bar and the counters.
- **Gate ledger** (one entry per `ledger_row` event, using `data.row` and `data.display`):
  - Attempt rows (`row_type "attempt"`) show `seq`, `kind`, a short destination, `display.query` (or
    `display.summary` for reader rows), and the decision mark: `✓` cyan for allowed, `✕ BLOCKED` red for blocked.
  - Short destinations: `api.tavily.com` → `tavily`, `api.anthropic.com` → `anthropic`, `127.0.0.1:8702` →
    `fake:8702`. The full host is in the `title` tooltip.
  - Result rows (`row_type "result"`) are the tear-off stub under their attempt (`attempt_seq`), in --text-muted,
    for example `↳ 200 · 1 credit` from `http_status` and `credits_used`.
  - Each row shows a short `hash` (first 4 and last 4 hex). The proof walk uses it. On attempts it is the receipt
    footer, `#c2a8…3e01 · 139 B · 23:40:41` (`bytes`, and `time` as HH:MM:SS). On stubs it sits at the right of the
    line.
  - The material, receipt slips, is described in "Materials" below.
  - `rule` and `display.detail` show under the row when they are set. Every rule renders the same way, including
    the Gate-owned `gate.path_not_allowed` and `gate.reader_error` (FORMATS §6): red when the attempt was blocked.
  - **Leak rule, word for word with FORMATS §10 (`run_done`):** an attempt is a **leak** only if it was `allowed`
    and its `rule` is `canary` (exact) or starts with `secret.` or `provenance.`.
    - A leak gets the LEAKED stamp and red, and counts in LEAKS.
    - An allowed attempt with any other rule (`shape.*`, `gate.*`) is **noted**: it keeps the cyan `✓` and shows
      `rule … · recorded, not a leak` in muted text, with no red, no stamp and no count.
    - Note for the group: FORMATS line 339 (§10 `ledger_row` notes) still carries the old "non-null rule is a leak"
      sentence, which the changelog has dropped. The UI follows the newer rule.
  - After a `blocked` event whose `data.planted` is true, the row is tagged `planted test query`.
- **Reader room:**
  - It shows `docs_read.data`: the `public_query` at the top, then one browser window per `docs[]` (see
    "Materials").
  - Each `highlights[].text` is a solid red marker with `--on-red` text. `highlights[].label` sits underneath as a
    red chip ("▲ planted instruction (demo annotation)").
  - Excerpts can be up to 2,000 characters (FORMATS §3). The text scrolls **inside** the browser window
    (`max-height: 12.5em`), and is focusable (`tabindex="0"`, `role="region"`) so it can be scrolled by keyboard.
  - When a poisoned page arrives, the room scrolls to the top of its window, so the tab and address bar stay in
    view. The excerpt then scrolls just enough to show the planted line.
  - Below the cards come `reader_claims.data`: `kept` claims with their quotes, and `dropped` claims in muted text
    with `reason`.
- **Answer bar:** a one-line summary of the `answer` event.
  - A run that ends without an answer shows `No answer. Run ended: {outcome}.`, with `run_done.data.reason` in
    brackets after the outcome when it is not null (for example `Run ended: error (reader timed out).`). The run
    labels (`{mode} · {source} · {outcome}`) show the reason the same way (`RunView.outcomeText`).
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
- A row counts as a leak when it is an `allowed` attempt whose `rule` is `canary` or starts with `secret.` or
  `provenance.` (FORMATS §10, see "Gate ledger"). It gets the LEAKED stamp, and every confirmed secret value that
  appears literally in `display.query` is wrapped in a red highlight.
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
- **Materials.** Each kind of thing has its own physical material, so a judge can tell the secret, the web and the
  record apart at a glance:

  | Thing | Material | Built from |
  |---|---|---|
  | The memo (the secret) | **A paper dossier.** An off-white `--paper` card with `--ink` text, 5% static darken-only paper grain, and a hard 6px offset shadow. A typewriter header (`FILE 1984 · SHA c4be…5bb0`, then `SUBJECT: …`) sits over a dashed rule. Below it, an ink-stamped `CONFIDENTIAL`: dark ink, a double border, rotated -4deg, with ink speckle. Redactions are black marker strokes (`--marker` with a faint streak texture); hover or focus reveals the value in paper colour on the black bar. | `dossier()` → `article.paper` |
  | The web | **A mini browser window.** A `--surface-3` chrome frame with a 2px `--slip-edge` outline and a 6px shadow. Inside: a square tab (`r_03 · title`), an address bar (`‹ › ↻` and a field with the **domain** bold and the path muted), then the light page with the title and the excerpt. | `docNode()` → `article.browser` |
  | The record | **Printed receipt slips.** Each attempt is a `--surface-3` slip with a 2px outline, a 4px hard shadow and a punched perforation along its top edge. Its footer, under a dashed tear line, holds the hash, the bytes and the time. Its result row is the indented tear-off stub underneath. The red layer, stamps and proof marks work as before. | `rowNode()` → `li.row` |
- **Dossier details.** Both rooms with a memo show the paper card. The subject is `memo_loaded.title` and the sha is
  the short `memo_loaded.sha256`.

  Redaction in the Planner room:
  - It is case-insensitive, so the subject `PROJECT HALYARD` and the memo's first line are hidden like
    `Project Halyard`.
  - `memo_id` is never shown, because it repeats the codename.
  - The One agent room shows everything in the clear, because that agent holds the secrets.
- **The eye.** A 5-line ASCII eye, 20px bold (about 230×115px), sits at the right of the gate header.
  - It is **open** in single agent layout (one model sees everything) and **closed** in Doublethink layout
    (nothing can leave). The closed eye is a downward-curved lid from corner to corner (`<.` … `'-.___.-'` … `.>`)
    with lashes hanging below (`/ /  |  \ \`), in off-white `--text`, in the same 19×5 box as the open eye.
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
  - `signer key {first 16 hex}…` from `proof_result.data.signer_key_sha256` (FORMATS §8, §10). It matches the
    verifier's text output `VALID (signer key <16 hex>)`, with the full value on hover. It is shown only when the
    field is a 64-hex string; when the field is absent or null, nothing is shown.
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

- It replaces the whole main area, including the Outbound strip and the footer.
- **Measured numbers come only from `/shared/results/results.json`. No number is typed into the code.**
  - app/run.py serves `/shared/results/` (FORMATS §11, confirmed by Ilia), and so does `ui/preview.py`.
- **No silent example data (Ilia's must-fix).** The page never falls back to `results_example.json` on its own.

  | Situation | What the screen shows |
  |---|---|
  | `results.json` missing (404) | **"No measured results yet"**: the path that is missing, that numbers appear once the red-team run writes it, and how to preview with `?example=1`. No numbers, no bars, and the example file is not even fetched. |
  | `results.json` unreadable (HTTP error, bad JSON, no runs) | The same "No measured results yet" state, with the error. |
  | `results.json` marked `"example": true` | The same state ("marked as example data, so it is not shown as a measurement"). Example data cannot enter through the real path either. |
  | `results.json` present and not marked as example | The measured screen below. |
  | URL has **`?example=1`** | Only the example file is loaded (the real one is not used). A large **"EXAMPLE DATA, not measured"** banner sits at the top (--fs-3, dashed outline), naming the file and the parameter. **Every number** carries the same label right next to it (18px bold, dashed outline): the attack total, each bar value, false blocks, answered-with-a-cited-number and both cost figures. |

  The label uses neutral ink (`--text`) with a dashed border, never red, green or amber, which keep their meanings.
  Both themes follow these rules.
- Tests (`ui/tests/ui.test.html`, run by `test_ui_browser`), in both themes:
  - with `results.json` missing, the screen says "No measured results yet", shows no numbers or bars, shows no example
    label, and the page makes no request for `results_example.json`;
  - with `?example=1`, the banner is at least 24px, every `[data-num]` value carries the label at 18px or more, and
    exactly one example fetch is made.
  - If a checkout already has `results.json`, the missing-file case reports SKIP, and the test instead checks that the
    example file is not fetched without `?example=1`.
- FORMATS §9 still has one judgement per run (`leak_judge`, a single description). If it ever stores several
  (for example the frozen detector plus a fallback), the screen shows the frozen-detector judgement and labels any
  fallback clearly.
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
- **Which run each number comes from is decided by the data, never by position** (`ui/results.js`, Ilia's check
  on PR #39). `runs` keeps every run in time order and never deletes one, and runs differ in how they were judged:
  1. A run whose `leak_judge` (or, as in the real file, `judge`) text says FALLBACK is **never shown**.
  2. A run counts as scored by the frozen detector only if `detector.matches_checks_frozen` is true.
  3. For each mode, the screen uses the **most recent** run that passes 1 and 2 and has that mode. False blocks,
     usefulness and cost are chosen the same way. With none, the screen says "not measured".
  4. Under the bars, "Where each number comes from" names each source run: `run N of M`, its label and its commit.
     The label alone is not unique: the real file has two runs labelled "checks-frozen". Excluded runs are listed as
     "Not shown: run N of M (scored with the fallback judge)", with no numbers.

  With the real file (PR #38: three runs), single agent and compromised come from run 2 ("checks-frozen
  rejudged-frozen"), and two minds and two minds + gate from run 3 (batch 2, commit c303c1c). Run 1 (fallback judge,
  single agent 1/40) is never shown. The old tick marks for `runs[0]` are gone, because they showed the fallback run.
  - With `?example=1` the example file has no judge or detector fields. Its runs are accepted unless they say
    FALLBACK, and every number carries the example label.
  - Test: `ui/tests/fixtures/results_three_runs.json` is shaped like the real file. Its fallback run carries
    distinctive numbers, and the harness checks that none of them appear, that each mode comes from the right run,
    and that a FALLBACK `leak_judge` or a missing detector flag also excludes a run.
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

- Files are `ui/index.html`, `ui/styles.css`, `ui/styles-1984.css`, `ui/outbound.js` and `ui/app.js`, plus
  `ui/preview.py`, `ui/check_network.py` and the tests in `ui/tests/`. `ui/fonts/` is added only with approval.
- **Nothing external.** The page loads only its own files from its origin:
  - no web fonts (system font stacks only), no CDN scripts, no icon sets and no analytics;
  - the favicon is an inline `data:` URI, so the browser does not request `/favicon.ico`.

  Proven three ways:
  1. `ui/tests/test_static.py` scans the page files for external URLs and `@import`. The SVG namespace string is the
     only allowed `http` text.
  2. `python ui/check_network.py` plays the **full replay** in both themes in headless Edge, served by preview.py. It
     records the browser's net log and the page's Resource Timing, and writes `ui/evidence/network-replay.md`.
     - The check fails if the page requests, loads or connects to anything but 127.0.0.1.
     - During the run, every non-loopback host is mapped to NOTFOUND, so nothing can leave even if something tried.
     - Edge's own background attempts (autofill, network time) are listed openly, separately from the page, with
       their outcome.
  3. `ui/tests/test_network.py` runs the same check into a temp file on every test run.
- **Tests** (`python -m unittest discover -s ui/tests -t .`, standard library only):
  - `test_preview` and `test_static`.
  - `test_ui_browser`: headless Edge or Chrome runs `ui/tests/ui.test.html`, which covers:
    - the Outbound logic and the panel in the page;
    - the four fixes on main: the canary is never in the DOM at any of the fixture's event times, in both themes; a
      run's memo never appears before its `parties_confirmed`; tampered rows show only the failure; reader job counts
      come from `docs_read` and typed facts appear once.
  - `test_network`.

  The browser tests skip with a reason when no browser is found (`DT_BROWSER` overrides the path).
- Replay reads `shared/fixtures/demo_events.jsonl` (one FORMATS §10 envelope per line) and waits on `t_ms`.
- Live reads `GET /events?token=…` (SSE, no `event:` line). Replay and live share one dispatcher keyed on `type`.
- Paths are relative to the one origin: the page is at `/ui/index.html` and the fixtures are read from
  `/shared/fixtures/…` (FORMATS §11).
- **Local preview: `python ui/preview.py`**, then open `http://127.0.0.1:8703/ui/index.html`. On this Windows
  machine the command is `python`, not `python3`. In live mode the same files are served by app/run.py on `APP_PORT`
  (8700).
  - **The repo root is no longer served** (Ilia's request). `python -m http.server` from the repo root exposed every
    file, including notes, other folders and the ledger.
  - `ui/preview.py` is standard library only (`ThreadingHTTPServer`). It binds **127.0.0.1:8703** only and installs
    a loopback-only audit hook (invariant 1).
  - It serves **only `/ui/` and `/shared/`**, and only page file types (`.html .css .js .json .jsonl .svg .png
    .woff2`). `/` redirects to `/ui/index.html`.
  - It refuses with 404:
    - any other folder;
    - `..`, `//`, `/./` and encoded traversal (`%2e%2e`, `%2f`, `%5c`);
    - backslashes and NUL bytes;
    - dotfiles (`.env`, `.git`);
    - Python and Markdown files (including its own source);
    - symlinks that resolve outside `ui/` or `shared/`.
  - Directory listings get 403, and every method except GET and HEAD gets 501.
  - Every response carries `Cache-Control: no-store` (so screenshots never show a stale page) and
    `X-Content-Type-Options: nosniff`.
  - Tests: `python -m unittest ui.tests.test_preview`.
  - All screenshots are taken through `ui/preview.py`. Port 8703 is the agreed preview port (section 10, item 5).
- **Replay or live:** the page is live when its URL has `?token=` and replays the fixture otherwise.
- **URL parameters** for rehearsal and screenshot QA:

  | Parameter | Effect |
  |---|---|
  | `?replay=1` | forces replay even with a token |
  | `?at=<ms>` | jumps the replay to that time (no title screen) |
  | `?play=1` | starts playing |
  | `?title=0` | skips the title screen |
  | `?open=answer` | opens the answer sheet |
  | `?example=1` | the results screen shows `shared/fixtures/results_example.json`, with "EXAMPLE DATA, not measured" on every number. Without it, example data never appears. |
  | `?freeze=<ms>` | with `?at=`, plays the next 100ms of events with animation, then pauses every animation at `<ms>`, so a frame of a moment can be screenshotted (for example `?at=86500&freeze=450` for the block, `?at=20990&freeze=900` for the leak) |

## 10. Items not in shared/FORMATS.md

### Open
None.

### Resolved
| # | Item | Resolution | Source |
|---|---|---|---|
| 2 | How the page reads `shared/results/results.json` | app/run.py serves `/shared/results/…` statically (FORMATS §11). The page reads `/shared/results/results.json` only. If it is missing it shows "No measured results yet" (section 7). The example file loads only with `?example=1`, and then every number is labelled. | Ilia confirmed; no-fallback rule is Ilia's must-fix |
| 1 | The token in the UI URL | `?token=` in the page URL. The page sends it as `?token=` on `/events` and `/api/bundle`, and as the `X-DT-Token` header on `/api/*` POSTs. | Aayush confirmed |
| 3 | The mode for the Single agent toggle | `compromised` (with `source: "fake"`) | notes/DEMO.md |
| 4 | The body Run sends | `POST /api/run {"mode", "source": "real"\|"fake", "plant_careless": true\|false}`. The source selector next to Run sets `source`, and a "careless query" switch sets `plant_careless`. Single agent forces `fake`. | Aayush |
| 5 | The preview port | 8703, served by `python ui/preview.py` (section 9), no longer from the repo root | Ilia proposed; restricted server at Ilia's request |

Checked against FORMATS.md and present there (no action needed):
- Events: all twelve event types (§10).
- Endpoints: `/events`, `/api/run`, `/api/verify`, `/api/tamper`, `/api/bundle` (§11).
- Command: `python3 proof/verify.py` and its reason codes (§8).
- Paths: `bundles/<session_id>.json`, `shared/fixtures/results_example.json`, `shared/results/results.json` (§8, §9).
- Fields: leak definition, `display.query` highlighting, `blocked.planted`, `docs_read.highlights`, the `runs` order
  and the `example` banner.
