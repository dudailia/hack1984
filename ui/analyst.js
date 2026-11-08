// Doublethink UI: the Analyst view's logic. Pure functions, no DOM, no network.
// Everything comes from events the app already emits (FORMATS §10): run_started, memo_loaded, parties_confirmed,
// ledger_row, answer and proof_result. No new event fields.
'use strict';

(function (root) {
  const MAX_QUESTION = 500;   // app/run.py MAX_QUESTION: /api/run refuses longer questions

  // Which run the Analyst view shows. runs: [{sid, mode, source, careless, order}] in start order.
  // Replay: the doublethink run that best stands for "the analyst's research": real source and not the planted
  // careless run first, then fake and not careless, then any doublethink run; the latest within a rank wins.
  // Live: the latest doublethink run (the one the analyst just asked for).
  function pickRun(runs, live) {
    const dt = (runs || []).filter((r) => r && r.mode === 'doublethink');
    if (!dt.length) return null;
    const latest = (list) => list.reduce((a, b) => ((b.order ?? 0) >= (a.order ?? 0) ? b : a));
    if (live) return latest(dt).sid;
    const ranks = [
      (r) => r.source === 'real' && !r.careless,
      (r) => !r.careless,
      () => true,
    ];
    for (const ok of ranks) {
      const hit = dt.filter(ok);
      if (hit.length) return latest(hit).sid;
    }
    return null;
  }

  // The Analyst view shows the last genuine verification of the run. A tamper result (proof_result.tampered: true)
  // checks an edited copy of the bundle, not the run's log, so it is shown only in the Audit view.
  function lastGenuine(proofs) {
    const list = (proofs || []).filter((p) => p && !p.tampered);
    return list.length ? list[list.length - 1] : null;
  }

  // "Verified" only when the run's latest genuine proof_result is VALID.
  function verified(proofs) {
    const p = lastGenuine(proofs);
    return !!p && p.valid === true;
  }

  // The body for POST /api/run from the Analyst question box (FORMATS §11). Throws on an empty or too long question.
  function runRequest(question, source) {
    const q = String(question == null ? '' : question).trim();
    if (!q) throw new Error('Type a research question first.');
    if (q.length > MAX_QUESTION) throw new Error(`Keep the question under ${MAX_QUESTION} characters.`);
    return { mode: 'doublethink', source: source === 'real' ? 'real' : 'fake', plant_careless: false, question: q };
  }

  // The answer event's numbers as one flat list, each with its quote and source (FORMATS §10 answer).
  function answerItems(answer) {
    const out = [];
    for (const n of (answer && answer.needs) || []) {
      for (const it of n.items || []) {
        const src = it.source || {};
        out.push({
          need: n.need, value: it.value, unit: it.unit, period: it.period || '', subject: it.subject || '',
          quote: it.quote || '', title: src.title || '', url: src.url || '', resultId: src.result_id || '',
        });
      }
    }
    return out;
  }

  // Remove every occurrence of the canary from a string (the canary is never rendered anywhere).
  function withoutCanary(text, canary) {
    const s = String(text == null ? '' : text);
    if (!canary) return s;
    return s.split(canary).join('').replace(/\s{2,}/g, ' ').trim();
  }

  root.Analyst = Object.freeze({ pickRun, verified, lastGenuine, runRequest, answerItems, withoutCanary, MAX_QUESTION });
})(typeof window !== 'undefined' ? window : globalThis);
