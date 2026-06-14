# Changelog

## v0.4.3 — annotation-quality fixes from a third-party baseline

A baseline test on a real repo we didn't write (Flask's `docs/design.rst`,
graded by an independent reviewer) drove two fixes:

- **annotate now proposes a `!! tripwire` proof for every assert.** Previously
  a generated "never add a database layer" guard shipped with no proof, so it
  could silently rot if someone edited the regex — passing green while
  detecting nothing. The prompt now requires a tripwire per assert: a probe
  that pipes a known violation sample into the same detector and must exit 0.
  Verified on Flask — every assert ships a proof and `doctor` reports "all
  asserts carry tripwire proofs."
- **`type: file#Class.method` targets resolve to the member.** The symbol
  scanner matched the literal dotted string, so a reasonable suggestion like
  `#Flask.wsgi_app` false-failed as enforcer rot (source defines `def
  wsgi_app`, never `Flask.wsgi_app`). A dotted target now resolves to its final
  member; whole-token matching for plain symbols is unchanged.
- **annotate now sees the repo's real files and targets them.** A 5-repo
  baseline (httpx, rust-analyzer, click, prettier, Flask) showed the dominant
  failure was annotate *guessing* test/file targets that don't exist — e.g. it
  invented `tests/test_envvars.py` — so a freshly-annotated repo checked mostly
  red for no real reason. The prompt now receives a capped manifest of actual
  repo paths and must target those (or prefer a self-contained `assert:`),
  greps dependency manifests rather than comment-matchable source for
  "must-not-depend" rules, and attaches `@ watch` globs to supervise decisions.
  On click this moved the result from 2/10 enforcers live to 6/6.

## v0.4.2 — trust bound to repo instance (adversarial review)

An adversarial review of the 0.4.1 trust redesign found a narrower residual
hole: the out-of-repo trust record was keyed only by repo path + CHARTER.md
hash, so a *different* repo later placed at the same path with a byte-identical
CHARTER.md inherited the approval — and could ship altered helper scripts its
asserts invoke. Trust is now also pinned to a per-repo **instance nonce**
stored in `.git` (uncommitted, regenerated on every clone). A replacement repo
gets a fresh `.git` with no nonce, so its asserts are refused until you approve
it yourself. Non-git repos and worktrees keep the path+hash fallback.

## v0.4.1 — security + correctness (pre-release audit)

A 5-lens audit before the public launch found two release blockers, both fixed
here:

- **Trust gate was forgeable (security).** In 0.4.0 the local trust marker
  lived inside the repo (`.charter/trusted`) and its content was just the
  approval hash — a value the repo author can compute. A committed or
  force-added marker could therefore make a *cloned* repo execute its asserts
  with no local review, the exact thing the gate exists to prevent. Trust now
  lives in a per-user store **outside** the repo (`~/.charter/trust`, keyed by
  repo path); nothing a repo ships can grant itself execution. A leftover
  in-repo `trusted` marker is ignored.
- **CRLF line endings broke approval across platforms.** `intent_hash` hashed
  raw bytes, so a CHARTER.md approved on Windows (CRLF) failed `check` on Linux
  CI (LF) as a false tamper. The hash now normalizes line endings.
- **`extract_json` could hang** for minutes on adversarial backend output (a
  long run of unclosed brackets was O(n²)); now bounded (~0.3s worst case).
- Smaller fixes: non-executing rot checks (type/test/lint) now run on a
  cloned-but-not-locally-trusted repo instead of being skipped; `.annotated`
  copies no longer raise spurious "uncited governed file" warnings; the
  pre-commit hook is written with LF newlines.

## v0.4.0 — publication hardening + rename

- **Renamed: governor → charter.** The tool is `charter`, the index is
  `CHARTER.md`, state lives in `.charter/`, env vars are `CHARTER_*`.
- **Trust gate (security).** A committed `.charter/charter.sha` no longer
  grants assert execution by itself. Asserts are shell commands authored by
  whoever wrote the repo, so running them now requires *local* approval:
  `charter approve` writes a `.charter/trusted` marker (auto-gitignored) on
  the approving machine. A cloned repo arrives approved-but-untrusted —
  `check` reports it and refuses to execute asserts until you review
  CHARTER.md and approve locally, or explicitly opt in with
  `CHARTER_TRUST_ASSERTS=1` / `check --trust` (for CI you control).
- **Tripwire heuristic fixed**: `echo sample | real-detector` pipelines are
  the canonical proof pattern and are no longer flagged as trivial; only a
  bare `echo`/`printf`/`true` (exit status unconditionally 0) is.
- **UTF-8 output everywhere**: stdout/stderr reconfigured at startup, fixing
  mojibake on Windows when output is piped (Git Bash, CI logs, agents).
- Packaging: LICENSE file, classifiers, `requires-python >= 3.10`,
  CI matrix 3.10/3.13, sdist excludes bytecode.

## v0.3.2 — packaging & trust

- pytest suite: parsing, glob semantics, JSON extraction, the full check
  lifecycle (approval, tamper, vacuous tripwires, blind supervise,
  watch-jurisdiction audit), and a golden test of the offline demo.
- `pyproject.toml` — `pip install .` gives a `charter` console command.
- CI workflow — Ubuntu + Windows matrix.
- Windows shell resolution fixed: asserts find Git Bash at its install paths
  and never use the System32 WSL launcher; `CHARTER_SHELL` overrides;
  `doctor` runs a live shell probe; with no POSIX shell, asserts fail with a
  clear message.
- Demo is location-agnostic.

## v0.3.1 — polish

- `check --json` and `explain --json` — machine-readable outputs.
- `CHARTER_ANNOTATE_MODEL` / `CHARTER_AUDIT_MODEL` env overrides.
- Bracket-typed JSON scanner; simplified trailing `/**` glob handling;
  doctor reads hooks with explicit encoding.
- `demo/` — self-contained SQLite-vs-Supabase scenario with an offline fake
  annotator (zero setup) that upgrades to a real LLM when configured.

## v0.3 — "hard to misuse"

- Blind supervise decisions now FAIL check (escape hatch:
  `--allow-blind-supervise`). A decision with no jurisdiction is not governed.
- `charter doctor` — setup-health checks.
- `charter explain D-001` — the full story of one decision.
- `charter install-hook` — pre-commit hook + Claude Code settings block.
- Annotator writes provenance comments; supervise proposals keep `@` globs.
- Correct `**` glob semantics; balanced-bracket JSON extraction; trace
  separates code citations from doc mentions.

## v0.2 — hardening (post-audit)

- **Watch scopes**: decisions take an optional `@ glob` suffix — a
  human-declared scope floor. Audit jurisdiction = code citations ∪ watched
  files.
- **Tripwires**: asserts take a `!! proof` suffix — a probe that must
  succeed, demonstrating the detector can detect a known violation sample.
- **Approval sentinel**: any change to CHARTER.md fails check until a human
  runs `charter approve --why "..."`.
- Stateless per-file steering hook (`hook --file`).
- Asserts run under Git Bash on Windows; audit discloses truncation;
  liveness counts code citations only; files >1MB skipped in scans.
