#!/usr/bin/env python3
"""Offline stand-in for the LLM backend so the demo needs no API key.

charter pipes its prompt to CHARTER_LLM_CMD on stdin and reads the reply
from stdout. This fake recognizes the two prompt shapes charter sends
(annotate / audit) and answers with canned, deterministic output for the
demo's local-first SQLite scenario. Anchors are verbatim quotes from
ARCHITECTURE.md so the symbols can be inlined into the doc.
"""
import json
import sys

prompt = sys.stdin.read()

if "design-compliance auditor" in prompt:
    print(json.dumps({"verdict": "COMPLIES",
                      "reason": "offline fake backend: demo default"}))
    sys.exit(0)

print(json.dumps([
    {"title": "All persistence is local SQLite, never a hosted backend",
     "kind": "assert",
     "target": ('! grep -rqiE "supabase|firebase|dynamodb" src '
                '!! echo supabase | grep -qiE "supabase|firebase|dynamodb"'),
     "anchor": "every byte of user data lives in a local SQLite file"},
    {"title": "Auth sessions persist in the app's local SQLite database",
     "kind": "supervise",
     "target": "@ src/auth/**",
     "anchor": "Sessions are rows in that same SQLite database"},
]))
