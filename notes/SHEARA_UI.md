# Sheara: UI and demo guide (Doublethink, HACK1984)

Read TEAM_BRIEF.md first. This doc covers only your part: the screen the judges watch for three minutes.
No code before 11:00. Installing skills before 11:00 is fine (it is setup, not code).

---

## 1. What the UI has to do

Judges decide in the first 20 seconds whether they understand the project. Your screen has to make three things
obvious with no explanation:

1. **The secret is in one room and the web is in another.** They never touch.
2. **Every request leaving the system passes one gate**, and we can see each one, including blocked ones in red.
3. **The record is real**: one button verifies it, and changing one byte breaks it.

If a judge looks at a screenshot and gets those three, the UI has done its job.

---

## 2. Design direction: "two rooms and a wall"

The event brand is HACK1984 (black, off-white, one red, pixel and monospace type). Our project name, Doublethink,
is also from 1984. Lean into it on purpose, so the UI looks like it belongs at this event and not like a generic
SaaS dashboard.

**Palette (suggestion, finalize with the design skill):**
- Background near-black, text off-white, one red accent used **only** for leaks and blocks.
- One calm color (muted green or cyan) used **only** for "verified" and "allowed".
- Everything else greyscale. If red appears, something bad happened. Judges learn that rule in one second.

**Type:** a monospace face for the ledger and queries (they are data), a clean sans for labels. No Google Fonts
link: the page must work offline. Use the system font stack, or put a free OFL font file in `ui/fonts/`.

**Layout at 1280x720 and 1920x1080 (projector first):**

    +-----------------------------------------------------------------------------------+
    | DOUBLETHINK      [ Single agent | Doublethink ]     Run    Verify proof    Bundle   |
    +--------------------------+---------------------------+----------------------------+
    | PLANNER ROOM             |        THE GATE           | READER ROOM                |
    | "never reads the web"    |   (the only door out)     | "never sees the secret"    |
    |                          |                           |                            |
    | Memo                     |  ledger rows stream here  | web pages being read       |
    | secrets shown as         |  seq  dest   query  ok    | poisoned line highlighted  |
    | redaction bars you can   |  12   tavily "payments.." | when it appears            |
    | hover to reveal          |  13   tavily BLOCKED red  |                            |
    |                          |       rule: secret.buyer  | claims extracted, each     |
    | typed facts arriving     |                           | with its quote             |
    | (numbers only)           |                           |                            |
    +--------------------------+---------------------------+----------------------------+
    | ANSWER: numbers with quote and source        | leaks 0 | blocked 2 | credits 9 | 41s |
    +-----------------------------------------------------------------------------------+

**Single agent mode:** the wall disappears. Memo and web text sit in one panel. When the poisoned page is read, the
next outgoing query shows "Project Halyard", "Ossory Capital Partners" and "$412 million" highlighted in red with a
"LEAKED" tag. This is the before. Doublethink mode is the after, same page, nothing leaks.

**Proof panel:** "Verify proof" walks the hash chain row by row (fast tick down the ledger), then shows VALID.
A "Tamper one byte" button edits one row; verify again and the chain breaks at that row in red: INVALID.

**Results screen (last 30 seconds of the demo):** one view, four bars: leaks out of 40 attacks for single agent,
compromised agent, two minds, two minds plus gate. Below: false blocks on 30 normal questions. Numbers come from a
JSON file Anant and Ilia produce; never type a number by hand.

---

## 3. Motion: only where it explains something

Every animation must answer "what just happened?". Nothing decorative.

| Moment | Motion | Why |
|---|---|---|
| Planner sends a request | a small packet slides from Planner room into the Gate (about 200ms) | shows the only path out |
| Gate allows | row lands in the ledger, packet continues out | normal flow |
| Gate blocks | packet stops at the wall, short shake, row turns red with the rule | the moment judges remember |
| Reader reads the poisoned page | the hidden instruction line highlights red in the Reader room, and nothing crosses the wall | proves the poisoned text reached a room with nothing to steal |
| Single agent leaks | secret words in the outgoing query flash red, "LEAKED" stamp | the before |
| Verify proof | ledger rows tick through, check marks, then VALID | makes "tamper evident" visible |
| Tamper | the edited row and every row below it break red | one byte breaks everything after it |

Rules: animate transform and opacity only; 150 to 250ms for small moves; one easing curve for the whole page;
respect `prefers-reduced-motion`; no motion that delays the demo.

---

## 4. Claude Code design skills to install

Install these in the repo (project scope), not globally, and read each SKILL.md before using it: they are
instructions written by other people. Do not install more than these; several design skills at once give
conflicting rules.

| Skill | What it does for us | Install |
|---|---|---|
| **frontend-design** (Anthropic, official) | stops generic "AI dashboard" look; makes Claude pick a clear aesthetic before coding | `/plugin marketplace add anthropics/skills` then `/plugin install frontend-design@anthropic-agent-skills`, or `npx skills add https://github.com/anthropics/skills --skill frontend-design` |
| **Impeccable** (Paul Bakaus) | design critique and audit commands, anti-slop rules; use for review passes | follow the README at github.com/pbakaus/impeccable |
| **motion-design** (LottieFiles) | rules for easing, timing, reduced motion, library-independent | `npx skills add lottiefiles/motion-design-skill --skill motion-design` |
| **web-design-guidelines** (Vercel) | accessibility, contrast, spacing checks | `/plugin marketplace add vercel-labs/agent-skills` |

Conflict to watch: these skills like Google Fonts, CDNs and frameworks. Our rule wins: no CDN, no external fonts,
no framework, plain HTML, CSS and JavaScript, one folder, works offline. Put that in every prompt (the prompts below
already do).

After installing, start Claude Code from the repo folder and ask: "Which skills are loaded?" to confirm.

---

## 5. Your build order and prompts

Model: Opus 5.5, high effort. Plan mode first for every prompt, then approve. Work only in `ui/`, on your branch
`sheara`. Merge to main at least every 2 hours. Wait for `shared/FORMATS.md` and
`shared/fixtures/demo_events.jsonl` (about 11:45) before step 2.

### Step 1 (11:15, plan mode only): design system

```
Read CLAUDE.md, notes/TEAM_BRIEF.md, notes/SHEARA_UI.md and notes/DEMO.md. I am Sheara and I own ui/
only. Use the frontend-design and motion-design skills.
Write ui/DESIGN.md: the design direction "two rooms and a wall" from SHEARA_UI.md section 2, adapted
to the HACK1984 look (black, off-white, one red, monospace). Include: color tokens with the rule that red
means only leak or block and the calm color means only verified or allowed; type scale readable on a
projector at 1280x720 (nothing below 16px); spacing scale; layout for both modes; every motion from
section 3 with duration and easing; the proof panel; the results screen.
Hard rules: no CDN, no external fonts, no framework, plain HTML, CSS and JavaScript, works offline,
contrast at least WCAG AA. Show me DESIGN.md before writing it.
```

### Step 2 (11:45 to 14:00): the page, driven by recorded events

```
Build ui/ from ui/DESIGN.md: index.html, styles.css, app.js, served by a tiny loopback server
(standard library Python, a random per-launch token in the URL).
Drive everything from shared/fixtures/demo_events.jsonl through a replay engine with realistic timing,
using the event names in shared/FORMATS.md exactly. Three panels (Planner room, Gate ledger, Reader
room), answer bar, metrics strip, mode toggle, Run, Verify proof, Download bundle.
Keyboard: Space plays or pauses the replay, Right arrow jumps to the next demo beat, R restarts,
1 and 2 switch modes. The demo must never depend on the network.
Open it in a browser at 1280x720, take a screenshot, and critique it against DESIGN.md before telling
me it is done.
```

### Step 3 (14:00 to 17:00): motion and the two money moments

```
Add the motions in ui/DESIGN.md section on motion, transform and opacity only, one easing curve,
prefers-reduced-motion respected. Make two moments excellent:
(1) the Gate blocking a request: packet stops at the wall, short shake, row turns red with the rule;
(2) single-agent mode leaking: secret words in the outgoing query flash red with a LEAKED stamp.
Then the proof panel: Verify walks the chain row by row and shows VALID; Tamper one byte edits a row and
Verify breaks the chain red from that row down. Record the screen for each moment and check the timing.
```

### Step 4 (17:00 to 19:00): results screen and polish

```
Add the results screen: four bars for leaks out of 40 attacks (single agent, compromised agent, two
minds, two minds plus gate) and false blocks out of 30 normal questions, read from
shared/results/results.json (use shared/fixtures/results_example.json until the real file exists; show
"example data" clearly while it is the example). Never hard-code a number.
Then run an Impeccable critique and an accessibility pass (contrast, focus states, font sizes on a
projector). Fix the top five issues only. Show me before and after screenshots.
```

### Step 5 (19:00 to 21:00): live wiring

```
Add a switch: replay mode (fixture file) or live mode (Server-Sent Events from app/run.py on loopback,
same event names). Live mode must degrade cleanly: if the stream drops, show a clear status and keep the
last state. Run one live end-to-end run with Aayush and list every event that did not match FORMATS.md.
Keep replay mode as the fallback for the demo.
```

### Step 6 (21:00 onward): demo rehearsal

```
Walk notes/DEMO.md beat by beat against the page in replay mode. Time each beat. The whole demo must fit
in 3 minutes with 15 seconds spare. Add a hidden presenter overlay (key P) that shows the current beat,
the line to say, and time left. Then record the full run as the backup video.
```

---

## 6. What "done" looks like
- Replay demo runs start to finish from one key press, offline, in under 3 minutes.
- A judge looking at one screenshot can tell: secret on one side, web on the other, gate in the middle, red means
  blocked.
- Verify shows VALID, tamper shows INVALID at the right row.
- Results screen reads from the JSON file, never from typed numbers.
- Readable from the back of the room at 1280x720.

## 7. Who to talk to
- Event names or formats wrong: Aayush (he owns app/run.py) and the group chat.
- Results numbers: Anant (false blocks) and Ilia (attack numbers).
- What the demo says and when: Ilia.
