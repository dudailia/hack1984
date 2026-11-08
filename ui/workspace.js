// Doublethink UI: the plug-in prototype page (ui/workspace.html). It reads the same replay file as the page
// (?events=<name>.jsonl from /shared/fixtures/, same name rule as app.js) and shows the deal name from memo_loaded.
// No deal name is written in this file. The canary is never rendered.
'use strict';

(async () => {
  const params = new URLSearchParams(location.search);
  const evParam = params.get('events') || '';
  const EVENTS_NAME = /^[a-z0-9_-]+\.jsonl$/.test(evParam) ? evParam : 'demo_events.jsonl';
  const nameEl = document.getElementById('ws-deal-name');
  const link = document.getElementById('ws-research');

  // "Research safely" opens the Analyst view of the same replay.
  const target = new URLSearchParams({ view: 'analyst', title: '0' });
  if (EVENTS_NAME !== 'demo_events.jsonl') target.set('events', EVENTS_NAME);
  link.href = `index.html?${target.toString()}`;

  let events = [];
  try {
    const r = await fetch(`/shared/fixtures/${EVENTS_NAME}`, { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    events = (await r.text()).split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));
  } catch (e) {
    nameEl.textContent = 'Deal not available';
    return;
  }

  // The same run the Analyst view shows (window.Analyst.pickRun), and its memo title.
  const runs = events.filter((e) => e.type === 'run_started').map((e, i) => ({
    sid: e.session_id, mode: e.data && e.data.mode, source: e.data && e.data.source,
    careless: !!(e.data && e.data.plant_careless), order: e.seq ?? i,
  }));
  const sid = window.Analyst.pickRun(runs, false);
  const memo = events.find((e) => e.type === 'memo_loaded' && e.session_id === sid)
    || events.find((e) => e.type === 'memo_loaded');
  const title = memo && memo.data ? window.Analyst.withoutCanary(memo.data.title || '', memo.data.canary) : '';
  nameEl.textContent = title || 'Untitled deal';
  document.body.dataset.ready = '1';
})();
