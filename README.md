# charter — checks your code against your design doc, then tries to beat its own checks

You write your design decisions in prose — "auth tokens are HMAC, never JWT," "the domain layer can't import the web layer." An LLM turns each one into a one-line deterministic check, you approve that file like code, and from then on `charter check` enforces it with no LLM involved.

```bash
$ charter annotate SPEC.md      # LLM turns prose into enforceable decisions
$ cat CHARTER.md
[D-001] Auth tokens are HMAC, never JWT -> assert: ! grep -rqE "jwt|jsonwebtoken" src
$ charter approve --why "initial review"
```

Weeks later an agent adds JWT code, and `charter check` catches it:

```bash
$ charter check
  FAIL D-001 "Auth tokens are HMAC, never JWT" — assert FAILED
```

The part worth showing is `charter verify --adversarial`. It's an LLM that tries to beat your own checks: it plants a real violation where the grep won't look — a different path, a synonym, another file type — on a sandboxed copy it always restores, and tells you which checks it got past. Then it suggests a tighter one. I ran it on rust-analyzer and it slipped past 6 of 7 layering rules with a Cargo package-rename trick. Those were rules I thought were enforcing something.

So that's the idea: keep an AI-coded repo true to the decisions you already made — design doc in, enforced checks out, with an adversary that tells you which checks are real.

> **Status: a weekend project / proof of concept.** One file, one idea — that an
> architectural decision should be *executable*, not just documented. No daemon,
> no service, no config sprawl. The interesting work from here is hardening
> annotation quality and the enforcer ladder — issues and PRs welcome.

Try it in 30 seconds: `sh demo/run_demo.sh` (on Windows, run it from Git
Bash) — an agent adds Supabase to a local-first app and check catches it.
No API key needed.

## Quick start

See it work first — the demo is offline and needs no API key (on Windows,
run it from Git Bash):

```bash
git clone https://github.com/cspergel/Charter
cd Charter
sh demo/run_demo.sh        # an agent adds Supabase to a local-first app; check catches it
```

Then use it on your own repo. There are two ways to run it:

```bash
# Option A — zero install. It's one file, zero dependencies (Python 3.10+).
python /path/to/charter.py check

# Option B — install the `charter` command.
pip install charter-intent   # the command is `charter`; `charter` was taken on PyPI
# — or from a local checkout: pip install .
charter check
```

`annotate` (turning a prose doc into decisions) needs an LLM backend; point it
at Claude Code with no API key required:

```bash
export CHARTER_LLM_CMD="claude -p"   # or set ANTHROPIC_API_KEY
charter annotate SPEC.md
charter approve --why "initial review"
charter check
charter doctor                       # checks your setup is sound
```

State on disk: `CHARTER.md` (yours), `.charter/ledger.jsonl` (append-only
journal), and `.charter/charter.sha` (approval hash — commit it). Permission to
*execute* asserts is recorded in a per-user trust store **outside** the repo
(`~/.charter/trust`, keyed by repo path), so nothing a repo ships can grant
itself execution.

## Security, in one paragraph

`charter check` executes shell commands defined in CHARTER.md (the assert
enforcers). A freshly cloned repo will **not** execute its asserts — even if it
ships an approval hash, and even if it ships a forged trust marker — until you
review CHARTER.md and run `charter approve` yourself, because the trust record
lives in a per-user store outside the repo. CI opts in explicitly with
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
charter verify               # prove each enforcer is actually live, not theater
charter verify --adversarial # an LLM saboteur tries to bypass each enforcer
charter audit                # judged pass over supervise-tier (PR-time)
charter log [D-001] [--verify]  # the accountability record (tamper-evident)
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
   citation protocol. The PreToolUse hook (`hook --file`) goes further: it
   **blocks an edit before it lands** if the proposed content would trip an
   assert, returning the decision as the reason so the agent self-corrects
   mid-task — governance inside the loop, not just post-hoc in CI.

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

## Proof-carrying governance (`verify`)

A check that's never been exercised is a check you can't trust — a typo'd grep
path passes forever and you never notice. `charter verify` proves each
deterministic decision is actually enforceable against your code *right now*.

`charter verify --adversarial` goes further: an LLM red-team agent tries to
slip a real violation past each enforcer — hiding it in a path the grep
doesn't scan, a synonym the pattern misses, a different file type — on a
sandboxed copy that's always restored. Anything it gets through is reported as
a **bypass**, with the exact evasion, and it proposes a tighter enforcer that
closes the hole. On rust-analyzer it bypassed 6 of 7 layering rules with a
Cargo package-rename trick; on this project's own sibling tool, 3 of 5 (a "no
network calls" rule only grepped `requests|httpx|urllib`, so `http.client`
walked right past). Governance that attacks itself — so "is this rule real or
just theater?" has an answer.

## Where it fits

The neighbors solve adjacent problems; none does Charter's loop:

| | Governs | Who writes the rules | Enforced every commit? |
|---|---|---|---|
| **Spec-driven dev** (Spec Kit, OpenSpec, Kiro) | code *generation*, up front | you write the spec | no — out of the loop once code exists |
| **Arch fitness functions** (ArchUnit, dependency-cruiser) | the codebase | you, by hand, in code | yes (per language) |
| **ADR tools** (adr-tools, Log4brains) | a written record | you write the ADR | no — nothing checks the code |
| **Charter** | the living repo | an LLM drafts, you approve | yes, deterministically |

The gap Charter fills: it turns a *prose* decision into an enforced check, keeps
the decision→code map current via citations, and does it without you
hand-writing the rule — across any language, since the deterministic layer is
just shell. Spec tools are upstream of the code; fitness functions need
hand-written rules per stack; ADR tools document but never enforce. Use Charter
*with* a spec tool if you like — scaffold generation with one, keep the repo
true with the other.

## FAQ

**Isn't this just a pre-commit hook that runs grep?**
At the deterministic layer, yes — and that's the point. A grep that can't be
argued with beats an LLM that can be talked out of a verdict. Charter's value
isn't a cleverer check; it's turning prose decisions into checks at all,
keeping them in sync with the code via citations, and proving the checks aren't
vacuous (tripwires). The grep is a feature, not an embarrassment.

**Why not Spec Kit / OpenSpec / Kiro?**
Those govern code *generation* — write a spec, then generate from it. They're
out of the loop the moment a later change quietly contradicts the original
design, which is where drift actually accrues. Charter governs the repo from
then on, on every commit. They compose: scaffold with whatever you like, keep
it true with Charter.

**An LLM wrote my enforcement rules — why would I trust that?**
You don't trust it — you review it. `annotate` only *proposes*; nothing takes
effect until you read CHARTER.md and `approve` it, exactly like reading code
you're about to run. At enforcement time there's no LLM in the loop: `check` is
deterministic shell. The model proposes, you ratify, grep decides.

**What stops an agent from editing CHARTER.md, or weakening an enforcer, to make
check pass?**
Any change to CHARTER.md fails `check` until a human runs `approve` (a hashed,
journaled gate) — so an agent can't quietly rewrite the constitution. The agent
instructions say *fix the code, never the enforcer*, and a weakened assert trips
its tripwire (the proof that it can still catch a known violation). Tampering is
visible, not silent.

**Won't grep-based asserts be brittle and false-positive?**
Some will — which is why the ladder exists. Push fragile checks up to `type`,
`test`, or `lint`, where the language and your test runner do the work; reserve
`assert` for things that genuinely are a grep. Tripwires flag asserts that have
quietly stopped detecting anything, so a brittle check fails loudly rather than
passing forever.

**Does it lock me into Claude?**
No. Any backend that reads a prompt on stdin works (`CHARTER_LLM_CMD`), the
Anthropic API works, and you can skip the LLM entirely and write CHARTER.md by
hand — `check` never calls a model.

## Known limits

- **Sweet spot: a repo with a real design/architecture doc.** Baseline-tested
  across 9 OSS repos in 7 languages — Flask, httpx, prettier, rust-analyzer, the
  GitHub CLI, okhttp, Deno, curl, and Polly. It does best when the doc states
  binding "never/always/default"
  decisions; it degrades on (a) repos with no design doc — pointed at a how-to
  guide it tends to extract file-existence trivia, (b) very large monorepos,
  and (c) deep language-specific symbol/dependency layouts (Go package symbols,
  Kotlin multi-root/Gradle version catalogs). Open issues track these. The
  deterministic `assert` rung is the most language-agnostic; lean on it.
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
