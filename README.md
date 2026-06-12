# charter — the design document becomes the charter

Your design doc says:

> Auth tokens are HMAC, never JWT.

```bash
$ charter annotate SPEC.md      # LLM turns prose into enforceable decisions
$ cat CHARTER.md
[D-001] Auth tokens are HMAC, never JWT -> assert: ! grep -rqE "jwt|jsonwebtoken" src
$ charter approve --why "initial review"
```

Weeks later, an AI agent adds JWT code.

```bash
$ charter check
  FAIL D-001 "Auth tokens are HMAC, never JWT" — assert FAILED
```

The agent fixes it. Nobody was interrupted, nothing was forgotten, and
`charter trace D-001` shows every file that implements the decision.

That's the whole idea: **executable design intent for AI-coded repos** —
ADRs + linter + traceability, in one file with almost no state.

The doctrine in one sentence: **a decision with no jurisdiction is not
governed.** Every decision names an enforcer; a supervise-only decision with
neither code citations nor an `@` watch scope fails check. CHARTER.md is the
constitution, `check` is the court, `audit` is the judge for gray areas, and
`[D-xxx]` citations are the map.

Try it in 30 seconds: `sh demo/run_demo.sh` (on Windows, run it from Git
Bash) — an agent adds Supabase to a local-first app and check catches it.
No API key needed.

## Install

```bash
pip install .          # gives you the `charter` command
# — or just copy charter.py into your repo: it's one file, zero dependencies
python charter.py check
```

Python 3.10+. State on disk: `CHARTER.md` (yours), `.charter/ledger.jsonl`
(append-only journal), `.charter/charter.sha` (approval hash — commit it),
and `.charter/trusted` (local approval marker — never committed).

## Security, in one paragraph

`charter check` executes shell commands defined in CHARTER.md (the assert
enforcers). A freshly cloned repo will **not** execute its asserts — even if
it ships an approval hash — until you review CHARTER.md and run
`charter approve` yourself; CI opts in explicitly with
`CHARTER_TRUST_ASSERTS=1`. `annotate`/`audit` send doc and file contents to
your configured LLM backend; nothing else makes network calls. Details and
threat model: [SECURITY.md](SECURITY.md).

## The lifecycle

```
charter annotate SPEC.md     # LLM reads your prose doc, extracts binding
                             #   decisions, assigns [D-xxx] symbols, proposes
                             #   the lowest viable enforcer per decision,
                             #   writes CHARTER.md + SPEC.annotated.md
                             #   (charter init creates an empty CHARTER.md
                             #   if you'd rather write it by hand)
<review CHARTER.md once>     # the only mandatory human moment: adjust
                             #   enforcers, strengthen supervise items
charter approve --why "..."  # the human gate: journaled, hash-stamped
charter check                # deterministic, free — pre-commit + CI
charter audit                # judged pass over supervise-tier (PR-time)
charter digest [--mark]      # batch-review everything the system did
charter trace D-001          # everything that traces to a decision
charter graph [--json]       # the derived graph (Mermaid / machine-readable)
charter explain D-001        # the full story of one decision
charter doctor               # setup-health checks
charter install-hook         # pre-commit hook + Claude Code settings block
```

## The line syntax

```
[D-001] title -> assert: <must-pass> !! <proof-must-succeed> @ glob, glob
[D-002] title -> supervise @ src/db/**
```

- The enforcer kind is one of the ladder below.
- `!!` introduces an assert's **tripwire**: a probe that must succeed,
  proving the detector can detect a known violation sample (a typo'd grep
  path can't pass forever). The canonical pattern is
  `echo <violation-sample> | <the-real-detector>`.
- `@` declares **watch scope**: a human-set jurisdiction floor. Audit reads
  cited files ∪ watched files, so an uncited violating file is still seen.

## The five layers

1. **Annotate** — the bootstrap agent. Extraction is conservative
   (contracts, not preferences — "keep the code simple" is correctly
   ignored), capped at 15 by default (`--cap N`), dedupes against decisions
   already indexed, and annotation of your original doc is non-destructive
   (writes a `.annotated` copy with symbols inlined at the source sentences).
2. **Enforce** — the ladder, strongest first: `structure > type > test >
   lint > assert > supervise`. During review, push supervise items toward
   the stronger deterministic rungs. `check` fails on: aspirational
   decisions (no enforcer), missing enforcer targets, **enforcer rot** (the
   `#Symbol` vanished in a refactor), failing asserts, and **blind
   decisions** (supervise-only with no citations and no watch scope). A
   proposed enforcer that doesn't exist yet is a **build obligation** —
   check stays red until the builder creates the type/test, which is
   governance generating the skeleton of the system. `check --budget N`
   warns when judgment-only decisions outgrow the budget (default 5).
3. **Trace** — builders leave `[D-xxx]` citations in comments and commits.
   The graph is **derived from grep on every run, never stored** — so it can
   never go stale.
4. **Supervise** — `audit` judges only the supervise tier, and **citations
   are the scope**: the auditor reads exactly the files that claim to
   implement the decision, plus watched files. Verdicts: COMPLIES (ok line,
   exit 0), VIOLATES (exit 1 — fix the code), AMBIGUOUS (flagged for digest
   review). All verdicts land in the ledger. No backend configured →
   everything AMBIGUOUS, never crashes.
5. **Steer** — one optional SessionStart hook injects the whole index
   (~15 one-liners, a few hundred tokens, once per session) plus the
   citation protocol. No gates: agents stay in their native loop — cite the
   symbol, keep `check` green.

## LLM backends

Resolution order for `annotate` and `audit`:

1. `CHARTER_LLM_CMD` — any command that reads the prompt on stdin and
   prints the reply on stdout. Point it at Claude Code headless:
   `export CHARTER_LLM_CMD="claude -p"` — rides your existing plan.
2. `ANTHROPIC_API_KEY` — direct API (Sonnet for annotation quality, Haiku
   for cheap audit verdicts; override with `CHARTER_ANNOTATE_MODEL` /
   `CHARTER_AUDIT_MODEL`).
3. Neither — `annotate` explains itself; `audit` degrades to AMBIGUOUS.

## Integration

`.git/hooks/pre-commit` (or just run `charter install-hook`):
```bash
python charter.py check || exit 1
```

CI on PRs (the judged layer) — note the explicit opt-in, and treat PRs that
modify CHARTER.md like PRs that modify your CI workflows:
```bash
CHARTER_TRUST_ASSERTS=1 python charter.py check && python charter.py audit
```

`.claude/settings.json` (optional steering):
```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "python charter.py hook" } ] }
    ]
  }
}
```

For non-hook agents (Cursor, aider), put this in `AGENTS.md`/`.cursorrules`:

> This repo's binding decisions live in CHARTER.md. When your work implements
> or touches a decision, leave its `[D-xxx]` symbol in a nearby comment and
> your commit message. Run `python charter.py check` before finishing; a
> failure means an enforcer caught a violation — fix the code, never the
> enforcer. Conflicts between a request and a decision must be surfaced, not
> silently resolved.

## Liberties taken, and why

- **Citations replace scope globs.** The derived graph defines what each
  decision governs. This deleted the lockfile, ack protocol, session
  baselines, and per-edit hooks of earlier designs — the single largest
  overhead reduction — at the cost of relying on builders to cite. The
  steering hook + agent instructions make citing the path of least
  resistance, and `check` fails supervise decisions that end up blind.
- **Stateless judgment.** `audit` judges *current* state, not drift-since —
  so there is nothing to pin, ack, or reconcile. Run it whenever; the ledger
  is the only memory, and it's append-only and reviewable.
- **The graph navigates; enforcers govern.** `graph --json` exists for
  agents to ask "what connects to what," but no verdict ever comes from
  graph topology — authority lives in things that can't be argued with.

## Known limits

- **`check` executes shell from CHARTER.md.** The trust gate means a cloned
  repo can't run code on your machine before you review it, but after you
  approve, the asserts are exactly as trustworthy as your review of them.
  Read them like code you are about to run — because they are.
- A builder that never cites makes citation-only supervise decisions blind —
  check fails them rather than letting them silently un-govern. Decisions
  with `@` watch globs are still audited via watched files. Deterministic
  rungs are immune — prefer them.
- Annotation quality is bounded by the doc: vague prose yields supervise
  proposals. The review-once step is where you strengthen enforcers.
- `assert` commands are POSIX-shell; on Windows they run under Git Bash
  (auto-detected, `CHARTER_SHELL` overrides).
- A vacuous assert's `!! proof` is authored by the same source as the
  assert, so the tripwire raises the bar but can't fully self-police —
  `check` flags trivially-true probes (`!! true`, bare `echo`), but a
  cleverly matched fake proof still needs the human review-once gate.
- `audit` judges at most the first 60 in-scope files per decision (chunked,
  worst-verdict-wins) to bound LLM cost; broad `@ src/**` scopes over huge
  trees are reported as truncated. Narrow watch globs audit completely.
- `audit` sends in-scope file contents to the model, and a determined
  prompt-injection in governed code can still influence a verdict —
  deterministic rungs carry the real authority; `supervise`+`audit` is the
  soft, advisory tier.

## History

See [CHANGELOG.md](CHANGELOG.md). Charter was previously named governor;
v0.4.0 renamed it and added the local trust gate.
