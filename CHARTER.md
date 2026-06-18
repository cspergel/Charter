# Intent Index — no decision without an enforcer
# ladder: structure > type > test > lint > assert > supervise

# source: README.md :: "It's one file, zero dependencies (Python 3.10+)"
[D-001] Charter ships as one file with zero runtime dependencies -> test: tests/test_charter.py#test_zero_runtime_dependencies
# source: README.md :: "A freshly cloned repo will not execute its asserts"
[D-002] A freshly cloned repo never executes its asserts before local approval -> test: tests/test_charter.py#test_cloned_preapproved_repo_does_not_execute_asserts
# source: README.md :: "even if it ships a forged trust marker"
[D-003] A repo-shipped (forged) trust marker is ignored -> test: tests/test_charter.py#test_forged_in_repo_trust_marker_is_ignored
# source: README.md :: "pinned to a per-repo instance nonce"
[D-004] Trust is pinned to a per-repo instance nonce and dies on replacement -> test: tests/test_charter.py#test_trust_does_not_survive_repo_instance_replacement
# source: README.md :: "recorded in a per-user trust store **outside** the repo"
[D-005] approve records execution trust outside the repo, not inside it -> test: tests/test_charter.py#test_approve_writes_trust_outside_the_repo
# source: README.md :: "Any change to CHARTER.md fails `check` until a human runs `approve`"
[D-006] Any change to CHARTER.md fails check until a human re-approves -> test: tests/test_charter.py#test_tamper_detected
# source: README.md :: "a weakened assert trips its tripwire"
[D-007] A weakened/vacuous assert is caught by its tripwire -> test: tests/test_charter.py#test_vacuous_assert_caught_by_tripwire
# source: README.md :: "`check` fails supervise decisions that end up blind"
[D-008] Blind supervise decisions (no citations, no watch scope) fail check by default -> test: tests/test_charter.py#test_blind_supervise_fails_by_default
# source: README.md :: "No backend configured → everything AMBIGUOUS, never crashes"
[D-009] With no LLM backend, audit degrades to AMBIGUOUS and never crashes -> test: tests/test_charter.py#test_audit_degrades_to_ambiguous_without_backend
# source: README.md :: "`.charter/ledger.jsonl` (append-only journal)"
[D-010] The ledger is append-only and tamper-evident -> test: tests/test_charter.py#test_log_verify_detects_tamper
# source: README.md :: "blocks an edit before it lands if the proposed content would trip an a"
[D-011] The PreToolUse hook blocks a violating edit before it lands -> test: tests/test_charter.py#test_hook_blocks_violating_edit
# source: README.md :: "CI opts in explicitly with `CHARTER_TRUST_ASSERTS=1`"
[D-012] Assert execution requires explicit CHARTER_TRUST_ASSERTS=1 opt-in -> test: tests/test_charter.py#test_trust_optins_execute_asserts
# source: README.md :: "capped at 15 by default (`--cap N`)"
[D-013] Annotation extraction is capped at 15 decisions by default -> assert: grep -qE 'default=15([^0-9]|$)' charter.py !! printf 'default=15)' | grep -qE 'default=15([^0-9]|$)'
# source: README.md :: "enforcer rot (the `#Symbol` vanished in a refactor)"
[D-014] An enforcer #Symbol must match a whole word, so rot is detected -> test: tests/test_charter.py#test_enforcer_symbol_must_match_whole_word
