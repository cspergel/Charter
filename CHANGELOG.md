# Changelog

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
