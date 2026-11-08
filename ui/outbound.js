// Doublethink UI: the Outbound panel's logic. Pure functions, no DOM, no network.
// Input: the ledger entries app.js keeps per session ({row, display, blockedInfo}, FORMATS §7 and §10).
// Output: one item per outbound attempt, a summary line and a secret-check line, all computed from the events.
// Nothing here is hard-coded per run: hosts, kinds, counts, rules and details all come from the ledger rows.
'use strict';

(function (root) {
  // A destination on loopback is the local Tavily stand-in: it plays the web in the demo, but stays on this device.
  const LOOPBACK = /^(127(?:\.\d{1,3}){3}|localhost|\[::1\]|::1)(?::\d+)?$/i;

  // The data's kinds (FORMATS §1: search | extract | reader) and the words for them.
  const KINDS = {
    search: { label: 'search', one: 'search query', many: 'search queries' },
    extract: { label: 'page read', one: 'page read', many: 'page reads' },
    reader: { label: 'reading job', one: 'reading job', many: 'reading jobs' },
  };

  const isLoopback = (host) => LOOPBACK.test(String(host || ''));
  // "Confirmed secret or the canary": the Gate's secret.* rules and the canary rule (FORMATS §6, §10).
  const isSecretRule = (rule) => typeof rule === 'string' && (rule === 'canary' || rule.startsWith('secret.'));
  const isProvenanceRule = (rule) => typeof rule === 'string' && rule.startsWith('provenance.');
  const pad2 = (n) => String(n).padStart(2, '0');

  function kindLabel(kind) { return (KINDS[kind] && KINDS[kind].label) || String(kind); }

  function counted(n, kind) {
    const k = KINDS[kind];
    if (k) return `${n} ${n === 1 ? k.one : k.many}`;
    return `${n} ${kind} ${n === 1 ? 'request' : 'requests'}`;
  }

  function plural(n, one, many) { return `${n} ${n === 1 ? one : many}`; }

  function summarize(entries) {
    const attempts = (entries || [])
      .filter((e) => e && e.row && e.row.row_type === 'attempt')
      .map((e) => {
        const r = e.row;
        return {
          seq: r.seq,
          time: typeof r.time === 'string' ? r.time.slice(11, 19) : '',
          host: r.destination || '',
          kind: r.kind,
          decision: r.decision === 'blocked' ? 'blocked' : 'sent',
          rule: r.rule == null ? null : r.rule,
          detail: (e.blockedInfo && e.blockedInfo.detail) || (e.display && e.display.detail) || null,
          local: isLoopback(r.destination),
        };
      });

    // Group sent attempts by (kind, host), in order of first appearance.
    const group = (list) => {
      const map = new Map();
      for (const a of list) {
        const key = `${a.kind}\u0000${a.host}`;
        if (!map.has(key)) map.set(key, { kind: a.kind, host: a.host, n: 0 });
        map.get(key).n += 1;
      }
      return [...map.values()];
    };
    const sent = attempts.filter((a) => a.decision === 'sent');
    const blocked = attempts.filter((a) => a.decision === 'blocked');
    return {
      attempts,
      sent,
      blocked,
      left: group(sent.filter((a) => !a.local)),
      local: group(sent.filter((a) => a.local)),
      secretSent: sent.filter((a) => isSecretRule(a.rule)),
      secretBlocked: blocked.filter((a) => isSecretRule(a.rule)),
      provenanceSent: sent.filter((a) => isProvenanceRule(a.rule)),
    };
  }

  const listGroups = (groups) => groups.map((g) => `${counted(g.n, g.kind)} to ${g.host}`).join(', ');
  const uniq = (xs) => [...new Set(xs)];

  // "Left this device: N search queries to [host], M page reads to [host]. Blocked: K."
  function summaryText(sum) {
    const parts = [];
    if (sum.left.length) parts.push(`Left this device: ${listGroups(sum.left)}.`);
    if (sum.local.length) parts.push(`Sent to the local stand-in for the web (stayed on this device): ${listGroups(sum.local)}.`);
    if (!sum.left.length && !sum.local.length) {
      parts.push(sum.attempts.length ? 'Nothing left this device.' : 'Nothing has left this device yet.');
    }
    parts.push(`Blocked: ${sum.blocked.length}.`);
    return parts.join(' ');
  }

  // From the Gate's check results (the rule on each attempt), never from matching strings in the page.
  function check(sum) {
    const head = 'Confirmed secret or canary in a sent request:';
    let verdict;
    let text;
    if (!sum.attempts.length) {
      verdict = 'none';
      text = `${head} no requests yet.`;
    } else if (sum.secretSent.length) {
      verdict = 'yes';
      const hits = sum.secretSent.map((a) => `Row ${pad2(a.seq)} to ${a.host}: ${a.detail ? `${a.detail} ` : ''}(${a.rule})`);
      text = `${head} yes, in ${sum.secretSent.length} of ${plural(sum.sent.length, 'sent request', 'sent requests')}. ${hits.join('; ')}.`;
    } else if (!sum.sent.length) {
      verdict = 'no';
      text = `${head} no, nothing was sent.`;
    } else {
      verdict = 'no';
      text = `${head} no, 0 of ${plural(sum.sent.length, 'sent request', 'sent requests')} matched.`;
    }
    // Notes are separate from the verdict, so the panel can colour the verdict alone.
    const notes = [];
    if (sum.secretBlocked.length) {
      notes.push(`Blocked before sending: ${sum.secretBlocked.length} (${uniq(sum.secretBlocked.map((a) => a.rule)).join(', ')}).`);
    }
    if (sum.provenanceSent.length) {
      notes.push(`A rare memo term (provenance check) was in ${plural(sum.provenanceSent.length, 'sent request', 'sent requests')} (${uniq(sum.provenanceSent.map((a) => a.rule)).join(', ')}).`);
    }
    return { verdict, verdictText: text, notes, text: [text, ...notes].join(' ') };
  }

  root.Outbound = Object.freeze({ summarize, summaryText, check, kindLabel, isLoopback, isSecretRule });
})(typeof window !== 'undefined' ? window : globalThis);
