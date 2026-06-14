# Contributing to Charter

Thanks for trying Charter. Bug reports, failing-case repros, and PRs are all
welcome.

## The most useful thing you can do

Run `charter annotate` on a real design doc and tell us whether the decisions
it extracts are any good. Annotation quality is the part most worth hardening,
and the failure cases are hard to find without real docs. A pasted CHARTER.md
that came out wrong is a great issue.

## Dev setup

Charter is a single file with zero runtime dependencies. The only dev
dependency is pytest.

```bash
git clone https://github.com/cspergel/Charter
cd Charter
python -m pip install "pytest==8.*"
python -m pytest tests/ -q          # 63 passed, 2 skipped on Windows; 65/0 on Linux CI
sh demo/run_demo.sh                 # offline end-to-end (Git Bash on Windows)
```

Python 3.10+. No backend or API key is needed to run the tests or the demo —
they use an offline fake annotator.

Two tests skip off-CI: a symlink test (needs elevated privileges on Windows)
and the POSIX demo golden test (skipped on Windows). Both run on Linux CI.

## Workflow

- **Tests first.** Every behavior change ships with a test. The suite uses a
  RED-then-GREEN discipline — write the failing test, watch it fail, then make
  it pass. New regression tests go in `tests/test_charter.py`.
- **Keep it one file, zero dependencies.** `charter.py` imports only the
  standard library. That constraint is a feature; please don't add runtime
  deps.
- **Run the demo before opening a PR.** `sh demo/run_demo.sh` must stay green —
  it's the first thing a new user sees. (Step 4 intentionally prints one
  `WARN uncited governed file …` — that's the demo catching a violation, not a
  regression. No other warnings should appear.)

## A note on the test backend (Windows gotcha)

A `CHARTER_LLM_CMD` test backend must be invoked with double quotes
(`f'"{sys.executable}" "{script}"'`) because `shell=True` runs it under
cmd.exe on Windows, which can't parse POSIX single-quotes. A broken backend
degrades audit to AMBIGUOUS and exits 0 — so a test can pass for the wrong
reason. Always include at least one assertion that fails loudly if the backend
didn't actually run.

## Security

Charter executes shell commands from CHARTER.md by design. If you find a way to
make `check` execute code without local approval, or to exfiltrate data, please
report it privately via GitHub's security advisory tab rather than a public
issue. See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree your contributions are licensed under the
[MIT License](LICENSE).
