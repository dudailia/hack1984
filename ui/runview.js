// Run view helpers (pure, no DOM): the step strip and the outcome text. Loaded before app.js; tested by
// ui/tests/ui.test.html. Event names: shared/FORMATS.md section 10. No event fields are added for these.
'use strict';

(() => {
  // The four steps shown at the top of the run view, in order.
  const STEPS = [
    'Drop in the memo',
    'Confirm flagged names and figures',
    'Ask a research question',
    'Cited answer + signed log',
  ];

  // Which step an event moves its run to (FORMATS §10 order: run_started, memo_loaded, parties_confirmed, then the
  // research events, then answer and run_done). Only `answer` reaches step 4: a run that ends without one (leaked,
  // blocked, budget, error) stays on step 3, so the strip never claims a cited answer the run did not give.
  // Every other type keeps the step. A run never moves back.
  const STEP_OF = { run_started: 1, memo_loaded: 2, parties_confirmed: 3, answer: 4 };

  function stepAfter(type, prev) {
    const p = Number.isInteger(prev) ? prev : 0;
    return Object.prototype.hasOwnProperty.call(STEP_OF, type) ? Math.max(p, STEP_OF[type]) : p;
  }

  // run_done outcome, with run_done.data.reason (FORMATS §10: why the run failed, null when it did not) next to it
  // whenever the run gives one.
  function outcomeText(done) {
    if (!done || !done.outcome) return '';
    const reason = typeof done.reason === 'string' ? done.reason.trim() : '';
    return reason ? `${done.outcome} (${reason})` : String(done.outcome);
  }

  window.RunView = { STEPS, stepAfter, outcomeText };
})();
