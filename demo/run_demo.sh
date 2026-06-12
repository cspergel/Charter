#!/bin/sh
# charter demo: an AI agent violates the architecture; check catches it.
# Usage: sh run_demo.sh   (uses a fake annotator so no API key is needed;
# set CHARTER_LLM_CMD="claude -p" or ANTHROPIC_API_KEY for the real one)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || { echo "python not found on PATH"; exit 1; }
if [ -f "$HERE/charter.py" ]; then GOVPY="$HERE/charter.py"
elif [ -f "$HERE/../charter.py" ]; then GOVPY="$HERE/../charter.py"
else echo "charter.py not found next to demo or in parent"; exit 1; fi
gov() { "$PY" "$GOVPY" "$@"; }
cd "$HERE" && rm -rf repo && mkdir -p repo/src/db repo/src/auth && cd repo
git init -q 2>/dev/null || mkdir -p .git/hooks
cp ../ARCHITECTURE.md .

echo "── 1. Bootstrap governance from the prose doc"
if [ -z "$CHARTER_LLM_CMD" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
  # charter runs this via the platform shell (cmd.exe on Windows), so the
  # paths must be native there, not Git Bash /c/... form
  if command -v cygpath >/dev/null 2>&1; then
    export CHARTER_LLM_CMD="\"$(cygpath -w "$PY")\" \"$(cygpath -w "$HERE/fake_annotator.py")\""
  else
    export CHARTER_LLM_CMD="\"$PY\" \"$HERE/fake_annotator.py\""
  fi
fi
gov annotate ARCHITECTURE.md
echo
echo "── 2. Human reviews once and approves"
gov approve --why "initial local-first architecture"
echo
echo "── 3. Builder implements correctly (cites symbols)"
printf '# [D-001] local-first storage\nimport sqlite3\n' > src/db/connection.py
printf '# [D-002] sessions in sqlite\nimport sqlite3\n' > src/auth/session_store.py
gov check
echo
echo "── 4. Later, an AI agent asked to 'add login persistence' adds Supabase"
printf 'from supabase import create_client\n' > src/auth/supabase_client.py
echo "$ charter check"
gov check || true
echo
echo "── 5. Agent self-corrects to SQLite"
rm src/auth/supabase_client.py
gov check
echo
echo "── 6. Trace the decision to its implementation"
gov trace D-001
