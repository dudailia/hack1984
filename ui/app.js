// Doublethink UI. Event names and fields: shared/FORMATS.md section 10. Design: ui/DESIGN.md.
// Two themes share this DOM: console (styles.css, default) and 1984 (styles-1984.css, key T). Where their words
// differ, both variants are rendered (.t-console / .t-classic) and each stylesheet hides the other's.
// One dispatcher on env.type serves both the replay file and the live SSE stream.
// All data goes into the DOM through textContent / text nodes, never innerHTML.
// Motion never delays the replay: every sequence is CSS delays or fire-and-forget timers.
'use strict';

(() => {
  const $ = (sel) => document.querySelector(sel);

  // Append (or replace with) children, flattening nested arrays and skipping null / false.
  function fill(n, kids, replace = true) {
    const list = [kids].flat(Infinity).filter((c) => c != null && c !== false)
      .map((c) => (c instanceof Node ? c : String(c)));
    if (replace) n.replaceChildren(...list); else n.append(...list);
    return n;
  }

  function el(tag, props, ...kids) {
    const n = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v == null || v === false) continue;
        if (k === 'class') n.className = v;
        else if (k === 'style') n.style.cssText = v;
        else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
        else n.setAttribute(k, v === true ? '' : String(v));
      }
    }
    return fill(n, kids, false);
  }

  // ---------- configuration ----------
  const params = new URLSearchParams(location.search);
  const TOKEN = params.get('token');
  const LIVE = !!TOKEN && params.get('replay') !== '1';
  const FIXTURE = '/shared/fixtures/demo_events.jsonl';
  const RESULTS_REAL = '/shared/results/results.json';
  const RESULTS_EXAMPLE = '/shared/fixtures/results_example.json';
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const EASE = 'cubic-bezier(0.2, 0, 0, 1)';
  document.body.classList.add(LIVE ? 'live' : 'replay');

  // ---------- theme (key T) ----------
  const THEME_KEY = 'dt-theme';
  function readTheme() {
    const q = params.get('theme');
    if (q === '1984' || q === 'console') return q;
    try { return localStorage.getItem(THEME_KEY) === '1984' ? '1984' : 'console'; } catch (_) { return 'console'; }
  }
  let theme = readTheme();
  function applyTheme(t) {
    theme = t;
    $('#css-console').disabled = t !== 'console';
    $('#css-classic').disabled = t !== '1984';
    document.body.classList.toggle('theme-console', t === 'console');
    document.body.classList.toggle('theme-classic', t === '1984');
    try { localStorage.setItem(THEME_KEY, t); } catch (_) { /* private window: the theme just isn't remembered */ }
  }
  applyTheme(theme);
  const classic = () => theme === '1984';

  // Both theme variants of one piece of text or nodes.
  const dual = (c1984, cConsole) => [el('span', { class: 't-classic' }, c1984), el('span', { class: 't-console' }, cConsole)];
  const cap = (t) => (t ? t[0].toUpperCase() + t.slice(1) : t);

  const SINGLE_MODES = new Set(['single_agent', 'compromised']);
  const UNIT_SUFFIX = { percent: '%', multiple: 'x' };
  // Moment timings (ms after the attempt row arrives). DESIGN.md section 5.
  const T = { blockRed: 400, blockStamp: 650, leakFlash: 400, leakStamp: 800, typeMax: 350 };

  // ---------- state ----------
  let S;
  let walkTimers = [];
  let fxTimers = [];
  let results = null;
  let resultsSource = null;

  function freshState() {
    return {
      sessions: {},      // session_id -> see session()
      current: null,     // session of the latest run_started
      view: null,        // session whose ledger, answer and counters are on screen
      lastDone: null,    // session of the latest run_done (target for Verify / Tamper / Bundle)
      uiMode: 'dt',      // 'single' | 'dt'
      fakeDest: null,
      beat: null,
      proofOpen: false,
    };
  }

  function session(sid) {
    if (!S.sessions[sid]) {
      S.sessions[sid] = {
        rows: [], typed: [], typedKeys: new Set(), urls: {}, secrets: [], secretsReady: false, canary: null, mode: null, source: null, careless: false,
        memo: '', title: '', sha: '', answer: null, done: null, step: 0,
        m: { leaks: 0, blocked: 0, credits: 0, seconds: null },
      };
    }
    return S.sessions[sid];
  }

  const animOK = (o) => !(o && o.instant) && !reduceMotion.matches;

  // Screenshot QA hook (?at=<ms>&freeze=<ms>): play the next moment, then hold every animation at <freeze> ms.
  let FREEZE = null;

  function later(fn, ms) {
    if (FREEZE != null) { if (ms <= FREEZE) fn(); return; }
    fxTimers.push(setTimeout(fn, ms));
  }
  function clearFx() {
    fxTimers.forEach(clearTimeout);
    fxTimers = [];
    $('#fx').replaceChildren();
  }

  // ---------- helpers ----------
  const shortHash = (h) => (h ? `${h.slice(0, 4)}…${h.slice(-4)}` : '');
  const pad2 = (n) => String(n).padStart(2, '0');

  function shortDest(d) {
    if (!d) return '';
    if (d === 'api.tavily.com') return 'tavily';
    if (d === 'api.anthropic.com') return 'anthropic';
    const m = /^127\.0\.0\.1:(\d+)$/.exec(d);
    if (m) return `fake:${m[1]}`;
    return d;
  }

  function fmtValue(v, unit) {
    const s = String(v);
    if (unit === 'usd') return `$${s}`;
    if (unit === 'usd_millions') return `$${s}m`;
    if (unit === 'usd_billions') return `$${s}bn`;
    return s + (UNIT_SUFFIX[unit] || '');
  }

  function fmtClock(ms) {
    const s = Math.max(0, Math.floor(ms / 1000));
    return `${Math.floor(s / 60)}:${pad2(s % 60)}`;
  }

  // Split text into plain and matched segments. terms: [{text, label}], longest first, non-overlapping.
  // ci = case-insensitive (used for redaction, so "PROJECT HALYARD" is hidden like "Project Halyard").
  function splitTerms(text, terms, ci = false) {
    const list = terms.filter((t) => t.text).sort((a, b) => b.text.length - a.text.length);
    const hay = ci ? text.toLowerCase() : text;
    const needles = list.map((t) => (ci ? t.text.toLowerCase() : t.text));
    const out = [];
    let buf = '';
    let i = 0;
    while (i < text.length) {
      const k = needles.findIndex((nd) => hay.startsWith(nd, i));
      if (k >= 0) {
        if (buf) { out.push({ text: buf }); buf = ''; }
        const len = needles[k].length;
        out.push({ text: text.slice(i, i + len), term: list[k] });
        i += len;
      } else {
        buf += text[i];
        i += 1;
      }
    }
    if (buf) out.push({ text: buf });
    return out;
  }

  function waiting(text) {
    return el('p', { class: 'empty waiting' },
      dual([`> ${text}`, el('span', { class: 'cursor', 'aria-hidden': 'true' })], cap(text)));
  }

  // Scroll a container so that `node` is visible, without scrolling any ancestor.
  function scrollWithin(container, node, where = 'nearest') {
    if (!container || !node) return;
    const c = container.getBoundingClientRect();
    const r = node.getBoundingClientRect();
    if (where === 'center') container.scrollTop += r.top - c.top - (c.height - r.height) / 2;
    else if (where === 'start') container.scrollTop += r.top - c.top - 8;
    else if (r.bottom > c.bottom) container.scrollTop += r.bottom - c.bottom + 8;
    else if (r.top < c.top) container.scrollTop += r.top - c.top - 8;
  }

  let toastTimer = null;
  function toast(msg) {
    const t = $('#toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), 3200);
  }

  // ---------- title screen ----------
  function showTitle() { $('#title').classList.add('show'); }
  function hideTitle() { $('#title').classList.remove('show'); }
  const titleShown = () => $('#title').classList.contains('show');

  // ---------- the eye ----------
  function setEye(open, red) {
    const eye = $('#eye');
    eye.classList.toggle('closed', !open);
    if (red != null) eye.classList.toggle('red', !!red);
    const st = !open ? 'closed: nothing can leave' : eye.classList.contains('red') ? 'open: a secret leaked' : 'open: one agent sees everything';
    $('#eye-state').textContent = `Eye ${st}`;
  }

  // ---------- layout and header ----------
  function setUiMode(m) {
    S.uiMode = m;
    $('#mode-single').setAttribute('aria-pressed', String(m === 'single'));
    $('#mode-dt').setAttribute('aria-pressed', String(m === 'dt'));
    const main = $('#main');
    main.classList.toggle('single', m === 'single');
    main.classList.toggle('dt', m === 'dt');
    $('#source').disabled = m === 'single';
    $('#careless').disabled = m === 'single';
    if (m === 'single') $('#source').value = 'fake';
    setEye(m === 'single');
    renderGateHead();
    renderMemo();   // the clear copy exists only while the single agent layout is shown
  }

  function renderBadge() {
    const b = $('#badge');
    const s = S.view && S.sessions[S.view];
    if (s && s.source === 'real') b.textContent = 'SOURCE: api.tavily.com (real)';
    else if (s && s.source === 'fake') b.textContent = 'SOURCE: LOCAL STAND-IN (fake)';
    else b.textContent = 'SOURCE: —';
    b.title = b.textContent;
    const pill = $('#session-pill');
    pill.hidden = !(S.view && s);
    if (s) fill(pill, [el('span', { class: 'mono' }, S.view), s.source ? ` · ${s.source}` : '']);
    pill.title = s && s.source === 'real' ? 'Searches go to api.tavily.com' : s ? 'Searches go to the local stand-in' : '';
  }

  function runBits(sid) {
    const s = S.sessions[sid];
    if (!s) return [];
    const bits = [s.mode, s.source];
    if (s.careless) bits.push('careless query');
    if (s.done) bits.push(window.RunView.outcomeText(s.done));
    return bits.filter(Boolean);
  }
  const runDescription = (sid) => [sid, ...runBits(sid)].join(' · ');
  const runLabel = (sid) => dual(`VERIFYING RUN ${runDescription(sid)}`,
    ['Showing run ', el('span', { class: 'mono' }, sid), runBits(sid).map((b) => ` · ${b}`).join('')]);

  function renderGateHead() {
    const single = S.uiMode === 'single';
    const s = S.view && S.sessions[S.view];
    fill($('#gate-title'), single ? dual('Outbound', 'Outbound') : dual('The gate', 'The gate'));
    let sub = 'the only way out';
    if (single) sub = 'recorded, not enforced';
    else if (s && s.mode === 'two_minds') sub = 'recording only · not enforcing';
    fill($('#gate-sub'), dual(sub, cap(sub)));

    const exit = $('#exit');
    exit.replaceChildren(el('span', { class: 'door' }, dual(single ? 'EXIT ▲' : 'ONLY DOOR OUT ▲', single ? 'Destinations' : 'Allowed')));
    const dests = [];
    if (s && s.source === 'real') dests.push('api.tavily.com');
    else if (s && s.source === 'fake') dests.push(S.fakeDest || '127.0.0.1 (local stand-in)');
    dests.push('api.anthropic.com (reader only)');
    for (const d of dests) exit.append(el('span', { class: 'dest' }, d));

    // When the ledger shows an earlier run than the latest one (the proof beats), say so loudly.
    const other = S.view && S.view !== S.current;
    fill($('#run-label'), other ? runLabel(S.view) : []);
    $('#ledger-session').textContent = S.view && !other ? `ledger ${S.view}${s && s.mode ? ` · ${s.mode}` : ''}` : '';
  }

  // ---------- incident banner (console theme) ----------
  const andList = (xs) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`);

  function incidentFor(sid) {
    const s = sid && S.sessions[sid];
    if (!s) return null;
    const bad = s.rows.filter((e) => ['blocked', 'leak'].includes(rowKind(e.row)));
    if (!bad.length) return null;
    const e = bad[0];
    const row = e.row;
    const d = e.display || {};
    const more = bad.length > 1 ? ` (+${bad.length - 1} more)` : '';
    if (rowKind(row) === 'blocked') {
      const detail = (e.blockedInfo && e.blockedInfo.detail) || d.detail;
      return { kind: 'blocked', title: ['Blocked by policy ', el('span', { class: 'mono' }, row.rule || 'gate'), more],
        sub: `${detail ? `${cap(detail)}. ` : ''}Nothing was sent to ${row.destination}.` };
    }
    const labels = [...new Set(splitTerms(d.query || '', s.secrets).filter((g) => g.term).map((g) => g.term.label))];
    const where = row.component === 'reader' ? 'the reader model' : 'the search provider';
    const what = labels.length ? andList(labels) : row.rule;
    return { kind: 'leak', title: `Leak: ${what} sent to ${where}${more}`,
      sub: ['Rule ', el('span', { class: 'mono' }, row.rule), ` matched, but nothing enforced it. The request went to ${row.destination}.`] };
  }

  function renderIncident(sid, animate) {
    if (sid !== S.view) return;
    const box = $('#incident');
    const inc = incidentFor(sid);
    box.hidden = !inc;
    if (!inc) { box.replaceChildren(); return; }
    box.className = `incident t-console ${inc.kind}${animate ? ' enter' : ''}`;
    fill(box, [el('span', { class: 'incident-icon', 'aria-hidden': 'true' }, inc.kind === 'leak' ? '!' : '✕'),
      el('div', null, el('p', { class: 'incident-title' }, inc.title), el('p', { class: 'incident-sub' }, inc.sub))]);
  }

  // ---------- big counters (M11) ----------
  function setCounter(id, value, animate) {
    const box = $(id);
    const dd = box.querySelector('dd');
    const nums = dd.querySelectorAll('.num');
    const old = nums[nums.length - 1];
    const text = String(value);
    if (old && old.textContent === text) return;
    if (!animate || !old || reduceMotion.matches) {
      dd.replaceChildren(el('span', { class: 'num' }, text));
      return;
    }
    const fresh = el('span', { class: 'num' }, text);
    dd.append(fresh);
    old.animate([{ transform: 'translateY(0)', opacity: 1 }, { transform: 'translateY(-100%)', opacity: 0 }],
      { duration: 200, easing: EASE, fill: 'forwards' }).finished.then(() => old.remove(), () => {});
    fresh.animate([{ transform: 'translateY(100%)', opacity: 0 }, { transform: 'translateY(0)', opacity: 1 }],
      { duration: 200, easing: EASE, fill: 'backwards' });
  }

  function renderCounters(sid, animate) {
    if (sid !== S.view) return;
    const m = sid && S.sessions[sid] ? S.sessions[sid].m : { leaks: 0, blocked: 0, credits: 0, seconds: null };
    setCounter('#m-leaks', m.leaks, animate);
    setCounter('#m-blocked', m.blocked, animate);
    setCounter('#m-credits', m.credits, animate);
    setCounter('#m-seconds', m.seconds == null ? '—' : `${m.seconds} s`, false);
    $('#m-leaks').classList.toggle('hot', m.leaks > 0);
    $('#m-blocked').classList.toggle('hot', m.blocked > 0);
  }

  // ---------- answer bar ----------
  function renderAnswerBar(sid) {
    if (sid !== S.view) return;
    const s = sid ? S.sessions[sid] : null;
    const t = $('#answer-text');
    t.classList.remove('bad');
    $('#answer-bar').disabled = !(s && s.answer);
    if (s && s.answer) t.textContent = s.answer.text || '';
    else if (s && s.done) {
      t.textContent = `No answer. Run ended: ${window.RunView.outcomeText(s.done)}.`;
      t.classList.toggle('bad', s.done.outcome === 'leaked' || s.done.outcome === 'blocked');
    } else t.textContent = '—';
  }

  // ---------- Outbound panel (console theme): logic in outbound.js, numbers from the ledger events only ----------
  function renderOutbound(sid) {
    if (sid !== S.view) return;
    const s = sid ? S.sessions[sid] : null;
    const O = window.Outbound;
    if (!O) return;
    const sum = O.summarize(s ? s.rows : []);
    const rows = sum.attempts.map((a) => {
      const leak = a.decision === 'sent' && O.isSecretRule(a.rule);
      const cls = `ob-row ${a.decision}${leak ? ' leak' : ''}`;
      return el('tr', { class: cls },
        el('td', { class: 'mono' }, a.time),
        el('td', { class: 'mono ob-host', title: a.host }, a.host),
        el('td', null, O.kindLabel(a.kind)),
        el('td', null, el('span', { class: `ob-decision ${a.decision}${leak ? ' leak' : ''}` }, a.decision === 'blocked' ? 'Blocked' : 'Sent')),
        el('td', null, a.rule
          ? el('span', { class: `ob-rule mono${a.decision === 'blocked' || leak ? ' bad' : ''}`, title: a.detail || a.rule }, a.rule)
          : el('span', { class: 'ob-none' }, '—')));
    });
    fill($('#ob-rows'), rows.length ? rows : el('tr', { class: 'ob-empty' }, el('td', { colspan: '5' }, 'No outbound attempts yet.')));
    fill($('#ob-run'), sid ? el('span', { class: 'mono' }, sid) : []);
    $('#ob-summary').textContent = O.summaryText(sum);
    const c = O.check(sum);
    const line = $('#ob-check');
    // Only the verdict carries red (yes) or green (no); notes such as a block stay neutral.
    fill(line, [el('span', { class: 'ob-verdict' }, c.verdictText),
      c.notes.length ? el('span', { class: 'ob-notes' }, ` ${c.notes.join(' ')}`) : null]);
    line.className = `ob-check ${c.verdict}`;
    const sc = $('#ob-scroll');
    sc.scrollTop = sc.scrollHeight;   // the newest attempt is always in view
  }

  // ---------- step strip: the run's step from existing events only (ui/runview.js) ----------
  function renderSteps(sid) {
    if (sid !== S.view) return;
    const step = sid && S.sessions[sid] ? S.sessions[sid].step : 0;
    document.querySelectorAll('#steps li').forEach((li) => {
      const n = Number(li.dataset.step);
      li.classList.toggle('done', step > 0 && n < step);
      if (n === step) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
    });
  }

  // Everything that describes one run follows the ledger: answer bar, counters, badge, gate header, Outbound, steps.
  function showRunSummary(sid, animate = false) {
    renderSteps(sid);
    renderAnswerBar(sid);
    renderOutbound(sid);
    renderCounters(sid, animate);
    renderBadge();
    renderGateHead();
    renderIncident(sid, false);
    // The Planner room follows the same run: its dossier and its typed facts (proof beats included).
    if (sid && S.sessions[sid] && S.sessions[sid].memo) renderMemo(sid);
    renderTyped(sid);
  }

  // ---------- dossier memo ----------
  function memoTerms(sid) {
    const s = session(sid);
    const terms = [...s.secrets];
    if (s.canary) terms.push({ text: s.canary, label: 'canary' });
    return terms;
  }

  // Secrets are replaced before anything reaches the DOM: a bar carries only its label (shown on hover),
  // padded with figure spaces to the secret's length. canaryOnly: the single agent's clear copy, where only
  // the canary is hidden. The canary is never rendered anywhere.
  function redacted(text, sid, canaryOnly = false) {
    const s = session(sid);
    const terms = canaryOnly ? (s.canary ? [{ text: s.canary, label: 'canary' }] : []) : memoTerms(sid);
    return splitTerms(text, terms, true).map((seg) => (seg.term
      ? el('button', { type: 'button', class: 'redact', 'data-label': seg.term.label, 'aria-label': `hidden: ${seg.term.label}` },
        seg.term.label.padEnd(seg.text.length, '\u2007'))
      : seg.text));
  }

  // The memo as a paper dossier: typewriter header, ink stamp, marker redactions (DESIGN.md "Materials").
  function dossier(sid, redact) {
    const s = session(sid);
    const subject = s.title || '—';
    return el('article', { class: 'paper', 'aria-label': 'Confidential memo' },
      el('p', { class: 'tw t-classic' }, 'FILE 1984', s.sha ? `  ·  SHA ${shortHash(s.sha)}` : ''),
      el('p', { class: 'tw t-classic' }, 'SUBJECT: ', redacted(subject, sid, !redact)),
      el('div', { class: 'stamp-row t-classic' }, el('span', { class: 'confidential' }, 'CONFIDENTIAL')),
      el('div', { class: 'doc-head t-console' },
        el('p', { class: 'doc-name' }, 'Deal memo'),
        el('p', { class: 'doc-meta', title: redact ? 'Hover a bar to see what kind of secret it hides' : '' }, redact ? 'Redacted on screen' : 'Shown in full',
          s.sha ? [' · sha ', el('span', { class: 'mono', title: s.sha }, shortHash(s.sha))] : '')),
      el('div', { class: 'memo' }, redacted(s.memo, sid, !redact)));
  }

  function renderMemo(sid = S.view) {
    // Nothing is rendered until parties_confirmed says what to redact (memo_loaded arrives first).
    if (!sid || !session(sid).memo || !session(sid).secretsReady) return;
    fill($('#dossier'), dossier(sid, true));
    // The single agent holds the memo in the clear (canary still hidden); outside that layout it is not in the DOM.
    if (S.uiMode === 'single') fill($('#agent-dossier'), dossier(sid, false));
    else fill($('#agent-dossier'), waiting('waiting for the memo'));
  }

  // ---------- typed facts: what the Planner receives, as receipt chips ----------
  function typedNode(d, animate) {
    return el('li', { class: animate ? 'fade' : '' },
      el('div', { class: 'tneed' }, dual(`${d.need} · ${d.found ? 'found' : 'not found'}`,
        [el('span', { class: 'mono' }, d.need), el('span', { class: 'ichip' }, d.found ? 'Found' : 'Not found')])),
      el('div', { class: 'chips' }, (d.values || []).map((v) => el('div', { class: 'chip' },
        el('div', { class: 'chip-top' }, el('span', { class: 'chip-num' }, String(v.value)), el('span', { class: 'chip-unit' }, v.unit)),
        el('div', { class: 'chip-foot' }, `${v.period || '—'} · ${v.result_id}`)))));
  }

  function renderTyped(sid) {
    const s = sid && S.sessions[sid];
    if (!s || s.typed.length === 0) {
      fill($('#typed'), el('li', null, waiting('no numbers yet')));
      return;
    }
    fill($('#typed'), s.typed.map((d) => typedNode(d, false)));
  }

  // ---------- ledger ----------
  function typedQuery(text, sid, animate, flash) {
    const secrets = S.sessions[sid] ? S.sessions[sid].secrets : [];
    const segs = splitTerms(text, secrets);
    if (!animate) {
      return segs.map((seg) => (seg.term ? el('mark', { class: 'secret', title: `confirmed secret: ${seg.term.label}` }, seg.text) : seg.text));
    }
    let i = 0;
    const chars = (s) => [...s].map((c) => el('span', { class: 'ch', style: `--i:${i++}` }, c));
    return segs.map((seg) => (seg.term
      ? el('mark', { class: `secret${flash ? ' flash' : ''}`, title: `confirmed secret: ${seg.term.label}`, style: `--i:${i}` }, chars(seg.text))
      : chars(seg.text)));
  }

  // FORMATS §10 (run_done): leaks count only allowed attempts whose rule is `canary` (exact) or starts with
  // `secret.` or `provenance.`; `shape.*` and `gate.*` don't count.
  function isLeakRule(rule) {
    return typeof rule === 'string' && (rule === 'canary' || rule.startsWith('secret.') || rule.startsWith('provenance.'));
  }

  // blocked | leak | noted (allowed, a non-leak rule recorded) | allowed | result
  function rowKind(row) {
    if (row.row_type !== 'attempt') return 'result';
    if (row.decision === 'blocked') return 'blocked';
    if (row.rule == null) return 'allowed';
    return isLeakRule(row.rule) ? 'leak' : 'noted';
  }

  function rowNode(entry, sid, animate) {
    const { row, display } = entry;
    const kind = rowKind(row);
    const li = el('li', { class: `row ${kind === 'result' ? 'result' : 'attempt'}`, 'data-seq': row.seq });
    if (animate) {
      li.classList.add('enter');
      if (kind === 'blocked') li.style.cssText = `--red-at:${T.blockRed}ms;--stamp-at:${T.blockStamp}ms`;
      else if (kind === 'leak') li.style.cssText = `--red-at:${T.leakStamp}ms;--stamp-at:${T.leakStamp}ms`;
    }

    if (kind !== 'result') {
      if (kind === 'blocked') li.classList.add('blocked');
      if (kind === 'leak') li.classList.add('leak');
      const mark = kind === 'blocked'
        ? el('span', { class: 'mark bad t-classic' }, '✕ BLOCKED')
        : kind === 'leak' ? el('span', { class: 'mark bad t-classic' }, '✕ LEAKED') : el('span', { class: 'mark ok t-classic', 'aria-label': 'allowed' }, '✓');
      const status = { blocked: 'Blocked', leak: 'Leaked' }[kind] || 'Allowed';
      li.append(el('div', { class: 'line1' },
        el('span', { class: 'pslot', 'aria-hidden': 'true' }),
        el('span', { class: 'seq t-classic' }, pad2(row.seq)),
        el('span', { class: 'time t-console', title: row.time || '' }, (row.time || '').slice(11, 19)),
        el('span', { class: 'kind t-classic' }, row.kind),
        el('span', { class: `ichip agent t-console ${row.component || ''}` }, cap(row.component || row.kind || '')),
        el('span', { class: 'dest', title: row.destination }, dual(shortDest(row.destination), row.destination)),
        mark,
        el('span', { class: `status t-console ${kind === 'leak' || kind === 'blocked' ? kind : 'allowed'}` }, status)));
      const d = display || {};
      if (d.query) {
        const n = [...d.query].length;
        const q = el('div', { class: `q query indent${animate ? ' typing' : ''}` },
          el('span', { class: 't-classic' }, '"'), el('span', null, typedQuery(d.query, sid, animate, kind === 'leak')), el('span', { class: 't-classic' }, '"'));
        if (animate) q.style.setProperty('--step', `${Math.min(25, T.typeMax / Math.max(1, n)).toFixed(2)}ms`);
        li.append(q);
      } else if (d.summary || d.label) li.append(el('div', { class: 'q summary indent' }, dual(d.summary || d.label, cap(d.summary || d.label))));
      const detail = (entry.blockedInfo && entry.blockedInfo.detail) || d.detail;
      if (row.rule && kind === 'noted') {
        // Allowed, and a non-leak rule fired (shape.*, gate.*): recorded, never red, never counted.
        li.append(el('div', { class: 'rule noted indent' },
          dual([`rule ${row.rule} · recorded, not a leak`, detail ? el('span', { class: 'detail' }, ` · ${detail}`) : null],
            [el('span', { class: 'ichip rule-chip mono' }, row.rule), el('span', { class: 'detail' }, `Recorded, not a leak${detail ? ` · ${detail}` : ''}`)])));
      } else if (row.rule) {
        li.append(el('div', { class: 'rule indent' },
          dual([`rule ${row.rule}`, detail ? el('span', { class: 'detail' }, ` · ${detail}`) : null],
            [el('span', { class: 'ichip rule-chip mono' }, row.rule), detail ? el('span', { class: 'detail' }, cap(detail)) : null])));
      }
      if (kind === 'blocked' || kind === 'leak') li.append(el('div', { class: 'indent t-classic' }, el('span', { class: 'stamp' }, kind === 'blocked' ? 'BLOCKED' : 'LEAKED')));
      if (entry.blockedInfo && entry.blockedInfo.planted) li.append(plantedTag());
      // Receipt footer (1984 theme): the hash, the bytes and the time, under a tear line.
      li.append(el('div', { class: 'slip-foot t-classic' },
        el('span', { class: 'hash', title: row.hash }, `#${shortHash(row.hash)}`),
        el('span', null, `${row.bytes != null ? `${row.bytes} B · ` : ''}${(row.time || '').slice(11, 19)}`)));
    } else {
      const bits = [row.status === 'sent' ? String(row.http_status ?? '') : row.status];
      if (row.credits_used != null) bits.push(`${row.credits_used} credit${row.credits_used === 1 ? '' : 's'}`);
      li.append(el('div', { class: 'line1' },
        el('span', { class: 'pslot', 'aria-hidden': 'true' }),
        el('span', { class: 'seq t-classic' }, pad2(row.seq)),
        el('span', { class: 'dest' }, dual(`↳ ${bits.filter(Boolean).join(' · ')}`, `↳ Response ${bits.filter(Boolean).join(' · ')}`)),
        el('span', { class: 'hash', title: row.hash }, dual(shortHash(row.hash), ['row ', pad2(row.seq), ' · ', el('span', { class: 'mono' }, shortHash(row.hash))]))));
    }
    return li;
  }

  const plantedTag = () => el('div', { class: 'indent' }, el('span', { class: 'tag' }, dual('planted test query', 'Planted test query')));

  function scrollLedger() {
    const sc = $('#ledger-scroll');
    sc.scrollTop = sc.scrollHeight;
  }

  function renderLedger(sid) {
    S.view = sid;
    const s = S.sessions[sid];
    const nodes = s ? s.rows.map((e) => rowNode(e, sid, false)) : [];
    fill($('#ledger'), nodes);
    $('#ledger-empty').hidden = nodes.length > 0;
    showRunSummary(sid, false);
    scrollLedger();
  }

  // ---------- packets (M1, M2, M3, M5) ----------
  function sourceRoom(component) {
    if (component === 'reader') return { node: $('#reader'), side: 'right' };
    if (S.uiMode === 'single') return { node: $('#agent'), side: 'left' };
    return { node: $('#planner'), side: 'left' };
  }

  function launchPacket(li, row, kind) {
    const { node: room, side } = sourceRoom(row.component);
    const gate = $('#gate').getBoundingClientRect();
    const exit = $('#exit').getBoundingClientRect();
    const rr = room && room.offsetParent ? room.getBoundingClientRect() : null;
    const lr = li.getBoundingClientRect();
    const y0 = Math.min(Math.max(lr.top + 10, gate.top + 40), gate.bottom - 30);
    const x0 = rr ? (side === 'left' ? rr.right - 40 : rr.left + 28) : (side === 'left' ? gate.left - 40 : gate.right + 28);
    const xIn = side === 'left' ? gate.left + 18 : gate.right - 30;
    const xMid = gate.left + gate.width / 2 - 6;
    const yStop = exit.bottom + 6;
    const yOut = exit.top - 36;
    const at = (x, y) => `translate(${Math.round(x)}px, ${Math.round(y)}px)`;

    const red = el('span', { class: 'pk-red' });
    const p = el('div', { class: 'packet' }, red);
    $('#fx').append(p);

    let frames;
    let duration;
    if (kind === 'blocked') {
      // Slide in, rise, stop under the door, shake, fade where it stopped.
      duration = 850;
      const o = (ms) => ms / duration;
      frames = [
        { transform: at(x0, y0), opacity: 1, offset: 0, easing: EASE },
        { transform: at(xIn, y0), opacity: 1, offset: o(200), easing: EASE },
        { transform: at(xMid, yStop), opacity: 1, offset: o(400), easing: EASE },
        { transform: at(xMid - 8, yStop), offset: o(440), easing: EASE },
        { transform: at(xMid + 8, yStop), offset: o(480), easing: EASE },
        { transform: at(xMid - 6, yStop), offset: o(525), easing: EASE },
        { transform: at(xMid + 6, yStop), offset: o(565), easing: EASE },
        { transform: at(xMid - 3, yStop), offset: o(610), easing: EASE },
        { transform: at(xMid, yStop), opacity: 1, offset: o(650), easing: EASE },
        { transform: at(xMid, yStop), opacity: 0, offset: 1 },
      ];
      red.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 150, delay: 400, easing: EASE, fill: 'both' });
    } else {
      // Slide in, rise through the door and leave.
      duration = 600;
      const o = (ms) => ms / duration;
      frames = [
        { transform: at(x0, y0), opacity: 1, offset: 0, easing: EASE },
        { transform: at(xIn, y0), opacity: 1, offset: o(200), easing: EASE },
        { transform: at(xMid, exit.top + 4), opacity: 1, offset: o(400), easing: EASE },
        { transform: at(xMid, yOut), opacity: 0, offset: 1 },
      ];
      if (kind === 'leak') red.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 150, delay: 300, easing: EASE, fill: 'both' });
    }
    p.animate(frames, { duration, fill: 'both' }).finished.then(() => p.remove(), () => p.remove());
  }

  function flashExit() {
    const exit = $('#exit');
    exit.classList.remove('flash');
    void exit.offsetWidth;   // restart the CSS animation
    exit.classList.add('flash');
  }

  // ---------- reader room and web ----------
  function excerptNodes(text, highlights) {
    const terms = (highlights || []).map((h) => ({ text: h.text, label: h.label }));
    return splitTerms(text, terms).map((seg) => (seg.term ? el('mark', { class: 'planted' }, seg.text) : seg.text));
  }

  function splitUrl(url) {
    try {
      const u = new URL(url);
      return { host: u.host, path: `${u.pathname}${u.search}` };
    } catch (_) {
      return { host: url || '', path: '' };
    }
  }

  // A web page as a mini browser window: tab, address bar, then the page (DESIGN.md "Materials").
  function docNode(doc, animate) {
    const hl = doc.highlights || [];
    const { host, path } = splitUrl(doc.url);
    return el('article', { class: `browser${hl.length ? ' has-planted' : ''}${animate ? ' fade' : ''}`, 'aria-label': `Web page ${doc.result_id}` },
      el('div', { class: 'tabbar' },
        el('span', { class: 'tab', title: doc.title }, `${doc.result_id} · ${doc.title}`)),
      el('div', { class: 'addr' },
        el('span', { class: 'dots t-console', 'aria-hidden': 'true' }, el('i'), el('i'), el('i')),
        el('span', { class: 'nav t-classic', 'aria-hidden': 'true' }, '‹ › ↻'),
        el('span', { class: 'field', title: doc.url }, el('b', null, host), path)),
      el('div', { class: 'page' },
        el('div', { class: 'doc-title' }, doc.title, el('span', { class: 'mono rid t-console' }, ` ${doc.result_id}`)),
        // Excerpts can be up to 2,000 characters (FORMATS §3): they scroll inside the window.
        el('p', { class: 'doc-excerpt', tabindex: '0', role: 'region', 'aria-label': `Text of ${doc.result_id}` },
          excerptNodes(doc.excerpt || '', hl)),
        hl.map((h) => el('p', { class: `planted-label${animate ? ' fade-late' : ''}` },
          dual(`▲ ${h.label}`, [el('span', { class: 'planted-icon', 'aria-hidden': 'true' }, '!'),
            el('span', null, el('span', { class: 'planted-title' }, 'Hidden instruction in page'),
              el('span', { class: 'planted-note' }, 'Planted for this demo. The reader holds no secret to send.'))])))));
  }

  function jobNode(d, animate) {
    const body = el('div', { class: 'job-body' }, (d.docs || []).map((doc) => docNode(doc, animate)), el('div', { class: 'claims' }));
    const job = el('section', { class: 'job', 'data-job': d.job || '', 'data-docs': (d.docs || []).length });
    const head = el('button', {
      type: 'button',
      class: 'job-head',
      'aria-expanded': 'true',
      onclick: () => {
        const c = job.classList.toggle('collapsed');
        head.setAttribute('aria-expanded', String(!c));
      },
    }, dual(`${d.job || 'web'} · query `, [el('span', { class: 'ichip mono' }, d.job || 'web'), ' Search ']),
    el('span', { class: 'pq' }, dual(`"${d.public_query}"`, d.public_query)),
    el('span', { class: 'job-summary' }, ` · ${(d.docs || []).length} documents read`));
    job.append(head, body);
    return job;
  }

  function collapseJobs(container) {
    container.querySelectorAll('.job').forEach((j) => {
      j.classList.add('collapsed');
      j.querySelector('.job-head').setAttribute('aria-expanded', 'false');
    });
  }

  // ---------- proof ----------
  function clearWalk() {
    walkTimers.forEach(clearTimeout);
    walkTimers = [];
  }

  function setProofOpen(open) {
    S.proofOpen = open;
    $('#main').classList.toggle('proof-open', open);
  }

  function renderProofStatic(sid) {
    fill($('#proof-session'), sid ? dual(`session ${sid}`, ['Session ', el('span', { class: 'mono' }, sid)]) : dual('no session yet', 'No session yet'));
    fill($('#proof-run'), sid ? runLabel(sid) : []);
    $('#proof-cmd').textContent = `python3 proof/verify.py bundles/${sid || '<session_id>'}.json`;
  }

  function showVerdict(d, animate) {
    const slot = $('#verdict');
    const fp = typeof d.signer_key_sha256 === 'string' && /^[0-9a-f]{64}$/.test(d.signer_key_sha256) ? d.signer_key_sha256 : null;
    const reason = d.reason ? cap(String(d.reason).replace(/_/g, ' ')) : 'Chain broken';
    if (d.valid) {
      fill(slot, [
        el('div', { class: 't-classic' }, el('div', { class: `verdict valid${animate ? ' fade' : ''}` }, 'VALID'),
          el('p', { class: 'verdict-why' }, `${d.rows_checked} rows checked`)),
        el('div', { class: `banner-ok t-console${animate ? ' pop' : ''}`, role: 'status' },
          el('span', { class: 'b-icon', 'aria-hidden': 'true' }, '✓'),
          el('div', null, el('p', { class: 'b-title' }, `Verified · ${d.rows_checked} rows`,
            fp ? [' · signer ', el('span', { class: 'mono', title: fp }, fp.slice(0, 16))] : ''),
          el('p', { class: 'b-sub' }, 'Every row hashes into the next and the chain ends at the bundle head.')))]);
    } else {
      fill(slot, [
        el('div', { class: 't-classic' }, el('div', { class: `verdict invalid${animate ? ' fade' : ''}` }, 'INVALID'),
          el('p', { class: 'verdict-why bad' }, `row ${d.broken_at_seq} · ${d.reason}`)),
        el('div', { class: `banner-bad t-console${animate ? ' pop' : ''}`, role: 'alert' },
          el('span', { class: 'b-icon', 'aria-hidden': 'true' }, '✕'),
          el('div', null, el('p', { class: 'b-title' }, `Integrity check failed at row ${d.broken_at_seq}`),
            el('p', { class: 'b-sub' }, `${reason}. Row ${d.broken_at_seq} and every row after it no longer match the chain.`)))]);
    }
  }

  function walkProof(d, animate) {
    clearWalk();
    const sc = $('#ledger-scroll');
    const rows = [...document.querySelectorAll('#ledger li.row')]
      .sort((a, b) => Number(a.dataset.seq) - Number(b.dataset.seq));
    rows.forEach((li) => {
      li.classList.remove('p-ok', 'broken', 'tampered');
      li.querySelector('.pslot').textContent = '';
      li.querySelectorAll('.tampered-tag').forEach((t) => t.closest('.indent').remove());
      li.querySelectorAll('.broken-badge').forEach((t) => t.remove());
    });
    fill($('#verdict'), waiting('checking the chain'));

    const broken = d.valid ? null : d.broken_at_seq;
    const good = rows.filter((li) => (broken == null ? Number(li.dataset.seq) <= d.rows_checked : Number(li.dataset.seq) < broken));
    const bad = broken == null ? [] : rows.filter((li) => Number(li.dataset.seq) >= broken);

    const markGood = (li) => {
      li.classList.add('p-ok');
      const p = li.querySelector('.pslot');
      p.textContent = '✓';
      if (animate) p.classList.add('fade');
    };
    const markBad = (li) => {
      li.classList.add('broken');
      li.querySelector('.pslot').textContent = '✕';
      li.querySelector('.line1').append(el('span', { class: 'status broken-badge t-console' }, 'Broken'));
      if (d.tampered && Number(li.dataset.seq) === d.tampered_seq) {
        li.classList.add('tampered');
        li.insertBefore(el('div', { class: 'indent' }, el('span', { class: 'tag tampered-tag' }, dual('1 byte edited', 'One byte edited'))),
          li.querySelector('.slip-foot'));
      }
    };

    if (!animate) {
      good.forEach(markGood);
      bad.forEach(markBad);
      if (bad.length) scrollWithin(sc, bad[0], 'start');
      showVerdict(d, false);
      return;
    }
    const step = good.length ? Math.min(classic() ? 80 : 40, 1200 / good.length) : 0;
    good.forEach((li, i) => walkTimers.push(setTimeout(() => { markGood(li); scrollWithin(sc, li); }, i * step)));
    let t = good.length * step;
    const badStep = bad.length ? Math.min(40, 600 / bad.length) : 0;
    bad.forEach((li, i) => walkTimers.push(setTimeout(() => { markBad(li); if (i === 0) scrollWithin(sc, li, 'start'); }, t + i * badStep)));
    t += bad.length * badStep;
    walkTimers.push(setTimeout(() => showVerdict(d, true), t));
  }

  // ---------- answer sheet ----------
  function renderSheet() {
    const sheet = $('#sheet');
    const s = S.view && S.sessions[S.view];
    const a = s && s.answer;
    if (!a) { sheet.replaceChildren(); return; }
    const needs = (a.needs || []).map((n) => {
      const h = n.headline;
      return el('section', { class: 'need' },
        el('h3', null, `${n.need} · ${n.status}`),
        h ? el('p', { class: 'headline' }, `${fmtValue(h.value, h.unit)}${h.period ? `  ${h.period}` : ''}  ${h.method || ''}`) : null,
        (n.items || []).map((it) => el('div', { class: 'item' },
          el('div', { class: 'num' }, fmtValue(it.value, it.unit)),
          el('div', null,
            el('div', null, `${it.subject}${it.period ? ` · ${it.period}` : ''}`),
            el('div', { class: 'quote' }, `“${it.quote}”`),
            el('div', { class: 'src' }, `${it.source.result_id}  ${it.source.title}  ${it.source.url}`)))));
    });
    fill(sheet, [
      el('div', { class: 'sheet-head' },
        el('h2', { id: 'sheet-title' }, 'Answer'),
        el('span', { class: 'spacer' }),
        el('button', { type: 'button', onclick: () => toggleSheet(false) }, 'Close')),
      el('p', { class: 'question' }, a.question),
      needs]);
  }

  function toggleSheet(force) {
    const sheet = $('#sheet');
    const open = force ?? !sheet.classList.contains('open');
    const s = S.view && S.sessions[S.view];
    if (open && !(s && s.answer)) { toast('No answer yet.'); return; }
    if (open) renderSheet();
    sheet.classList.toggle('open', open);
    if (open) sheet.querySelector('button').focus();
  }

  // ---------- results screen ----------
  async function fetchJSON(url) {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return r.json();
  }

  // Results (FORMATS §9). Measured numbers come only from /shared/results/results.json. There is no silent fallback:
  // example data is loaded only when the URL says ?example=1, and then every number is labelled as example data.
  const EXAMPLE_MODE = params.get('example') === '1';
  let resultsState = 'loading';   // 'measured' | 'example' | 'missing' | 'not-measured' | 'error'
  let resultsError = '';

  async function loadResults() {
    results = null;
    resultsError = '';
    if (EXAMPLE_MODE) {
      try {
        results = await fetchJSON(RESULTS_EXAMPLE);
        resultsSource = RESULTS_EXAMPLE;
        resultsState = 'example';
      } catch (e) {
        resultsState = 'error';
        resultsError = String(e.message || e);
      }
      return;
    }
    try {
      const r = await fetch(RESULTS_REAL, { cache: 'no-store' });
      if (r.status === 404) { resultsState = 'missing'; return; }
      if (!r.ok) throw new Error(`${RESULTS_REAL}: HTTP ${r.status}`);
      const data = await r.json();
      resultsSource = RESULTS_REAL;
      // A results.json that is itself marked as example data is not a measurement either.
      if (data && data.example) { resultsState = 'not-measured'; return; }
      results = data;
      resultsState = 'measured';
    } catch (e) {
      resultsState = 'error';
      resultsError = String(e.message || e);
    }
  }

  function renderNoResults(box) {
    const why = {
      loading: 'The results file is still loading.',
      missing: `${RESULTS_REAL} does not exist yet. Measured numbers appear here once the red-team run writes it.`,
      'not-measured': `${RESULTS_REAL} is marked as example data, so it is not shown as a measurement.`,
      error: `The results file could not be read: ${resultsError}.`,
    }[resultsState] || 'No results file.';
    fill(box, [
      el('div', { class: 'no-results' },
        el('h2', { id: 'results-title', class: 'results-title' }, 'No measured results yet'),
        el('p', { class: 'no-results-why' }, why),
        el('p', { class: 'smallprint' }, 'To preview the layout with example data, open the page with ',
          el('code', null, '?example=1'), '. Every number is then labelled as example data.'))]);
  }

  function renderResults() {
    const box = $('#results');
    const usable = results && Array.isArray(results.runs) && results.runs.length > 0;
    if (!usable || (resultsState !== 'measured' && resultsState !== 'example')) {
      renderNoResults(box);
      return;
    }
    // Which run feeds which number is decided by the data (ui/results.js), never by position in runs[].
    window.Results.render(box, results, { example: resultsState === 'example', source: resultsSource });
  }

  function setScreen(screen) {
    const box = $('#results');
    const open = screen === 'results';
    if (open) renderResults();
    box.classList.toggle('open', open);
  }

  // ---------- empty rooms ----------
  function setEmptyRooms() {
    fill($('#dossier'), waiting('waiting for the memo'));
    fill($('#agent-dossier'), waiting('waiting for the memo'));
    fill($('#typed'), el('li', null, waiting('no numbers yet')));
    fill($('#agent-web'), waiting('waiting for web text'));
    fill($('#reader-body'), waiting('waiting for web text'));
    $('#ledger').replaceChildren();
    $('#ledger-empty').hidden = false;
  }

  // ---------- dispatcher ----------
  const handlers = {
    run_started(env) {
      const d = env.data;
      const sid = env.session_id;
      const s = session(sid);
      Object.assign(s, { rows: [], typed: [], typedKeys: new Set(), urls: {}, mode: d.mode, source: d.source, careless: !!d.plant_careless, answer: null, done: null, step: 0,
        m: { leaks: 0, blocked: 0, credits: 0, seconds: null } });
      S.current = sid;
      S.fakeDest = null;
      setRunBusy(true);    // Run button loader on until this run's run_done
      clearWalk();
      clearFx();
      if (LIVE) hideTitle();
      setProofOpen(false);
      setEmptyRooms();
      $('#sheet').classList.remove('open');
      setUiMode(SINGLE_MODES.has(d.mode) ? 'single' : 'dt');
      setEye(!$('#eye').classList.contains('closed'), false);
      renderLedger(sid);   // clears the ledger panel and shows this run's (empty) answer and counters
    },

    memo_loaded(env) {
      const s = session(env.session_id);
      s.canary = env.data.canary || null;
      s.memo = env.data.text || '';
      s.title = env.data.title || '';
      s.sha = env.data.sha256 || '';
      if (env.session_id === S.current) renderMemo();
    },

    parties_confirmed(env) {
      const s = session(env.session_id);
      s.secrets = [];
      for (const g of env.data.confirmed_secrets || []) {
        for (const v of g.values || []) s.secrets.push({ text: v, label: g.label });
      }
      s.secretsReady = true;
      if (env.session_id === S.current) renderMemo();
    },

    ledger_row(env, o) {
      const sid = env.session_id;
      const s = session(sid);
      const entry = { row: env.data.row, display: env.data.display, credits: env.data.credits_used, blockedInfo: null };
      s.rows.push(entry);
      const row = entry.row;
      const kind = rowKind(row);
      if (kind === 'blocked') s.m.blocked += 1;
      if (kind === 'leak') s.m.leaks += 1;
      if (typeof entry.credits === 'number') s.m.credits += entry.credits;
      if (sid === S.current && row.destination && row.destination.startsWith('127.0.0.1') && S.fakeDest !== row.destination) {
        S.fakeDest = row.destination;
        renderGateHead();
      }
      if (sid !== S.view) return;

      const animate = animOK(o);
      const li = rowNode(entry, sid, !(o && o.instant));
      $('#ledger').append(li);
      $('#ledger-empty').hidden = true;
      scrollLedger();

      // The moment: packet, red wall flash, stamp, counter tick, eye. None of it delays the replay.
      if (animate && kind !== 'result') launchPacket(li, row, kind);
      // The Outbound panel changes with the counters, so a leak or a block never shows there before its moment.
      if (kind === 'blocked') {
        if (animate) {
          later(flashExit, 0);
          later(() => { renderCounters(sid, true); renderOutbound(sid); }, T.blockStamp);
          later(() => renderIncident(sid, true), T.blockRed);
        } else { renderCounters(sid, false); renderIncident(sid, false); renderOutbound(sid); }
      } else if (kind === 'leak') {
        if (animate) {
          later(() => { renderCounters(sid, true); setEye(true, true); renderIncident(sid, true); renderOutbound(sid); }, T.leakStamp);
        } else { renderCounters(sid, false); setEye(true, true); renderIncident(sid, false); renderOutbound(sid); }
      } else {
        renderCounters(sid, animate);
        renderOutbound(sid);
      }
    },

    blocked(env, o) {
      const sid = env.session_id;
      const s = session(sid);
      const entry = s.rows.find((e) => e.row.row_type === 'attempt' && e.row.seq === env.data.ledger_seq);
      if (!entry) return;
      entry.blockedInfo = env.data;
      if (sid !== S.view) return;
      // Update the row in place, so its running animation is not restarted.
      const li = document.querySelector(`#ledger li.attempt[data-seq="${env.data.ledger_seq}"]`);
      if (!li) return;
      if (env.data.detail && !li.querySelector('.rule .detail')) {
        const [c1984, cConsole] = li.querySelectorAll('.rule > span');
        if (c1984) c1984.append(el('span', { class: 'detail' }, ` · ${env.data.detail}`));
        if (cConsole) cConsole.append(el('span', { class: 'detail' }, cap(env.data.detail)));
      }
      if (env.data.planted && !li.querySelector('.tag')) li.insertBefore(plantedTag(), li.querySelector('.slip-foot'));
      renderIncident(sid, false);
      if (o && o.instant) { scrollLedger(); renderOutbound(sid); }   // animated: the block moment redraws it
    },

    docs_read(env, o) {
      // result_id -> url for this session (FORMATS §4: ids are per session), used to dedupe typed facts.
      const urls = session(env.session_id).urls;
      for (const doc of env.data.docs || []) urls[doc.result_id] = doc.url;
      if (env.session_id !== S.current) return;
      const d = env.data;
      const target = d.by === 'baseline' ? $('#agent-web') : $('#reader-body');
      target.querySelectorAll('.waiting').forEach((n) => n.remove());
      collapseJobs(target);
      const node = jobNode(d, !(o && o.instant));
      target.append(node);
      const planted = node.querySelector('mark.planted');
      // Show the poisoned page from its tab and address bar down, and bring the planted line into its text box.
      scrollWithin(target, planted ? planted.closest('.browser') : node, 'start');
      if (planted) scrollWithin(planted.closest('.doc-excerpt'), planted, 'nearest');
    },

    reader_claims(env) {
      if (env.session_id !== S.current) return;
      const d = env.data;
      const job = [...document.querySelectorAll('#reader-body .job')].find((j) => j.dataset.job === d.job);
      if (!job) return;
      const box = job.querySelector('.claims');
      const kept = d.kept || [];
      const dropped = d.dropped || [];
      fill(box, [
        el('h3', { class: 'label' }, `Claims kept ${kept.length} · dropped ${dropped.length}`),
        kept.map((c) => el('div', { class: 'claim' },
          el('span', { class: 'v' }, fmtValue(c.value, c.unit)), `  ${c.period || ''}  ${c.document_id}`,
          el('div', { class: 'cq' }, `“${c.quote}”`))),
        dropped.map((c) => el('div', { class: 'claim dropped' }, `${c.document_id} ${c.claim_type} dropped: ${c.reason}`))]);
      // The count comes from this job's docs_read event, not from the DOM.
      job.querySelector('.job-summary').textContent = ` · ${job.dataset.docs} documents read, ${kept.length} claims kept`;
    },

    planner_typed(env, o) {
      const s = session(env.session_id);
      // A need asked twice repeats its facts, sometimes under a new result id for the same page.
      // Keep each (need, value, unit, period, source url) once per run; there is no fact id.
      const fresh = (env.data.values || []).filter((v) => {
        const k = JSON.stringify([env.data.need, v.value, v.unit, v.period, s.urls[v.result_id] || v.result_id]);
        if (s.typedKeys.has(k)) return false;
        s.typedKeys.add(k);
        return true;
      });
      const needKey = JSON.stringify([env.data.need, env.data.found]);
      if (fresh.length === 0 && s.typedKeys.has(needKey)) return;
      s.typedKeys.add(needKey);
      env = { ...env, data: { ...env.data, values: fresh } };
      s.typed.push(env.data);
      if (env.session_id !== S.view) return;
      const list = $('#typed');
      list.querySelectorAll('.waiting').forEach((n) => n.closest('li').remove());
      const li = typedNode(env.data, !(o && o.instant));
      list.append(li);
      scrollWithin($('#planner-low'), li);
    },

    answer(env) {
      const s = session(env.session_id);
      s.answer = env.data;
      renderAnswerBar(env.session_id);
    },

    run_done(env) {
      const d = env.data;
      const s = session(env.session_id);
      s.done = d;
      s.m = { leaks: d.leaks, blocked: d.blocked, credits: d.credits_total, seconds: d.seconds };
      S.lastDone = env.session_id;
      if (env.session_id === S.current) setRunBusy(false);   // the run the button is waiting for has finished
      renderCounters(env.session_id, false);
      renderAnswerBar(env.session_id);
      renderGateHead();
      renderProofStatic(S.lastDone);
    },

    proof_result(env, o) {
      const sid = env.session_id;
      const d = env.data;
      setProofOpen(true);
      // One story on screen: ledger, answer bar and counters all switch to the verified run.
      if (S.view !== sid && S.sessions[sid]) renderLedger(sid);
      renderProofStatic(sid);
      $('#proof-head').textContent = shortHash(d.bundle_head);
      $('#proof-head').title = d.bundle_head;
      $('#proof-rows').textContent = String(d.rows_checked);
      // Signer key fingerprint (FORMATS §8, §10): first 16 hex like the verifier prints, full value on hover.
      const fp = typeof d.signer_key_sha256 === 'string' && /^[0-9a-f]{64}$/.test(d.signer_key_sha256) ? d.signer_key_sha256 : null;
      $('#proof-signer-row').hidden = !fp;
      $('#proof-signer').textContent = fp ? `${fp.slice(0, 16)}…` : '';
      $('#proof-signer').title = fp || '';
      if (d.tampered_seq != null) $('#tamper-seq').value = d.tampered_seq;
      walkProof(d, animOK(o));
    },

    beat(env) {
      S.beat = env.data;
      setScreen(env.data.screen);
      renderReplayStatus();
    },
  };

  function dispatch(env, o = { instant: false }) {
    const h = handlers[env.type];
    if (!h) { console.warn('unknown event type', env.type, env); return; }
    try { h(env, o); } catch (e) { console.error('handler failed', env.type, e); }
    // The step strip moves on event types the run already emits (run_started resets the step to 0 first).
    if (env.session_id && window.RunView) {
      const s = session(env.session_id);
      const step = window.RunView.stepAfter(env.type, s.step);
      if (step !== s.step) { s.step = step; renderSteps(env.session_id); }
    }
  }

  // ---------- replay engine ----------
  const R = { events: [], i: 0, base: 0, startedAt: 0, playing: false, raf: 0 };

  function replayNow() { return R.playing ? R.base + (performance.now() - R.startedAt) : R.base; }

  function renderReplayStatus() {
    if (LIVE) return;
    const end = R.i >= R.events.length && R.events.length > 0;
    const icon = end ? '■' : R.playing ? '▶' : '❚❚';
    const st = $('#replay-status');
    st.textContent = `Replay ${icon} ${fmtClock(replayNow())}`;
    st.title = S.beat ? `${S.beat.at} ${S.beat.title}` : '';
  }

  function tick() {
    const t = replayNow();
    while (R.i < R.events.length && R.events[R.i].t_ms <= t) dispatch(R.events[R.i++], { instant: false });
    if (R.i >= R.events.length && R.playing) pause();
    renderReplayStatus();
    if (R.playing) R.raf = requestAnimationFrame(tick);
  }

  function play() {
    if (R.i >= R.events.length) restart();
    hideTitle();
    R.startedAt = performance.now();
    R.playing = true;
    cancelAnimationFrame(R.raf);
    R.raf = requestAnimationFrame(tick);
  }

  function pause() {
    R.base = replayNow();
    R.playing = false;
    cancelAnimationFrame(R.raf);
    renderReplayStatus();
  }

  function resetView() {
    clearWalk();
    clearFx();
    S = freshState();
    setProofOpen(false);
    setEmptyRooms();
    fill($('#verdict'), el('p', { class: 'empty' }, 'Not verified yet. Press Verify proof.'));
    $('#proof-head').textContent = '—';
    $('#proof-rows').textContent = '—';
    $('#proof-signer-row').hidden = true;
    $('#sheet').classList.remove('open');
    $('#exit').classList.remove('flash');
    setScreen('main');
    setUiMode('dt');
    setEye(false, false);
    showRunSummary(null, false);
    renderProofStatic(null);
  }

  function seek(ms) {
    const wasPlaying = R.playing;
    if (wasPlaying) pause();
    resetView();
    setRunBusy(false);   // re-dispatching below turns it back on if the new position is mid-run
    R.i = 0;
    while (R.i < R.events.length && R.events[R.i].t_ms <= ms) dispatch(R.events[R.i++], { instant: true });
    R.base = ms;
    renderReplayStatus();
    if (wasPlaying) play();
  }

  function restart() {
    pause();
    seek(0);
    showTitle();
  }

  function nextBeat() {
    hideTitle();
    let j = R.i;
    while (j < R.events.length && R.events[j].type !== 'beat') j += 1;
    if (j >= R.events.length) { toast('Last beat reached. Press R to restart.'); return; }
    while (R.i <= j) dispatch(R.events[R.i++], { instant: true });
    R.base = R.events[j].t_ms;
    R.startedAt = performance.now();
    renderReplayStatus();
  }

  async function startReplay() {
    let text;
    try {
      const r = await fetch(FIXTURE, { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      text = await r.text();
    } catch (e) {
      hideTitle();
      toast(`Could not load ${FIXTURE}. Serve the repo root: python -m http.server 8703 --bind 127.0.0.1`);
      return;
    }
    R.events = text.split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l)).sort((a, b) => a.seq - b.seq);
    const at = Number(params.get('at'));
    const start = Number.isFinite(at) && at > 0 ? at : 0;
    seek(start);
    if (start > 0 || params.get('title') === '0') hideTitle();
    if (params.get('open') === 'answer') toggleSheet(true);
    if (params.has('freeze')) {
      // Dispatch the events of the next 100ms with animation, then pin all animations at <freeze> ms.
      FREEZE = Number(params.get('freeze')) || 0;
      const until = start + 100;
      while (R.i < R.events.length && R.events[R.i].t_ms <= until) dispatch(R.events[R.i++], { instant: false });
      R.base = until;
      renderReplayStatus();
      requestAnimationFrame(() => document.getAnimations().forEach((a) => { a.pause(); a.currentTime = FREEZE; }));
      return;
    }
    if (params.get('play') === '1') play();
  }

  function recordedProof(tampered) {
    return R.events.find((e) => e.type === 'proof_result' && !!e.data.tampered === tampered);
  }

  // ---------- live ----------
  function startLive() {
    if (params.get('title') === '0') hideTitle();
    const es = new EventSource(`/events?token=${encodeURIComponent(TOKEN)}`);
    es.onopen = () => toast('Live: connected.');
    es.onmessage = (m) => {
      let env;
      try { env = JSON.parse(m.data); } catch (_) { console.warn('bad frame', m.data); return; }
      dispatch(env, { instant: false });
    };
    es.onerror = () => toast('Live stream lost. Showing the last state. Reconnecting…');
  }

  async function api(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-DT-Token': TOKEN },
      body: JSON.stringify(body),
    });
    let j = null;
    try { j = await r.json(); } catch (_) { /* no body */ }
    if (!r.ok) throw new Error((j && (j.detail || j.error)) || `HTTP ${r.status}`);
    return j;
  }

  const targetSession = () => S.lastDone || S.current;

  // ---------- Run button loader ----------
  // POST /api/run only STARTS a run; the run ends when its run_done event arrives on /events (FORMATS §10, §11).
  // So the button shows "running" from the click (and from any run_started, which also covers a page reload or SSE
  // reconnect mid-run) until run_done. Live: the button is disabled meanwhile, since the app refuses a second run
  // with 409. Replay: the band still shows while a scripted run plays, but the button stays clickable (Run restarts
  // the replay). The moving band is CSS (#run.is-running::after), transform only, and still under reduced motion.
  const RUN_WATCHDOG_MS = 10 * 60 * 1000;   // safety net if run_done never arrives (stream lost for good)
  let runWatchdog = null;

  function setRunBusy(on) {
    const b = $('#run');
    if (!b) return;
    b.classList.toggle('is-running', on);
    b.setAttribute('aria-busy', on ? 'true' : 'false');
    b.textContent = on ? 'Running…' : 'Run';
    b.disabled = LIVE && on;
    clearTimeout(runWatchdog);
    runWatchdog = null;
    if (on && LIVE) runWatchdog = setTimeout(() => setRunBusy(false), RUN_WATCHDOG_MS);
  }

  // ---------- controls ----------
  async function onRun() {
    hideTitle();
    if (!LIVE) { restart(); hideTitle(); play(); return; }
    const single = S.uiMode === 'single';
    const body = {
      mode: single ? 'compromised' : 'doublethink',
      source: single ? 'fake' : $('#source').value,
      plant_careless: single ? false : $('#careless').checked,
    };
    setRunBusy(true);   // immediately on click, before the request returns
    try {
      const j = await api('/api/run', body);
      toast(`Run started: ${j && j.session_id ? j.session_id : body.mode}.`);
    } catch (e) {
      // If a run is already going (its run_started arrived, its run_done not yet), keep the loader: that run_done
      // clears it. Otherwise this run never started, so clear the loader at once.
      const cur = S.current && S.sessions[S.current];
      if (!(cur && !cur.done)) setRunBusy(false);
      toast(`Run failed: ${e.message}`);
    }
  }

  async function onVerify() {
    hideTitle();
    setProofOpen(true);
    if (!LIVE) {
      const ev = recordedProof(false);
      if (ev) dispatch(ev); else toast('No recorded verify result in the replay file.');
      return;
    }
    const sid = targetSession();
    if (!sid) { toast('Run something first.'); return; }
    try { await api('/api/verify', { session_id: sid }); } catch (e) { toast(`Verify failed: ${e.message}`); }
  }

  async function onTamper() {
    setProofOpen(true);
    if (!LIVE) {
      const ev = recordedProof(true);
      if (ev) dispatch(ev); else toast('No recorded tamper result in the replay file.');
      return;
    }
    const sid = targetSession();
    const seq = Number($('#tamper-seq').value);
    if (!sid) { toast('Run something first.'); return; }
    if (!Number.isInteger(seq) || seq < 1) { toast('Pick a row number of 1 or more.'); return; }
    try { await api('/api/tamper', { session_id: sid, seq }); } catch (e) { toast(`Tamper failed: ${e.message}`); }
  }

  function onBundle() {
    if (!LIVE) { toast('Download bundle is available in live mode.'); return; }
    const sid = targetSession();
    if (!sid) { toast('Run something first.'); return; }
    window.location.href = `/api/bundle?session_id=${encodeURIComponent(sid)}&token=${encodeURIComponent(TOKEN)}`;
  }

  function toggleProof() {
    setProofOpen(!S.proofOpen);
    // Closing the proof panel brings the latest run back on screen.
    if (!S.proofOpen && S.current && S.view !== S.current) renderLedger(S.current);
  }

  function toggleResults() {
    setScreen($('#results').classList.contains('open') ? 'main' : 'results');
  }

  $('#mode-single').addEventListener('click', () => setUiMode('single'));
  $('#mode-dt').addEventListener('click', () => setUiMode('dt'));
  $('#run').addEventListener('click', onRun);
  $('#verify').addEventListener('click', onVerify);
  $('#proof-verify').addEventListener('click', onVerify);
  $('#proof-tamper').addEventListener('click', onTamper);
  $('#proof-bundle').addEventListener('click', onBundle);
  $('#answer-bar').addEventListener('click', () => toggleSheet(true));
  $('#title').addEventListener('click', () => { if (LIVE) hideTitle(); else play(); });

  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const tag = (e.target && e.target.tagName) || '';
    if (e.key === 'Escape') {
      toggleSheet(false);
      $('#results').classList.remove('open');
      return;
    }
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
    if (LIVE && titleShown()) { hideTitle(); return; }
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    const replayOnly = (fn) => { if (!LIVE) fn(); };
    switch (k) {
      case ' ': e.preventDefault(); replayOnly(() => (R.playing ? pause() : play())); break;
      case 'ArrowRight': e.preventDefault(); replayOnly(nextBeat); break;
      case 'r': replayOnly(restart); break;
      case '1': setUiMode('single'); break;
      case '2': setUiMode('dt'); break;
      case 'v': toggleProof(); break;
      case 'a': toggleSheet(); break;
      case 's': toggleResults(); break;
      case 't': applyTheme(classic() ? 'console' : '1984'); toast(classic() ? 'Theme: 1984. Press T for the console theme.' : 'Theme: console. Press T for the 1984 theme.'); break;
      default: return;
    }
  });

  // ---------- boot ----------
  S = freshState();
  resetView();
  if (!(Number(params.get('at')) > 0) && params.get('title') !== '0') showTitle();
  loadResults().then(() => {
    if ($('#results').classList.contains('open')) renderResults();
    if (LIVE) startLive(); else startReplay();
  });
})();
