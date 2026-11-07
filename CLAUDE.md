# Doublethink

A research agent for confidential work, split into two minds. The Planner holds the private memo and never reads
web text. The Reader reads web text and never sees the memo. The Gate is the only process with network access;
every outbound payload is checked, ledgered before sending, and exportable as a signed bundle.

Team of four, one folder each. Start every session by reading notes/TEAM_BRIEF.md and the personal file of the
person you are working for: notes/AAYUSH.md, notes/ANANT.md, notes/ILIA.md or notes/SHEARA_UI.md.
Spec: notes/SPEC.md. Interfaces: notes/INTERFACES.md, then shared/FORMATS.md once it exists (FORMATS.md wins).
Threat model: notes/THREAT_MODEL.md. Demo: notes/DEMO.md.

## Hackathon rule: fresh code only
- All code in this repo is written during HACK1984, after 11:00 on Sat Nov 7. Open-source libraries are allowed;
  other pre-written code is not.
- Never read, open, search, list, copy or import anything from any existing project folder on this machine
  (for example `~/doublethink`, `~/Projects`, `~/code`). If a task seems to need old code, stop and ask.
- Never run `/add-dir` on another folder. Work only inside this repo.

## Ownership
- Aayush: gate/, planner/, app/. Anant: checks/, proof/. Ilia: reader/, baseline/, fake_tavily/.
  Sheara: ui/. Shared: shared/ (change only after telling the group chat).
- Only edit the folders of the person you are working for. If you need something from another folder, write a
  clearly marked stub and say what the owner must provide.

## Invariants (a change that weakens one is a bug even if tests pass)
1. Only the Gate process touches the network. Every other process may reach loopback only, enforced by an audit
   hook installed at startup.
2. The Planner never receives web text: only result ids and validated typed fields (numbers, units, periods,
   found or not found).
3. The Reader never receives the memo, the question, the confirmed secrets or anything derived from them other
   than the public query that was already sent. The Reader has no tools and opens no connections.
4. The Gate runs every check on every outbound payload, whatever the Planner did.
5. Exact host allowlist: api.tavily.com, and api.anthropic.com for Reader jobs only.
6. Every outbound attempt, blocked ones included, is ledgered before it is sent. No code path sends without a row.
7. The single-agent baseline and compromised mode run only against the local Tavily stand-in.
8. Numbers in answers come from validated quotes and are computed in code, never written by a model.
9. All memos, companies, people and deals in fixtures are fictional.

## Working style
- notes/ATTACKS.md is not in this repo until the checks are frozen (tag `checks-frozen`). Do not ask for it.
- Tests first for every gate check. Tests use the standard library: `python3 -m unittest discover`.
- Small steps; tests green before moving on; report what changed and what is stubbed.
- Allowed dependency: `cryptography` (Ed25519). Ask before adding anything else. Tavily and Anthropic are called
  over plain HTTPS from the Gate, not through SDKs.
- Never print keys, never put keys in the ledger or logs, never commit .env.
- Plan mode first for any new task.
