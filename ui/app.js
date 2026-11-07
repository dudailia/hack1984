// Doublethink UI. Event names and fields: shared/FORMATS.md section 10. Design: ui/DESIGN.md.
// One dispatcher on env.type serves both the replay file and the live SSE stream.
// All data is put into the DOM with textContent, never innerHTML.
'use strict';

(() => {
  const $ = (sel) => document.querySelector(sel);

  function el(tag, props, ...kids) {
    const n = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v == null || v === false) continue;
        if (k === 'class') n.className = v;
        else if (k === 'text') n.textContent = v;
        else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
        else n.setAttribute(k, v === true ? '' : String(v));
      }
    }
    fill(n, kids, false);
    return n;
  }

  // Append (or replace with) children, flattening nested arrays and skipping null / false.
  function fill(n, kids, replace = true) {
    const list = [kids].flat(Infinity).filter((c) => c != null && c !== false)
      .map((c) => (c instanceof Node ? c : String(c)));
    if (replace) n.replaceChildren(...list); else n.append(...list);
    return n;
  }

  // ---------- configuration ----------
  const params = new URLSearchParams(location.search);
  const TOKEN = params.get('token');
  const LIVE = !!TOKEN && params.get('replay') !== '1';
  const FIXTURE = '/shared/fixtures/demo_events.jsonl';
  const RESULTS_REAL = '/shared/results/results.json';
  const RESULTS_EXAMPLE = '/shared/fixtures/results_example.json';
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  document.body.classList.add(LIVE ? 'live' : 'replay');

  const SINGLE_MODES = new Set(['single_agent', 'compromised']);
  const UNIT_SUFFIX = { percent: '%', multiple: 'x' };

  // ---------- state ----------
  let S;
  let walkTimers = [];
  let results = null;
  let resultsSource = null;

  function freshState() {
    return {
      sessions: {},          // session_id -> {rows: [entry], secrets: [], canary, mode, source}
      current: null,         // session of the latest run_started
      ledgerSession: null,   // session whose ledger is on screen
      lastDone: null,        // session of the latest run_done (target for Verify / Tamper / Bundle)
      mode: null,
      source: null,
      uiMode: 'dt',          // 'single' | 'dt'
      memo: '',
      fakeDest: null,
      leaks: 0, blocked: 0, credits: 0, seconds: null,
      answer: null,
      beat: null,
      proofOpen: false,
    };
  }

  function session(sid) {
    if (!S.sessions[sid]) S.sessions[sid] = { rows: [], secrets: [], canary: null, mode: null, source: null };
    return S.sessions[sid];
  }

  // ---------- helpers ----------
  const shortHash = (h) => (h ? `${h.slice(0, 4)}…${h.slice(-4)}` : '');
  const pad2 = (n) => String(n).padStart(2, '0');

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
  function splitTerms(text, terms) {
    const list = terms.filter((t) => t.text).sort((a, b) => b.text.length - a.text.length);
    const out = [];
    let buf = '';
    let i = 0;
    while (i < text.length) {
      const hit = list.find((t) => text.startsWith(t.text, i));
      if (hit) {
        if (buf) { out.push({ text: buf }); buf = ''; }
        out.push({ text: hit.text, term: hit });
        i += hit.text.length;
      } else {
        buf += text[i];
        i += 1;
      }
    }
    if (buf) out.push({ text: buf });
    return out;
  }

  function secretTerms(sid) {
    const s = S.sessions[sid];
    return s ? s.secrets : [];
  }

  function highlightSecrets(text, sid) {
    return splitTerms(text, secretTerms(sid)).map((seg) =>
      seg.term ? el('mark', { class: 'secret', title: `confirmed secret: ${seg.term.label}` }, seg.text) : seg.text);
  }

  let toastTimer = null;
  function toast(msg) {
    const t = $('#toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), 3200);
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
    renderGateHead();
  }

  function renderBadge() {
    const b = $('#badge');
    if (S.source === 'real') b.textContent = 'SOURCE: api.tavily.com (real)';
    else if (S.source === 'fake') b.textContent = 'SOURCE: LOCAL STAND-IN (fake)';
    else b.textContent = 'SOURCE: —';
    b.title = b.textContent;
  }

  function renderGateHead() {
    const single = S.uiMode === 'single';
    $('#gate-title').textContent = single ? 'Outbound' : 'The gate';
    let sub = 'only door out';
    if (single) sub = 'recorded, not enforced';
    else if (S.mode === 'two_minds') sub = 'recording only · not enforcing';
    $('#gate-sub').textContent = sub;

    const exit = $('#exit');
    exit.replaceChildren(el('span', { class: 'door' }, 'EXIT ▲'));
    const dests = [];
    if (S.source === 'real') dests.push('api.tavily.com');
    else if (S.source === 'fake') dests.push(S.fakeDest || '127.0.0.1 (local stand-in)');
    dests.push('api.anthropic.com (reader only)');
    for (const d of dests) exit.append(el('span', { class: 'dest' }, d));

    const sid = S.ledgerSession;
    const mode = sid && S.sessions[sid] ? S.sessions[sid].mode : null;
    $('#ledger-session').textContent = sid ? `ledger ${sid}${mode ? ` · ${mode}` : ''}` : '';
  }

  function renderMetrics() {
    const set = (id, v, hot) => {
      const n = $(id);
      n.querySelector('dd').textContent = v;
      n.classList.toggle('hot', !!hot);
    };
    set('#m-leaks', S.leaks, S.leaks > 0);
    set('#m-blocked', S.blocked, S.blocked > 0);
    set('#m-credits', S.credits, false);
    set('#m-seconds', S.seconds == null ? '— s' : `${S.seconds} s`, false);
  }

  function setEmptyHints() {
    const msg = LIVE ? 'Waiting for a run. Press Run.' : 'Waiting for a run. Press Space to play the replay.';
    document.querySelectorAll('[data-empty]').forEach((n) => { n.textContent = msg; });
  }

  // ---------- memo ----------
  function memoTerms(sid) {
    const s = session(sid);
    const terms = [...s.secrets];
    if (s.canary) terms.push({ text: s.canary, label: 'canary' });
    return terms;
  }

  function renderMemo() {
    const sid = S.current;
    if (!sid || !S.memo) return;
    const segs = splitTerms(S.memo, memoTerms(sid));
    // Planner room: secrets as redaction bars, revealed on hover or focus.
    $('#memo').replaceChildren(...segs.map((seg) => (seg.term
      ? el('button', { type: 'button', class: 'redact', 'data-label': seg.term.label, 'aria-label': `hidden: ${seg.term.label}` }, seg.text)
      : seg.text)));
    // One agent room: the single agent has the memo in the clear.
    $('#agent-memo').replaceChildren(S.memo);
  }

  // ---------- ledger ----------
  function rowNode(entry, sid, animate) {
    const { row, display } = entry;
    const isAttempt = row.row_type === 'attempt';
    const li = el('li', { class: `row ${isAttempt ? 'attempt' : 'result'}`, 'data-seq': row.seq });
    if (animate) li.classList.add('enter');

    if (isAttempt) {
      const blocked = row.decision === 'blocked';
      const leak = row.decision === 'allowed' && row.rule != null;
      if (blocked) li.classList.add('blocked');
      if (leak) li.classList.add('leak');
      const mark = blocked
        ? el('span', { class: 'mark bad' }, '✕ BLOCKED')
        : leak ? el('span', { class: 'mark bad' }, '✕ LEAKED') : el('span', { class: 'mark ok', 'aria-label': 'allowed' }, '✓');
      li.append(el('div', { class: 'line1' },
        el('span', { class: 'pslot', 'aria-hidden': 'true' }),
        el('span', { class: 'seq' }, pad2(row.seq)),
        el('span', { class: 'kind' }, row.kind),
        el('span', { class: 'dest', title: row.destination }, row.destination),
        el('span', { class: 'hash', title: row.hash }, shortHash(row.hash)),
        mark));
      const d = display || {};
      if (d.query) li.append(el('div', { class: 'q' }, '"', el('span', { class: 'quote' }, highlightSecrets(d.query, sid)), '"'));
      else if (d.summary || d.label) li.append(el('div', { class: 'q' }, d.summary || d.label));
      const detail = (entry.blockedInfo && entry.blockedInfo.detail) || d.detail;
      if (row.rule) li.append(el('div', { class: 'rule' }, `rule ${row.rule}`, detail ? el('span', { class: 'detail' }, ` · ${detail}`) : null));
      if (blocked || leak) li.append(el('div', null, el('span', { class: 'stamp' }, blocked ? 'BLOCKED' : 'LEAKED')));
      if (entry.blockedInfo && entry.blockedInfo.planted) li.append(el('div', { class: 'q' }, el('span', { class: 'tag' }, 'planted test query')));
    } else {
      const bits = [row.status === 'sent' ? String(row.http_status ?? '') : row.status];
      if (row.credits_used != null) bits.push(`${row.credits_used} credit${row.credits_used === 1 ? '' : 's'}`);
      li.append(el('div', { class: 'line1' },
        el('span', { class: 'pslot', 'aria-hidden': 'true' }),
        el('span', { class: 'seq' }, pad2(row.seq)),
        el('span', { class: 'dest' }, `↳ ${bits.filter(Boolean).join(' · ')}`),
        el('span', { class: 'hash', title: row.hash }, shortHash(row.hash))));
    }
    return li;
  }

  function scrollLedger() {
    const sc = $('#ledger-scroll');
    sc.scrollTop = sc.scrollHeight;
  }

  function renderLedger(sid) {
    S.ledgerSession = sid;
    const s = S.sessions[sid];
    const nodes = s ? s.rows.map((e) => rowNode(e, sid, false)) : [];
    $('#ledger').replaceChildren(...nodes);
    $('#ledger-empty').hidden = nodes.length > 0;
    renderGateHead();
    scrollLedger();
  }

  // ---------- reader room and web ----------
  function excerptNodes(text, highlights) {
    const terms = (highlights || []).map((h) => ({ text: h.text, label: h.label }));
    return splitTerms(text, terms).map((seg) => (seg.term ? el('mark', { class: 'planted' }, seg.text) : seg.text));
  }

  function docNode(doc, animate) {
    const hl = doc.highlights || [];
    return el('article', { class: `doc${animate ? ' fade' : ''}` },
      el('div', { class: 'doc-title' }, `${doc.result_id}  ${doc.title}`),
      el('div', { class: 'doc-url' }, doc.url),
      el('p', { class: 'doc-excerpt' }, excerptNodes(doc.excerpt || '', hl)),
      hl.map((h) => el('p', { class: `planted-label${animate ? ' fade-late' : ''}` }, `▲ ${h.label}`)));
  }

  function jobNode(d, animate) {
    const body = el('div', { class: 'job-body' }, (d.docs || []).map((doc) => docNode(doc, animate)), el('div', { class: 'claims' }));
    const job = el('section', { class: 'job', 'data-job': d.job || '' });
    const head = el('button', { type: 'button', class: 'job-head', 'aria-expanded': 'true',
      onclick: () => {
        const c = job.classList.toggle('collapsed');
        head.setAttribute('aria-expanded', String(!c));
      } },
    `${d.job || 'web'} · query `, el('span', { class: 'pq' }, `"${d.public_query}"`),
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
    $('#proof-session').textContent = sid ? `session ${sid}` : 'no session yet';
    $('#proof-cmd').textContent = `python3 proof/verify.py bundles/${sid || '<session_id>'}.json`;
  }

  function showVerdict(d, animate) {
    const slot = $('#verdict');
    if (d.valid) {
      slot.replaceChildren(el('div', { class: `verdict valid${animate ? ' fade' : ''}` }, 'VALID'),
        el('p', { class: 'verdict-why' }, `${d.rows_checked} rows checked`));
    } else {
      slot.replaceChildren(el('div', { class: `verdict invalid${animate ? ' fade' : ''}` }, 'INVALID'),
        el('p', { class: 'verdict-why bad' }, `row ${d.broken_at_seq} · ${d.reason}`));
    }
  }

  function walkProof(d, animate) {
    clearWalk();
    const rows = [...document.querySelectorAll('#ledger li.row')]
      .sort((a, b) => Number(a.dataset.seq) - Number(b.dataset.seq));
    rows.forEach((li) => {
      li.classList.remove('p-ok', 'broken', 'tampered');
      li.querySelector('.pslot').textContent = '';
      const t = li.querySelector('.tampered-tag');
      if (t) t.parentNode.remove();
    });
    $('#verdict').replaceChildren(el('p', { class: 'empty' }, 'Checking the chain…'));

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
      if (d.tampered && Number(li.dataset.seq) === d.tampered_seq) {
        li.classList.add('tampered');
        li.append(el('div', { class: 'q' }, el('span', { class: 'tag tampered-tag' }, '1 byte edited')));
      }
    };

    if (!animate) {
      good.forEach(markGood);
      bad.forEach(markBad);
      showVerdict(d, false);
      return;
    }
    const step = good.length ? Math.min(80, 1200 / good.length) : 0;
    good.forEach((li, i) => walkTimers.push(setTimeout(() => { markGood(li); li.scrollIntoView({ block: 'nearest' }); }, i * step)));
    let t = good.length * step;
    const badStep = bad.length ? Math.min(40, 600 / bad.length) : 0;
    bad.forEach((li, i) => walkTimers.push(setTimeout(() => { markBad(li); if (i === 0) li.scrollIntoView({ block: 'nearest' }); }, t + i * badStep)));
    t += bad.length * badStep;
    walkTimers.push(setTimeout(() => showVerdict(d, true), t));
  }

  // ---------- answer sheet ----------
  function renderSheet() {
    const sheet = $('#sheet');
    const a = S.answer;
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
    if (open && !S.answer) { toast('No answer yet.'); return; }
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

  async function loadResults() {
    try {
      results = await fetchJSON(RESULTS_REAL);
      resultsSource = RESULTS_REAL;
    } catch (_) {
      try {
        results = await fetchJSON(RESULTS_EXAMPLE);
        resultsSource = RESULTS_EXAMPLE;
      } catch (e) {
        results = null;
        resultsSource = String(e.message || e);
      }
    }
  }

  function renderResults() {
    const box = $('#results');
    if (!results || !Array.isArray(results.runs) || results.runs.length === 0) {
      box.replaceChildren(el('h2', { id: 'results-title', class: 'results-title' }, 'Results file not found.'),
        el('p', { class: 'smallprint' }, `Tried ${RESULTS_REAL} and ${RESULTS_EXAMPLE}.`));
      return;
    }
    const runs = results.runs;
    const run = runs[runs.length - 1];
    const frozen = runs.length > 1 ? runs[0] : null;
    const bars = [
      ['single agent', 'single_agent'],
      ['compromised agent', 'compromised'],
      ['two minds', 'two_minds'],
      ['two minds + gate', 'doublethink'],
    ];
    const grid = el('div', { class: 'bars' });
    for (const [label, key] of bars) {
      const m = (run.modes || {})[key];
      const track = el('div', { class: 'track', 'aria-hidden': 'true' });
      if (m && m.runs) {
        const fill = el('div', { class: 'fill' });
        fill.style.width = `${(100 * m.leaked) / m.runs}%`;
        track.append(fill);
        const f = frozen && (frozen.modes || {})[key];
        if (f && f.runs) {
          const tick = el('div', { class: 'tick' });
          tick.style.left = `${(100 * f.leaked) / f.runs}%`;
          track.append(tick);
        }
      }
      grid.append(el('div', { class: 'bl' }, label), track,
        el('div', { class: 'bv' }, m ? `${m.leaked} / ${m.runs}` : 'not run'));
    }
    const fb = run.false_blocks;
    const byRule = fb && fb.by_rule ? Object.entries(fb.by_rule).map(([k, v]) => `${k} ${v}`).join(', ') : '';
    const u = run.usefulness;
    const c = run.cost || {};
    const nm = (v) => (v == null ? 'not measured' : String(v));
    fill(box, [
      results.example ? el('div', { class: 'banner', role: 'note' }, results.banner || 'EXAMPLE DATA') : null,
      el('h2', { id: 'results-title', class: 'results-title' },
        el('span', { class: 'big' }, String(results.attacks_total)), 'attacks, written and hashed before the code.'),
      el('p', { class: 'sha' }, `attack file sha256 ${shortHash(results.attack_file_sha256)}`),
      el('p', { class: 'smallprint', style: 'margin:0 0 0.75rem' }, 'Leaks per setup'),
      grid,
      frozen ? el('p', { class: 'smallprint' }, `| = ${frozen.label} run`) : null,
      fb ? el('p', { class: 'fb' }, 'False blocks on normal questions: ',
        el('span', { class: fb.blocked > 0 ? 'bad' : '' }, `${fb.blocked} / ${fb.total}`),
        byRule ? el('span', { class: 'smallprint' }, `  ${byRule}`) : null) : null,
      el('p', { class: 'smallprint' },
        `run ${run.label} · commit ${run.commit} · planner ${run.planner_model} · source ${run.source}`),
      u ? el('p', { class: 'smallprint' }, `answered with a cited number ${u.answered_with_cited_number} / ${u.total}`) : null,
      el('p', { class: 'smallprint' },
        `Tavily credits per question ${nm(c.tavily_credits_per_question)} · seconds per question ${nm(c.seconds_per_question)}`),
      el('p', { class: 'smallprint' }, `from ${resultsSource}`)]);
  }

  function setScreen(screen) {
    const box = $('#results');
    const open = screen === 'results';
    if (open) renderResults();
    box.classList.toggle('open', open);
  }

  // ---------- dispatcher ----------
  const handlers = {
    run_started(env) {
      const d = env.data;
      const sid = env.session_id;
      const s = session(sid);
      s.rows = [];
      s.mode = d.mode;
      s.source = d.source;
      S.current = sid;
      S.mode = d.mode;
      S.source = d.source;
      S.fakeDest = null;
      S.memo = '';
      S.leaks = 0; S.blocked = 0; S.credits = 0; S.seconds = null;
      S.answer = null;
      clearWalk();
      $('#memo').replaceChildren();
      $('#agent-memo').replaceChildren();
      $('#typed').replaceChildren();
      $('#agent-web').replaceChildren();
      $('#reader-body').replaceChildren(el('p', { class: 'empty' }, 'No web text yet.'));
      $('#answer-text').textContent = '—';
      $('#answer-text').classList.remove('bad');
      $('#answer-bar').disabled = true;
      $('#sheet').classList.remove('open');
      setUiMode(SINGLE_MODES.has(d.mode) ? 'single' : 'dt');
      renderBadge();
      renderLedger(sid);   // clears the ledger panel
      renderMetrics();
    },

    memo_loaded(env) {
      const s = session(env.session_id);
      s.canary = env.data.canary || null;
      if (env.session_id === S.current) {
        S.memo = env.data.text || '';
        renderMemo();
      }
    },

    parties_confirmed(env) {
      const s = session(env.session_id);
      s.secrets = [];
      for (const g of env.data.confirmed_secrets || []) {
        for (const v of g.values || []) s.secrets.push({ text: v, label: g.label });
      }
      if (env.session_id === S.current) renderMemo();
    },

    ledger_row(env, o) {
      const sid = env.session_id;
      const entry = { row: env.data.row, display: env.data.display, credits: env.data.credits_used, blockedInfo: null };
      session(sid).rows.push(entry);
      const row = entry.row;
      if (sid === S.current) {
        if (row.row_type === 'attempt') {
          if (row.decision === 'blocked') S.blocked += 1;
          else if (row.rule != null) S.leaks += 1;
        }
        if (typeof entry.credits === 'number') S.credits += entry.credits;
        if (row.destination && row.destination.startsWith('127.0.0.1') && S.fakeDest !== row.destination) {
          S.fakeDest = row.destination;
          renderGateHead();
        }
        renderMetrics();
      }
      if (sid === S.ledgerSession) {
        $('#ledger').append(rowNode(entry, sid, !o.instant));
        $('#ledger-empty').hidden = true;
        scrollLedger();
      }
    },

    blocked(env, o) {
      const sid = env.session_id;
      const s = session(sid);
      const entry = s.rows.find((e) => e.row.row_type === 'attempt' && e.row.seq === env.data.ledger_seq);
      if (!entry) return;
      entry.blockedInfo = env.data;
      if (sid === S.ledgerSession) {
        const old = document.querySelector(`#ledger li.attempt[data-seq="${env.data.ledger_seq}"]`);
        const fresh = rowNode(entry, sid, !o.instant);
        if (old) old.replaceWith(fresh); else $('#ledger').append(fresh);
        scrollLedger();
      }
    },

    docs_read(env, o) {
      if (env.session_id !== S.current) return;
      const d = env.data;
      const target = d.by === 'baseline' ? $('#agent-web') : $('#reader-body');
      target.querySelectorAll('.empty').forEach((n) => n.remove());
      collapseJobs(target);
      const node = jobNode(d, !o.instant);
      target.append(node);
      const planted = node.querySelector('mark.planted');
      (planted || node).scrollIntoView({ block: planted ? 'center' : 'start' });
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
      job.querySelector('.job-summary').textContent = ` · ${job.querySelectorAll('.doc').length} documents read, ${kept.length} claims kept`;
    },

    planner_typed(env, o) {
      if (env.session_id !== S.current) return;
      const d = env.data;
      const vals = (d.values || []).map((v) => el('div', { class: 'val' }, `${v.value} ${v.unit}  ${v.period || '—'}  ${v.result_id}`));
      const li = el('li', { class: o.instant ? '' : 'fade' },
        el('div', { class: 'tneed' }, `${d.need}  ${d.found ? 'found' : 'not found'}`), vals);
      $('#typed').append(li);
      li.scrollIntoView({ block: 'nearest' });   // keep the newest typed facts in view under the memo
    },

    answer(env) {
      if (env.session_id !== S.current) return;
      S.answer = env.data;
      $('#answer-text').textContent = env.data.text || '';
      $('#answer-bar').disabled = false;
    },

    run_done(env) {
      const d = env.data;
      S.lastDone = env.session_id;
      if (env.session_id !== S.current) return;
      S.leaks = d.leaks; S.blocked = d.blocked; S.credits = d.credits_total; S.seconds = d.seconds;
      renderMetrics();
      if (!S.answer) {
        const t = $('#answer-text');
        t.textContent = `No answer. Run ended: ${d.outcome}.`;
        t.classList.toggle('bad', d.outcome === 'leaked' || d.outcome === 'blocked');
      }
      renderProofStatic(S.lastDone);
    },

    proof_result(env, o) {
      const sid = env.session_id;
      const d = env.data;
      setProofOpen(true);
      if (S.ledgerSession !== sid && S.sessions[sid]) renderLedger(sid);
      renderProofStatic(sid);
      $('#proof-head').textContent = shortHash(d.bundle_head);
      $('#proof-head').title = d.bundle_head;
      $('#proof-rows').textContent = String(d.rows_checked);
      if (d.tampered_seq != null) $('#tamper-seq').value = d.tampered_seq;
      walkProof(d, !o.instant && !reduceMotion.matches);
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
  }

  // ---------- replay engine ----------
  const R = { events: [], i: 0, base: 0, startedAt: 0, playing: false, raf: 0 };

  function replayNow() { return R.playing ? R.base + (performance.now() - R.startedAt) : R.base; }

  function renderReplayStatus() {
    if (LIVE) return;
    const end = R.i >= R.events.length && R.events.length > 0;
    const icon = end ? '■' : R.playing ? '▶' : '❚❚';
    const st = $('#replay-status');
    st.textContent = `REPLAY ${icon} ${fmtClock(replayNow())}`;
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
    S = freshState();
    setProofOpen(false);
    $('#ledger').replaceChildren();
    $('#ledger-empty').hidden = false;
    $('#memo').replaceChildren(el('p', { class: 'empty', 'data-empty': '' }));
    $('#agent-memo').replaceChildren(el('p', { class: 'empty', 'data-empty': '' }));
    $('#typed').replaceChildren();
    $('#agent-web').replaceChildren();
    $('#reader-body').replaceChildren(el('p', { class: 'empty' }, 'No web text yet.'));
    $('#verdict').replaceChildren(el('p', { class: 'empty' }, 'Not verified yet. Press Verify proof.'));
    $('#proof-head').textContent = '—';
    $('#proof-rows').textContent = '—';
    $('#answer-text').textContent = '—';
    $('#answer-bar').disabled = true;
    $('#sheet').classList.remove('open');
    setScreen('main');
    setUiMode('dt');
    renderBadge();
    renderMetrics();
    renderProofStatic(null);
    setEmptyHints();
  }

  function seek(ms) {
    const wasPlaying = R.playing;
    if (wasPlaying) pause();
    resetView();
    R.i = 0;
    while (R.i < R.events.length && R.events[R.i].t_ms <= ms) dispatch(R.events[R.i++], { instant: true });
    R.base = ms;
    renderReplayStatus();
    if (wasPlaying) play();
  }

  function restart() {
    pause();
    seek(0);
  }

  function nextBeat() {
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
      toast(`Could not load ${FIXTURE}. Serve the repo root: python -m http.server 8703 --bind 127.0.0.1`);
      return;
    }
    R.events = text.split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l)).sort((a, b) => a.seq - b.seq);
    const at = Number(params.get('at'));
    seek(Number.isFinite(at) && at > 0 ? at : 0);
    if (params.get('open') === 'answer') toggleSheet(true);
    if (params.get('play') === '1') play();
  }

  function recordedProof(tampered) {
    return R.events.find((e) => e.type === 'proof_result' && !!e.data.tampered === tampered);
  }

  // ---------- live ----------
  function startLive() {
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

  // ---------- controls ----------
  async function onRun() {
    if (!LIVE) { restart(); play(); return; }
    const single = S.uiMode === 'single';
    const body = {
      mode: single ? 'compromised' : 'doublethink',
      source: single ? 'fake' : $('#source').value,
      plant_careless: single ? false : $('#careless').checked,
    };
    try {
      const j = await api('/api/run', body);
      toast(`Run started: ${j && j.session_id ? j.session_id : body.mode}.`);
    } catch (e) { toast(`Run failed: ${e.message}`); }
  }

  async function onVerify() {
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
    if (!S.proofOpen && S.current && S.ledgerSession !== S.current) renderLedger(S.current);
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

  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const tag = (e.target && e.target.tagName) || '';
    if (e.key === 'Escape') {
      toggleSheet(false);
      $('#results').classList.remove('open');
      return;
    }
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
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
      default: return;
    }
  });

  // ---------- boot ----------
  S = freshState();
  resetView();
  loadResults().then(() => {
    if ($('#results').classList.contains('open')) renderResults();
    if (LIVE) startLive(); else startReplay();
  });
})();
