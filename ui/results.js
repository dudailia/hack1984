// Doublethink UI: the results screen. Which run each number comes from is decided by the data, never by position.
//
// shared/results/results.json (FORMATS §9) keeps every run in time order and never deletes one. Rules:
//   1. A run scored with the fallback judge is never shown: its `leak_judge` (or `judge`) text says FALLBACK.
//   2. Leak bars: only runs scored by the frozen detector (`detector.matches_checks_frozen` true). For each mode,
//      the most recent such run that has that mode.
//   3. False blocks, usefulness and cost: the most recent non-fallback run that carries the figure. These runs
//      (benign-frozen, usefulness) judge no leaks, so they have no detector field and need none.
//   4. Every figure names its run (label, place in the file, commit). Runs that feed nothing are listed as not shown.
//   5. The 40 attacks were measured on the corporate deal memo: the block is labelled "First evaluation, corporate deal
//      memo". The real estate scenario is a demo, not a measurement: a run tagged real estate (`scenario` field, or a
//      label starting "re-" or containing "real estate") never feeds a number on this screen.
// With ?example=1 the example file has no judge or detector fields; its runs are accepted (unless they say FALLBACK)
// and every number carries the example label.
'use strict';

(function (root) {
  const MODES = [
    ['single_agent', 'single agent'],
    ['compromised', 'compromised agent'],
    ['two_minds', 'two minds'],
    ['doublethink', 'two minds + gate'],
  ];
  const EXAMPLE_LABEL = 'EXAMPLE DATA, not measured';

  const judgeText = (run) => String((run && (run.leak_judge != null ? run.leak_judge : run.judge)) || '');
  const isFallback = (run) => /fallback/i.test(judgeText(run));
  const isFrozen = (run) => !!(run && run.detector && run.detector.matches_checks_frozen === true);

  const RE_SCENARIO = /^real[\s_-]?estate$/i;
  function scenarioOf(run) {
    if (!run) return 'corporate';
    if (typeof run.scenario === 'string' && RE_SCENARIO.test(run.scenario.trim())) return 'real_estate';
    const label = String(run.label || '').toLowerCase();
    return label.startsWith('re-') || /real[\s-]estate/.test(label) ? 'real_estate' : 'corporate';
  }

  const FIRST_EVAL = 'First evaluation, corporate deal memo';

  // Pure: which run feeds each mode and each extra figure.
  function select(data, opts) {
    const example = !!(opts && opts.example);
    const all = (data && Array.isArray(data.runs) ? data.runs : []).map((run, i) => ({ run, index: i }));
    const corporate = all.filter((r) => r.run && scenarioOf(r.run) === 'corporate' && !isFallback(r.run));
    const leakRuns = corporate.filter((r) => example || isFrozen(r.run));
    const latestIn = (list, pick) => {
      for (let i = list.length - 1; i >= 0; i -= 1) {
        const v = pick(list[i].run);
        if (v != null) return { value: v, index: list[i].index, run: list[i].run };
      }
      return null;
    };
    const modes = MODES.map(([key, label]) => {
      const hit = latestIn(leakRuns, (run) => {
        const m = run.modes && run.modes[key];
        return m && typeof m.runs === 'number' && m.runs > 0 ? m : null;
      });
      return { key, label, value: hit ? hit.value : null, index: hit ? hit.index : null, run: hit ? hit.run : null };
    });
    const cost = (k) => (run) => (run.cost && run.cost[k] != null ? run.cost[k] : null);
    const figures = {
      falseBlocks: latestIn(corporate, (run) => run.false_blocks || null),
      usefulness: latestIn(corporate, (run) => run.usefulness || null),
      secondsPerQuestion: latestIn(corporate, cost('seconds_per_question')),
      creditsPerQuestion: latestIn(corporate, cost('tavily_credits_per_question')),
    };
    const used = new Set([...modes.map((m) => m.index), ...Object.values(figures).map((h) => h && h.index)].filter((i) => i != null));
    const reasonOf = (run) => {
      if (!run) return 'empty';
      if (scenarioOf(run) === 'real_estate') return 'real estate scenario: a demo, not a measurement';
      if (isFallback(run)) return 'scored with the fallback judge';
      if (run.modes && !isFrozen(run) && !example) return 'not scored by the frozen detector';
      return 'superseded by a later run';
    };
    return {
      total: all.length,
      modes,
      ...figures,
      excluded: all.filter((r) => !used.has(r.index)).map((r) => ({ index: r.index, label: r.run && r.run.label, reason: reasonOf(r.run) })),
    };
  }

  // "run 2 of 3, “checks-frozen rejudged-frozen”, commit 486a8b6"
  function runName(index, run, total) {
    const bits = [`run ${index + 1} of ${total}`];
    if (run && run.label) bits.push(`“${run.label}”`);
    if (run && run.commit) bits.push(`commit ${run.commit}`);
    return bits.join(', ');
  }

  function el(tag, props, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') n.className = v; else if (k === 'style') n.style.cssText = v; else n.setAttribute(k, v === true ? '' : String(v));
    }
    for (const c of kids.flat(Infinity)) if (c != null && c !== false) n.append(c instanceof Node ? c : String(c));
    return n;
  }

  // Render the measured (or ?example=1) screen into box. Every number goes through num(), so in example mode each one
  // carries the example label.
  function render(box, data, opts) {
    const example = !!(opts && opts.example);
    const source = (opts && opts.source) || '';
    const short = (h) => (h ? `${String(h).slice(0, 4)}…${String(h).slice(-4)}` : '');
    const num = (text, cls) => el('span', { class: `num-val${cls ? ` ${cls}` : ''}`, 'data-num': '' }, text,
      example ? el('span', { class: 'example-tag' }, EXAMPLE_LABEL) : null);
    const sel = select(data, { example });

    // Bars plus "Where each number comes from".
    function block() {
      const grid = el('div', { class: 'bars' });
      for (const m of sel.modes) {
        const track = el('div', { class: 'track', 'aria-hidden': 'true' });
        if (m.value) {
          const f = el('div', { class: 'fill' });
          f.style.width = `${(100 * m.value.leaked) / m.value.runs}%`;
          track.append(f);
        }
        grid.append(el('div', { class: 'bl' }, m.label), track,
          el('div', { class: 'bv', 'data-mode': m.key, 'data-run': m.index == null ? '' : String(m.index) },
            m.value ? num(`${m.value.leaked} / ${m.value.runs}`) : 'not measured'));
      }
      const groups = [];
      for (const m of sel.modes) {
        if (m.index == null) continue;
        let g = groups.find((x) => x.index === m.index);
        if (!g) { g = { index: m.index, run: m.run, labels: [] }; groups.push(g); }
        g.labels.push(m.label);
      }
      const missing = sel.modes.filter((m) => m.index == null).map((m) => m.label);
      const sources = el('ul', { class: 'run-sources' },
        groups.map((g) => el('li', { 'data-run': String(g.index) },
          el('strong', null, g.labels.join(', ')), `: ${runName(g.index, g.run, sel.total)}`)),
        missing.length ? el('li', null, el('strong', null, missing.join(', ')), ': no run scored by the frozen detector') : null,
        sel.excluded.length ? el('li', { class: 'run-excluded' },
          `Not shown: ${sel.excluded.map((x) => `run ${x.index + 1} of ${sel.total} (${x.reason})`).join('; ')}.`) : null);
      return [
        el('p', { class: 'smallprint', style: 'margin:0 0 0.75rem' }, 'Leaks per setup'),
        grid,
        el('p', { class: 'smallprint run-sources-title' }, 'Where each number comes from'),
        sources,
      ];
    }

    const fb = sel.falseBlocks;
    const u = sel.usefulness;
    const from = (hit) => (hit ? el('span', { class: 'run-from' }, ` (${runName(hit.index, hit.run, sel.total)})`) : null);
    const nm = (hit) => (hit ? num(String(hit.value)) : 'not measured');
    const byRule = fb && fb.value.by_rule ? Object.entries(fb.value.by_rule).map(([k, v]) => `${k} ${v}`).join(', ') : '';

    box.classList.toggle('is-example', example);
    box.replaceChildren(...[
      example ? el('div', { class: 'example-banner', role: 'note' }, EXAMPLE_LABEL,
        el('span', { class: 'example-banner-sub' }, `Loaded because the URL has ?example=1, from ${source}.`)) : null,
      el('p', { class: 'eval-label', 'data-scenario': 'corporate' }, FIRST_EVAL),
      el('h2', { id: 'results-title', class: 'results-title' },
        num(String(data.attacks_total), 'big'), ' attacks, written and hashed before the code.'),
      el('p', { class: 'sha' }, `attack file sha256 ${short(data.attack_file_sha256)}`),
      el('div', { class: 'headline-eval', 'data-scenario': 'corporate' }, block()),
      fb ? el('p', { class: 'fb' }, 'False blocks on normal questions: ',
        num(`${fb.value.blocked} / ${fb.value.total}`, fb.value.blocked > 0 ? 'bad' : ''),
        byRule ? el('span', { class: 'smallprint' }, `  ${byRule}`) : null, from(fb))
        : el('p', { class: 'smallprint' }, 'False blocks on normal questions: not measured'),
      u ? el('p', { class: 'smallprint' }, 'answered with a cited number ',
        num(`${u.value.answered_with_cited_number} / ${u.value.total}`), from(u)) : null,
      el('p', { class: 'smallprint' }, 'Tavily credits per question ', nm(sel.creditsPerQuestion), from(sel.creditsPerQuestion),
        ' · seconds per question ', nm(sel.secondsPerQuestion), from(sel.secondsPerQuestion)),
      el('p', { class: 'smallprint' }, `from ${source}`),
    ].filter(Boolean));
    return sel;
  }

  root.Results = Object.freeze({ select, scenarioOf, render, FIRST_EVAL, isFallback, isFrozen, EXAMPLE_LABEL, MODES });
})(typeof window !== 'undefined' ? window : globalThis);
