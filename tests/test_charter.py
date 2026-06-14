"""charter test suite — run with: pytest tests/ -q"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import charter as g  # noqa: E402

GOV = [sys.executable, str(HERE.parent / "charter.py")]


def trust_home(repo):
    """The per-user trust store base for a test repo — kept OUTSIDE the repo
    (a sibling dir) so the subprocess writes nowhere near the real ~/.charter
    and the repo's own file walk never sees it."""
    return Path(str(repo) + ".charterhome")


def run(args, cwd, env=None, stdin=""):
    e = {**os.environ, "CHARTER_HOME": str(trust_home(Path(cwd))), **(env or {})}
    return subprocess.run(GOV + args, cwd=cwd, capture_output=True,
                          text=True, env=e, timeout=120, input=stdin)

FAKE_AUDITOR = (f'{sys.executable} -c "import sys,json; p=sys.stdin.read(); '
                f"print(json.dumps({{'verdict':'VIOLATES','reason':'pg'}}) "
                f"if 'psycopg2' in p else "
                f"json.dumps({{'verdict':'COMPLIES','reason':'ok'}}))\"")


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "db").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------- unit

GLOB_CASES = [
    ("src/a/auth/x.py", "src/**/auth/*.py", True),
    ("src/auth/x.py", "src/**/auth/*.py", True),
    ("src/a/auth/sub/x.py", "src/**/auth/*.py", False),
    ("src/x.py", "src/**", True),
    ("src", "src/**", True),
    ("other/x.py", "src/**", False),
    ("a.sql", "*.sql", True),
    ("d/a.sql", "*.sql", False),
    ("src/auth/x.py", "src/auth/*.py", True),
    ("src/auth/d/x.py", "src/auth/*.py", False),
]


@pytest.mark.parametrize("rel,pat,exp", GLOB_CASES)
def test_glob_match(rel, pat, exp):
    assert g.glob_match(rel, pat) == exp


def test_extract_json_tolerates_prose_and_symbols():
    raw = 'Per [D-001] and [D-002]: {"verdict":"COMPLIES","reason":"ok"} bye'
    assert g.extract_json(raw) == {"verdict": "COMPLIES", "reason": "ok"}


def test_extract_json_recovers_from_mismatched_nesting():
    assert g.extract_json('junk [1,{]} then {"a":2}') == {"a": 2}


def test_extract_json_none_cases():
    assert g.extract_json("") is None
    assert g.extract_json("no json here") is None


def test_extract_json_does_not_hang_on_bracket_spam():
    import time
    t0 = time.time()
    assert g.extract_json("[" * 200_000) is None
    assert time.time() - t0 < 2.0


def test_parse_intent_full_line(repo):
    (repo / "CHARTER.md").write_text(
        '# source: SPEC.md :: "never JWT"\n'
        '[D-001] No JWT -> assert: ! grep -rq jwt src '
        '!! echo jwt | grep -q jwt @ src/auth/**, src/api/*.py\n'
        "[D-002] Local only -> supervise @ src/db/**\n", encoding="utf-8")
    d, problems = g.parse_intent(repo)
    assert not problems
    assert d["D-001"]["kind"] == "assert"
    assert d["D-001"]["tripwire"] == "echo jwt | grep -q jwt"
    assert d["D-001"]["watch"] == ["src/auth/**", "src/api/*.py"]
    assert d["D-002"]["watch"] == ["src/db/**"]


def test_parse_intent_flags_aspirational_lines(repo):
    (repo / "CHARTER.md").write_text("[D-001] wishful thinking, no arrow\n")
    _, problems = g.parse_intent(repo)
    assert problems and "enforcer" in problems[0]


def test_parse_intent_rejects_malformed_kind(repo):
    (repo / "CHARTER.md").write_text("[D-001] x -> supervised @ src/**\n")
    d, problems = g.parse_intent(repo)
    assert not d and problems


# ----------------------------------------------------------- lifecycle

INTENT = (
    "[D-001] No JWT -> assert: ! grep -rq jwt src "
    "!! echo jwt | grep -q jwt @ src/auth/**\n"
    "[D-002] SQLite only -> supervise @ src/db/**\n")


def settle(repo):
    (repo / "CHARTER.md").write_text(INTENT, encoding="utf-8")
    (repo / "src/auth/token.py").write_text("# [D-001]\nok\n")
    (repo / "src/db/conn.py").write_text("# [D-002]\nimport sqlite3\n")
    assert run(["approve", "--why", "t"], repo).returncode == 0


def _approve_assert_repo(repo):
    """A repo with one deterministic decision that currently holds (no
    'supabase' under src/), approved locally so verify may run it."""
    (repo / "CHARTER.md").write_text(
        '[D-001] No hosted backend -> assert: ! grep -rqE "supabase" src '
        '!! echo supabase | grep -qE "supabase"\n', encoding="utf-8")
    (repo / "src" / "app.py").write_text("import sqlite3\n", encoding="utf-8")
    assert run(["approve", "--why", "t"], repo).returncode == 0


def test_verify_proves_live_enforcer(repo):
    _approve_assert_repo(repo)
    r = run(["verify"], repo)
    assert r.returncode == 0
    assert "proven" in r.stdout


def test_verify_adversarial_defended_and_restores(repo):
    """Saboteur writes the violation where the grep DOES look -> caught;
    and the mutation is always reverted."""
    _approve_assert_repo(repo)
    backend = echo_backend(repo, {"file": "src/sneaky.py", "mode": "create",
                                  "content": "import supabase\n",
                                  "note": "inside src"})
    r = run(["verify", "--adversarial"], repo, env={"CHARTER_LLM_CMD": backend})
    assert r.returncode == 0
    assert "defended" in r.stdout
    assert not (repo / "src" / "sneaky.py").exists()   # restored


def test_verify_adversarial_finds_bypass_and_restores(repo):
    """Saboteur writes the violation where the grep does NOT look (outside
    src/) -> the enforcer misses it -> reported as a bypass; mutation reverted."""
    _approve_assert_repo(repo)
    backend = echo_backend(repo, {"file": "notes.txt", "mode": "create",
                                  "content": "we use supabase here\n",
                                  "note": "outside the src/ scope the grep checks"})
    r = run(["verify", "--adversarial"], repo, env={"CHARTER_LLM_CMD": backend})
    assert r.returncode == 1
    assert "BYPASS" in r.stdout
    assert not (repo / "notes.txt").exists()           # restored even on bypass


def test_verify_requires_local_approval(repo):
    (repo / "CHARTER.md").write_text(
        '[D-001] x -> assert: ! grep -rqE "supabase" src !! echo supabase | grep -q supabase\n',
        encoding="utf-8")
    d = repo / ".charter"; d.mkdir()
    (d / "charter.sha").write_text(g.intent_hash(repo) + "\n", encoding="utf-8")
    r = run(["verify"], repo)   # approved-but-not-locally-trusted clone
    assert r.returncode == 1 and "approve" in (r.stdout + r.stderr)


def test_hook_blocks_violating_edit(repo):
    """In-loop enforcement: a PreToolUse edit that would trip an assert is
    denied before it lands, and the sandbox is restored."""
    _approve_assert_repo(repo)
    new = repo / "src" / "new.py"
    payload = json.dumps({"tool_input": {
        "file_path": str(new), "content": "import supabase\n"}})
    r = run(["hook", "--file"], repo, stdin=payload)
    out = json.loads(r.stdout)
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "D-001" in hso["permissionDecisionReason"]
    assert not new.exists()   # sandbox restored


def test_hook_allows_compliant_edit(repo):
    _approve_assert_repo(repo)
    new = repo / "src" / "new.py"
    payload = json.dumps({"tool_input": {
        "file_path": str(new), "content": "import sqlite3\n"}})
    r = run(["hook", "--file"], repo, stdin=payload)
    if r.stdout.strip():
        out = json.loads(r.stdout)
        assert out["hookSpecificOutput"]["permissionDecision"] != "deny"
    assert not new.exists()


def test_hook_does_not_block_untrusted_repo(repo):
    """A cloned-but-not-locally-approved repo must not run its asserts from the
    hook — it steers at most, never executes."""
    (repo / "CHARTER.md").write_text(
        '[D-001] No hosted backend -> assert: ! grep -rqE "supabase" src '
        '!! echo supabase | grep -qE "supabase"\n', encoding="utf-8")
    d = repo / ".charter"; d.mkdir()
    (d / "charter.sha").write_text(g.intent_hash(repo) + "\n", encoding="utf-8")
    new = repo / "src" / "new.py"
    payload = json.dumps({"tool_input": {
        "file_path": str(new), "content": "import supabase\n"}})
    r = run(["hook", "--file"], repo, stdin=payload)
    if r.stdout.strip():
        out = json.loads(r.stdout)
        assert out["hookSpecificOutput"]["permissionDecision"] != "deny"


def test_log_shows_record_and_verifies_chain(repo):
    settle(repo)
    r = run(["log"], repo)
    assert "APPROVED" in r.stdout
    v = run(["log", "--verify"], repo)
    assert v.returncode == 0 and "intact" in v.stdout


def test_log_verify_detects_tamper(repo):
    settle(repo)
    assert run(["approve", "--why", "second approval"], repo).returncode == 0
    led = repo / ".charter" / "ledger.jsonl"
    lines = led.read_text(encoding="utf-8").splitlines()
    e = json.loads(lines[0]); e["reason"] = "HACKED"
    lines[0] = json.dumps(e)
    led.write_text("\n".join(lines) + "\n", encoding="utf-8")
    v = run(["log", "--verify"], repo)
    assert v.returncode == 1 and "TAMPER" in v.stdout


def test_unapproved_index_fails(repo):
    (repo / "CHARTER.md").write_text(INTENT)
    r = run(["check"], repo)
    assert r.returncode == 1 and "never been approved" in r.stdout


def test_clean_check_passes(repo):
    settle(repo)
    r = run(["check"], repo)
    assert r.returncode == 0, r.stdout


def test_tamper_detected(repo):
    settle(repo)
    (repo / "CHARTER.md").write_text(INTENT.replace("No JWT", "JWT fine"))
    r = run(["check"], repo)
    assert r.returncode == 1 and "changed since last approval" in r.stdout


def test_assert_violation_fails(repo):
    settle(repo)
    (repo / "src/auth/bad.py").write_text("# [D-001]\nimport jwt\n")
    r = run(["check"], repo)
    assert r.returncode == 1 and "assert FAILED" in r.stdout


def test_vacuous_assert_caught_by_tripwire(repo):
    (repo / "CHARTER.md").write_text(
        "[D-001] vacuous -> assert: ! grep -rq xyzzy missing_dir "
        "!! grep -rq xyzzy missing_dir\n")
    run(["approve", "--why", "t"], repo)
    r = run(["check"], repo)
    assert r.returncode == 1 and "tripwire FAILED" in r.stdout


def test_blind_supervise_fails_by_default(repo):
    (repo / "CHARTER.md").write_text("[D-001] thing -> supervise\n")
    run(["approve", "--why", "t"], repo)
    assert run(["check"], repo).returncode == 1
    assert run(["check", "--allow-blind-supervise"], repo).returncode == 0


def test_uncited_governed_file_warned_and_check_json(repo):
    settle(repo)
    (repo / "src/db/new.py").write_text("uncited\n")
    r = run(["check", "--json"], repo)
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert any("uncited governed file" in w for w in out["warnings"])


def test_audit_uses_watch_jurisdiction_for_uncited_violator(repo):
    settle(repo)
    (repo / "src/db/pg.py").write_text("import psycopg2\n")  # uncited!
    r = run(["audit"], repo, env={"CHARTER_LLM_CMD": FAKE_AUDITOR})
    assert r.returncode == 1 and "VIOLATES" in r.stdout


def test_audit_judges_beyond_first_six_files(repo):
    settle(repo)
    for i in range(6):
        (repo / f"src/db/a{i}.py").write_text("# [D-002]\nimport sqlite3\n")
    (repo / "src/db/z_last.py").write_text("import psycopg2\n")  # sorts last
    r = run(["audit"], repo, env={"CHARTER_LLM_CMD": FAKE_AUDITOR})
    assert r.returncode == 1 and "VIOLATES" in r.stdout


def test_audit_refuses_tampered_intent(repo):
    settle(repo)
    (repo / "CHARTER.md").write_text(INTENT.replace("No JWT", "JWT fine"))
    r = run(["audit"], repo)
    assert r.returncode == 1 and "approve" in (r.stdout + r.stderr)


def test_audit_does_not_read_through_escaping_symlinks(repo, tmp_path_factory):
    settle(repo)
    secret = tmp_path_factory.mktemp("outside") / "secret.py"
    secret.write_text("import psycopg2\n")
    try:
        os.symlink(secret, repo / "src/db/leak.py")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform/privilege level")
    r = run(["audit"], repo, env={"CHARTER_LLM_CMD": FAKE_AUDITOR})
    assert r.returncode == 0 and "VIOLATES" not in r.stdout


def test_audit_degrades_to_ambiguous_without_backend(repo):
    settle(repo)
    env = {k: "" for k in ("CHARTER_LLM_CMD", "ANTHROPIC_API_KEY")}
    r = run(["audit"], repo, env=env)
    assert r.returncode == 0 and "AMBIGUOUS" in r.stdout


def test_explain_json(repo):
    settle(repo)
    out = json.loads(run(["explain", "D-001", "--json"], repo).stdout)
    assert out["kind"] == "assert" and out["code_citations"]


def test_enforcer_symbol_must_match_whole_word(repo):
    (repo / "CHARTER.md").write_text(
        "[D-001] envelope type -> type: src/api/types.py#Envelope\n")
    (repo / "src" / "api").mkdir(parents=True)
    (repo / "src/api/types.py").write_text("class EnvelopeFactory: pass\n")
    run(["approve", "--why", "t"], repo)
    r = run(["check"], repo)
    assert r.returncode == 1 and "not found" in r.stdout
    (repo / "src/api/types.py").write_text("class Envelope: pass\n")
    assert run(["check"], repo).returncode == 0


def test_llm_backend_failure_reported_on_stderr(repo):
    settle(repo)
    cmd = f'{sys.executable} -c "import sys; sys.exit(3)"'
    r = run(["audit"], repo, env={"CHARTER_LLM_CMD": cmd})
    assert r.returncode == 0 and "AMBIGUOUS" in r.stdout  # degrades as before
    assert "exited 3" in r.stderr                         # but says why


def test_failing_backend_verdict_not_trusted(repo):
    settle(repo)
    lie = repo / "lie.py"
    lie.write_text('import sys\n'
                   'print(\'{"verdict":"COMPLIES","reason":"x"}\')\n'
                   'sys.exit(7)\n')
    r = run(["audit"], repo,
            env={"CHARTER_LLM_CMD": f'"{sys.executable}" "{lie}"'})
    assert r.returncode == 0 and "AMBIGUOUS" in r.stdout
    assert "COMPLIES" not in r.stdout


def test_ledger_timestamps_are_timezone_aware(repo):
    settle(repo)
    last = json.loads((repo / ".charter" / "ledger.jsonl")
                      .read_text(encoding="utf-8").splitlines()[-1])
    assert "+" in last["ts"] or last["ts"].endswith("Z")


def test_install_hook_uses_running_interpreter(repo):
    (repo / ".git" / "hooks").mkdir(parents=True)
    run(["install-hook"], repo)
    hook = (repo / ".git/hooks/pre-commit").read_text(encoding="utf-8")
    assert "python3" not in hook and sys.executable in hook


def test_hook_silent_when_index_unapproved_or_tampered(repo):
    (repo / "CHARTER.md").write_text(INTENT)  # never approved
    r = run(["hook"], repo)
    assert r.returncode == 0 and "D-001" not in r.stdout
    settle(repo)
    assert "D-001" in run(["hook"], repo).stdout  # approved -> injected
    (repo / "CHARTER.md").write_text(INTENT.replace("No JWT", "JWT fine"))
    r = run(["hook"], repo)  # tampered -> silent again
    assert r.returncode == 0 and "D-001" not in r.stdout


def test_graph_json_marks_code_vs_doc_citations(repo):
    settle(repo)
    (repo / "NOTES.md").write_text("see [D-001]\n")
    out = json.loads(run(["graph", "--json"], repo).stdout)
    kinds = {(e["from"], e.get("kind"))
             for e in out["edges"] if e["to"] == "D-001"}
    assert ("src/auth/token.py", "code") in kinds
    assert ("NOTES.md", "doc") in kinds


def test_doctor_flags_oversized_code_files(repo):
    settle(repo)
    (repo / "src/db/big.py").write_text("x = 1\n" * 200_000)
    r = run(["doctor"], repo)
    assert r.returncode == 0 and "scan size cap" in r.stdout


MALFORMED_LINE = "[D-009] wishful thinking with no enforcer arrow\n"


def test_audit_refuses_unparseable_intent(repo):
    (repo / "CHARTER.md").write_text(MALFORMED_LINE)
    r = run(["audit"], repo)
    assert r.returncode == 1
    assert "does not parse" in (r.stdout + r.stderr)


def append_malformed(repo):
    with open(repo / "CHARTER.md", "a", encoding="utf-8") as f:
        f.write(MALFORMED_LINE)


def test_trace_warns_on_unparseable_lines(repo):
    settle(repo)
    append_malformed(repo)
    r = run(["trace", "D-001"], repo)
    assert r.returncode == 0 and "implemented by" in r.stdout
    assert "WARN" in r.stderr and "enforcer" in r.stderr


def test_graph_json_warns_on_stderr_only(repo):
    settle(repo)
    append_malformed(repo)
    r = run(["graph", "--json"], repo)
    assert r.returncode == 0
    json.loads(r.stdout)
    assert "WARN" in r.stderr


def test_explain_warns_on_unparseable_lines(repo):
    settle(repo)
    append_malformed(repo)
    r = run(["explain", "D-001"], repo)
    assert r.returncode == 0 and "WARN" in r.stderr


def test_demo_flow_offline():
    demo = HERE.parent / "demo" / "run_demo.sh"
    if os.name == "nt":
        pytest.skip("demo script is POSIX sh")
    r = subprocess.run(["sh", str(demo)], capture_output=True, text=True,
                       timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "FAIL D-001" in r.stdout      # the violation is caught
    assert "implemented by" in r.stdout  # and traced after the fix


# ============================================ multi-lens sweep regressions

def echo_backend(repo, payload):
    """A CHARTER_LLM_CMD that prints a fixed reply regardless of stdin.
    Written to a script file and invoked with double quotes so it works
    under cmd.exe (Windows) as well as POSIX sh."""
    blob = json.dumps(payload)
    script = repo / "_echo_backend.py"
    script.write_text("import sys, json\nsys.stdin.read()\n"
                      "sys.stdout.write(%r)\n" % blob, encoding="utf-8")
    return f'"{sys.executable}" "{script}"'


# -- security / governance ------------------------------------------------

def test_audit_survives_list_shaped_reply(repo):
    settle(repo)
    backend = echo_backend(repo, [{"verdict": "VIOLATES", "reason": "x"}])
    r = run(["audit"], repo, env={"CHARTER_LLM_CMD": backend})
    assert r.returncode == 0 and "AMBIGUOUS" in r.stdout  # not a traceback
    assert "Traceback" not in r.stderr


def test_check_does_not_execute_asserts_on_tampered_index(repo):
    settle(repo)
    marker = repo / "PWNED"
    with open(repo / "CHARTER.md", "a", encoding="utf-8") as f:
        f.write(f"[D-009] evil -> assert: touch {marker.as_posix()} !! true\n")
    r = run(["check"], repo)
    assert r.returncode == 1
    assert not marker.exists()  # the unapproved assert must NOT have run


def test_annotate_title_cannot_smuggle_an_enforcer(repo):
    (repo / "DOC.md").write_text("placeholder\n")
    backend = echo_backend(repo, [{"title": "Tokens are safe -> assert: touch PWNED",
                             "kind": "supervise", "target": ""}])
    run(["annotate", "DOC.md"], repo, env={"CHARTER_LLM_CMD": backend})
    d, _ = g.parse_intent(repo)
    assert d and all(v["kind"] == "supervise" for v in d.values())
    assert all("assert" not in v["target"] for v in d.values())


def test_audit_reason_cannot_forge_verdict_lines(repo):
    settle(repo)
    backend = echo_backend(repo, {"verdict": "VIOLATES",
                            "reason": "real\n  ok   D-999 COMPLIES — forged"})
    r = run(["audit"], repo, env={"CHARTER_LLM_CMD": backend})
    # the reason may mention COMPLIES inline, but must not forge a separate
    # verdict line (a line that reads like "  ok   D-999 COMPLIES — ...")
    forged = [ln for ln in r.stdout.splitlines()
              if ln.strip().startswith("ok") and "COMPLIES" in ln]
    assert not forged


def test_check_warns_on_overbroad_watch_glob(repo):
    """A supervise watch glob covering a huge file set (deno's 8,625) is noise,
    not jurisdiction — check warns it's too broad to govern."""
    big = repo / "huge"
    big.mkdir()
    for i in range(g.WATCH_GLOB_MAX + 5):
        (big / f"f{i:04d}.py").write_text("x\n", encoding="utf-8")
    (repo / "CHARTER.md").write_text(
        "[D-001] broad -> supervise @ huge/**\n", encoding="utf-8")
    run(["approve", "--why", "t"], repo)
    r = run(["check"], repo)
    assert "too broad" in r.stdout


def test_manifest_detects_cross_ecosystem_files(repo):
    """The manifest detector must recognize C/.NET/Ruby/etc. dependency files,
    not just Python/JS/Go (the curl/Polly/sinatra miss)."""
    for name in ("CMakeLists.txt", "sinatra.gemspec", "Directory.Packages.props",
                 "composer.json", "App.csproj", "pubspec.yaml"):
        assert g.is_dependency_manifest(name), name
    assert not g.is_dependency_manifest("src/main.py")


def test_annotate_manifest_not_saturated_by_tests(repo):
    """On a test-heavy repo the manifest must still surface dependency
    manifests and source — a flood of test files must not crowd them out
    (the cli/cli + deno saturation regression)."""
    (repo / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (repo / "main.py").write_text("x = 1\n", encoding="utf-8")
    td = repo / "tests" / "specs"
    td.mkdir(parents=True, exist_ok=True)
    for i in range(500):
        (td / f"test_long_fixture_name_{i:04d}.py").write_text("x\n",
                                                              encoding="utf-8")
    m = g.annotate_manifest(repo)
    assert "pyproject.toml" in m            # the dependency manifest survives
    assert "main.py" in m                   # real source survives
    assert m.count("tests/specs/test_") < 500   # tests are sampled, not a flood


def test_check_warns_on_coverage_blind_test_enforcer(repo):
    """A `test:`/`type:` target with no #symbol only proves the FILE exists, not
    that it covers the decision (the httpx D-005 trap). check stays green but
    warns; a symbol-bound target does not warn."""
    (repo / "tests").mkdir()
    (repo / "tests" / "test_x.py").write_text("def test_real(): pass\n",
                                              encoding="utf-8")
    (repo / "CHARTER.md").write_text(
        "[D-001] covered -> test: tests/test_x.py\n", encoding="utf-8")
    assert run(["approve", "--why", "t"], repo).returncode == 0
    r = run(["check"], repo)
    assert r.returncode == 0                       # file exists -> still live
    assert "proves the file exists" in r.stdout    # ...but flagged as weak

    # a symbol-bound target proves coverage -> no warning
    (repo / "CHARTER.md").write_text(
        "[D-001] covered -> test: tests/test_x.py#test_real\n", encoding="utf-8")
    run(["approve", "--why", "t2"], repo)
    r2 = run(["check"], repo)
    assert r2.returncode == 0 and "proves the file exists" not in r2.stdout


def test_type_enforcer_resolves_dotted_member_symbol(repo):
    """A `type: file#Class.method` target must resolve to the member's
    definition (`def method` / `class`), not require the literal dotted string
    — otherwise a reasonable annotate suggestion false-fails as enforcer rot."""
    (repo / "app.py").write_text(
        "class Flask:\n    def wsgi_app(self):\n        pass\n", encoding="utf-8")
    ok = {"kind": "type", "target": "app.py#Flask.wsgi_app", "title": "x",
          "tripwire": "", "watch": []}
    assert g.verify_enforcer(repo, ok) is None
    # a genuinely absent member still fails
    rot = {"kind": "type", "target": "app.py#Flask.nope", "title": "x",
           "tripwire": "", "watch": []}
    assert g.verify_enforcer(repo, rot) is not None
    # non-dotted whole-token behavior unchanged: #Env must not match EnvFactory
    (repo / "t.py").write_text("class EnvFactory: pass\n", encoding="utf-8")
    sub = {"kind": "type", "target": "t.py#Env", "title": "x",
           "tripwire": "", "watch": []}
    assert g.verify_enforcer(repo, sub) is not None


def test_self_certifying_tripwire_is_flagged(repo):
    # assert passes (grep of a present file), so the only thing that can flag
    # this is trivial_tripwire firing — no exit-code escape hatch
    (repo / "src" / "auth" / "x.py").write_text("ok\n")
    (repo / "CHARTER.md").write_text(
        "[D-001] vacuous -> assert: ! grep -rq zz src/auth/x.py !! true\n")
    run(["approve", "--why", "t"], repo)
    r = run(["check"], repo)
    assert "tripwire is trivial" in r.stdout


# -- robustness -----------------------------------------------------------

def test_bom_prefixed_intent_first_decision_seen(repo):
    (repo / "CHARTER.md").write_bytes(
        b"\xef\xbb\xbf[D-001] no jwt -> assert: true !! true\n")
    d, _ = g.parse_intent(repo)
    assert "D-001" in d


def test_utf16_intent_fails_cleanly_not_traceback(repo):
    (repo / "CHARTER.md").write_bytes(
        "[D-001] x -> supervise @ src/**\n".encode("utf-16"))
    r = run(["check"], repo)
    assert "Traceback" not in r.stderr
    assert "charter:" in (r.stdout + r.stderr)


def test_directory_symbol_target_does_not_crash(repo):
    (repo / "CHARTER.md").write_text("[D-001] t -> type: src#Envelope\n")
    run(["approve", "--why", "t"], repo)
    r = run(["check"], repo)
    assert r.returncode == 1 and "Traceback" not in r.stderr


def test_digest_mark_preserves_foreign_ledger_lines(repo):
    settle(repo)
    led = repo / ".charter" / "ledger.jsonl"
    with open(led, "a", encoding="utf-8") as f:
        f.write("GARBAGE NOT JSON\n")
    before = led.read_text(encoding="utf-8")
    run(["digest", "--mark"], repo)
    after = led.read_text(encoding="utf-8")
    assert "GARBAGE NOT JSON" in after
    assert before.count("\n") <= after.count("\n")  # nothing destroyed


def test_explain_survives_ledger_entry_without_ts(repo):
    settle(repo)
    led = repo / ".charter" / "ledger.jsonl"
    with open(led, "a", encoding="utf-8") as f:
        f.write(json.dumps({"decision": "D-001", "verdict": "AMBIGUOUS",
                            "reason": "no ts"}) + "\n")
    r = run(["explain", "D-001"], repo)
    assert "Traceback" not in r.stderr


def test_install_hook_preserves_existing_hook(repo):
    (repo / ".git" / "hooks").mkdir(parents=True)
    hp = repo / ".git/hooks/pre-commit"
    hp.write_text("#!/bin/sh\nnpx husky run pre-commit\n", encoding="utf-8")
    run(["install-hook"], repo)
    body = hp.read_text(encoding="utf-8")
    assert "husky" in body and "charter" in body


def test_glob_match_no_catastrophic_backtracking():
    import time
    pat = "a/" + "**/" * 14 + "zz.py"
    path = "a/" + "/".join(f"x{i}" for i in range(30)) + "/yy.py"
    t0 = time.time()
    assert g.glob_match(path, pat) is False
    assert time.time() - t0 < 2.0


# -- cost / scale ---------------------------------------------------------

def test_audit_caps_files_per_decision(repo):
    settle(repo)
    for i in range(70):
        (repo / "src/db" / f"f{i:03d}.py").write_text(f"# [D-002]\nx={i}\n")
    backend = echo_backend(repo, {"verdict": "COMPLIES", "reason": "ok"})
    r = run(["audit"], repo, env={"CHARTER_LLM_CMD": backend})
    assert r.returncode == 0  # bounded work, no hang
    last = json.loads((repo / ".charter" / "ledger.jsonl")
                      .read_text(encoding="utf-8").splitlines()[-1])
    assert len(last["files"]) <= 60


def test_check_caps_uncited_warnings(repo):
    settle(repo)
    for i in range(30):
        (repo / "src/db" / f"f{i:03d}.py").write_text(f"x={i}\n")  # uncited
    r = run(["check", "--json"], repo)
    out = json.loads(r.stdout)
    uncited = [w for w in out["warnings"] if "uncited governed file" in w]
    assert len(uncited) <= 6  # capped + summary line, not 30


# ------------------------------------------- trust gate (publication audit)

def test_cloned_preapproved_repo_does_not_execute_asserts(repo):
    """A committed sentinel travels with a cloned repo — it proves the AUTHOR
    approved, not the user running check. Asserts must not execute."""
    marker = repo / "PWNED"
    (repo / "CHARTER.md").write_text(
        f"[D-001] evil -> assert: touch {marker.as_posix()} "
        f"!! echo x | grep -q x\n", encoding="utf-8")
    d = repo / ".charter"
    d.mkdir()
    (d / "charter.sha").write_text(g.intent_hash(repo) + "\n", encoding="utf-8")
    r = run(["check"], repo)
    assert r.returncode == 1
    assert "not from this machine" in r.stdout
    assert not marker.exists()


def test_forged_in_repo_trust_marker_is_ignored(repo):
    """The v0.4.0 hole: a repo could ship a `.charter/trusted` whose content is
    the (author-computable) intent hash and get its asserts executed on clone.
    Trust now lives in a per-user store outside the repo; an in-repo marker —
    even a perfectly-formed one — must grant nothing."""
    marker = repo / "PWNED"
    (repo / "CHARTER.md").write_text(
        f"[D-001] evil -> assert: touch {marker.as_posix()} "
        f"!! echo x | grep -q x\n", encoding="utf-8")
    d = repo / ".charter"
    d.mkdir()
    (d / "charter.sha").write_text(g.intent_hash(repo) + "\n", encoding="utf-8")
    # attacker forges the old-style in-repo marker with the correct hash
    (d / "trusted").write_text(g.intent_hash(repo) + "\n", encoding="utf-8")
    r = run(["check"], repo)
    assert r.returncode == 1
    assert "not from this machine" in r.stdout
    assert not marker.exists()


def test_trust_does_not_survive_repo_instance_replacement(repo):
    """Trust is bound to a repo INSTANCE, not just its path + CHARTER.md hash.
    A different repo dropped at the same path (e.g. delete + re-clone) with a
    byte-identical CHARTER.md must NOT inherit the prior approval — even though
    path and hash match — because it could ship altered assert helper scripts."""
    marker = repo / "RAN"
    (repo / "CHARTER.md").write_text(
        f"[D-001] x -> assert: touch {marker.as_posix()} "
        f"!! echo z | grep -q z\n", encoding="utf-8")
    assert run(["approve", "--why", "instance A"], repo).returncode == 0
    assert run(["check"], repo).returncode == 0
    assert marker.exists()                       # the approved instance executed
    marker.unlink()
    # simulate a replacement instance at the same path: a fresh clone's .git
    # carries no charter instance nonce (CHARTER.md/sentinel are unchanged)
    (repo / ".git" / "charter_instance").unlink()
    r = run(["check"], repo)
    assert r.returncode == 1
    assert "not from this machine" in r.stdout
    assert not marker.exists()                   # stale path-trust must not execute


def test_local_approve_grants_assert_execution(repo):
    settle(repo)
    import shutil
    shutil.rmtree(trust_home(repo), ignore_errors=True)   # simulate a fresh clone
    r = run(["check"], repo)
    assert r.returncode == 1 and "not from this machine" in r.stdout
    assert run(["approve", "--why", "reviewed after clone"], repo).returncode == 0
    assert run(["check"], repo).returncode == 0


def test_approve_writes_trust_outside_the_repo(repo):
    """The trust record must never land inside the repo tree (where it could be
    committed); it goes to the per-user store keyed by repo path."""
    settle(repo)
    assert not (repo / ".charter" / "trusted").exists()
    store = trust_home(repo) / ".charter" / "trust"
    assert store.is_dir() and any(store.iterdir())


def test_trust_optins_execute_asserts(repo):
    settle(repo)
    import shutil
    shutil.rmtree(trust_home(repo), ignore_errors=True)
    assert run(["check"], repo, env={"CHARTER_TRUST_ASSERTS": "1"}).returncode == 0
    assert run(["check", "--trust"], repo).returncode == 0


def test_crlf_charter_hashes_same_as_lf(repo):
    """approve on Windows (CRLF) must match check on Linux (LF) — the hash
    normalizes line endings so it isn't a false tamper."""
    body = "[D-001] x -> supervise @ src/**\n"
    (repo / "CHARTER.md").write_text(body, encoding="utf-8", newline="\n")
    lf = g.intent_hash(repo)
    (repo / "CHARTER.md").write_text(body, encoding="utf-8", newline="\r\n")
    crlf = g.intent_hash(repo)
    assert lf == crlf


def test_version_flag_matches_constant(repo):
    r = run(["--version"], repo)
    assert r.returncode == 0
    assert r.stdout.strip() == f"charter {g.__version__}"


def test_echo_pipeline_tripwire_is_not_trivial():
    """echo sample | real-detector is the canonical proof pattern — only a
    bare echo (exit status unconditionally 0) is vacuous."""
    assert not g.trivial_tripwire('echo supabase | grep -qiE "supabase|firebase"')
    assert g.trivial_tripwire("echo ok")
    assert g.trivial_tripwire("printf x")
    assert g.trivial_tripwire("true")
    assert g.trivial_tripwire(":")
